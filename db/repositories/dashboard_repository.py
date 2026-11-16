"""Real dashboard aggregates from the approved MLD, in one read snapshot."""

from datetime import datetime, time, timedelta

from db.repositories.common import database_cursor


METRICS_SQL = """
WITH active_stays AS (
    SELECT idPatient, idLit FROM HOSPITALISATION
    WHERE dateAdmission <= %s AND (dateSortie IS NULL OR dateSortie > %s)
)
SELECT
    (SELECT COUNT(*) FROM PATIENT) AS patients,
    (SELECT COUNT(*) FROM MEDECIN) AS doctors,
    (SELECT COUNT(*) FROM RENDEZ_VOUS WHERE dateHeure >= %s AND dateHeure < %s) AS appointments,
    (SELECT COUNT(DISTINCT idPatient) FROM active_stays) AS hospitalized,
    (SELECT COUNT(DISTINCT idLit) FROM active_stays) AS occupied_beds,
    (SELECT COUNT(*) FROM LIT) - (SELECT COUNT(DISTINCT idLit) FROM active_stays) AS available_beds
"""


def load_dashboard(as_of: datetime) -> dict:
    """Treat stays as [admission, discharge); appointment counts include all statuses."""
    start = datetime.combine(as_of.date(), time.min)
    end = start + timedelta(days=1)
    period_start = start - timedelta(days=29)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(METRICS_SQL, (as_of, as_of, start, end))
        metrics = cursor.fetchone()
        cursor.execute("""
            SELECT c.idConsultation, c.dateHeure,
                CONCAT(p.nom, ' ', p.prenom) AS patient,
                CONCAT(m.nom, ' ', m.prenom) AS medecin,
                s.codeSalle
            FROM CONSULTATION c
            JOIN PATIENT p ON p.idPatient = c.idPatient
            JOIN MEDECIN m ON m.idMedecin = c.idMedecin
            LEFT JOIN SALLE s ON s.idSalle = c.idSalle
            WHERE c.dateHeure <= %s
            ORDER BY c.dateHeure DESC, c.idConsultation DESC LIMIT 10
        """, (as_of,))
        recent = cursor.fetchall()
        # Date spine supplies SQL-derived zero counts for genuinely inactive days.
        cursor.execute("""
            WITH RECURSIVE days AS (
                SELECT DATE(%s) AS jour
                UNION ALL SELECT DATE_ADD(jour, INTERVAL 1 DAY) FROM days WHERE jour < DATE(%s)
            )
            SELECT days.jour, COUNT(c.idConsultation) AS consultations
            FROM days LEFT JOIN CONSULTATION c
              ON c.dateHeure >= days.jour AND c.dateHeure < DATE_ADD(days.jour, INTERVAL 1 DAY)
             AND c.dateHeure <= %s
            GROUP BY days.jour ORDER BY days.jour
        """, (period_start, start, as_of))
        daily = cursor.fetchall()
        cursor.execute("""
            SELECT s.idService, s.libelleService AS service, COUNT(c.idConsultation) AS consultations
            FROM SERVICE s
            LEFT JOIN MEDECIN m ON m.idService = s.idService
            LEFT JOIN CONSULTATION c ON c.idMedecin = m.idMedecin
                AND c.dateHeure >= %s AND c.dateHeure <= %s
            GROUP BY s.idService, s.libelleService ORDER BY consultations DESC, s.idService
        """, (period_start, as_of))
        by_service = cursor.fetchall()
    return dict(metrics=metrics, recent=recent, daily=daily, by_service=by_service, as_of=as_of)
