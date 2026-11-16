"""Bound SQL for patient registration, editing and read-only clinical histories."""

from db.repositories.common import ConcurrentEditError, PatientNotFoundError, database_cursor


FIELDS = ('nom', 'prenom', 'dateNaissance', 'telephone', 'adresse')
COLUMNS = 'idPatient, nom, prenom, dateNaissance, telephone, adresse'
PAGE_SIZE = 25


def list_patients(search: str = '', page: int = 0) -> dict:
    # LOCATE treats %, _ and backslashes literally, unlike unescaped LIKE patterns.
    where = "WHERE LOCATE(%s, CONCAT_WS(' ', nom, prenom)) > 0 OR LOCATE(%s, CONCAT_WS(' ', prenom, nom)) > 0"
    values = (search.strip(), search.strip())
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total FROM PATIENT {where}', values)
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f'SELECT {COLUMNS} FROM PATIENT {where} ORDER BY nom, prenom, idPatient LIMIT %s OFFSET %s',
                       (*values, PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def patient_detail(patient_id: int) -> dict:
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT {COLUMNS} FROM PATIENT WHERE idPatient = %s', (patient_id,))
        patient = cursor.fetchone()
        if patient is None:
            raise PatientNotFoundError('Ce patient n’est plus disponible. Actualisez le répertoire.')
        cursor.execute("""
            SELECT c.idConsultation, c.dateHeure, c.motif, c.diagnostic,
                CONCAT(m.nom, ' ', m.prenom) AS medecin, c.idRDV, s.codeSalle
            FROM CONSULTATION c JOIN MEDECIN m ON m.idMedecin = c.idMedecin
            LEFT JOIN SALLE s ON s.idSalle = c.idSalle
            WHERE c.idPatient = %s ORDER BY c.dateHeure DESC, c.idConsultation DESC
        """, (patient_id,))
        consultations = cursor.fetchall()
        cursor.execute("""
            SELECT h.idHospitalisation, h.dateAdmission, h.dateSortie,
                ch.numeroChambre, l.numeroLit
            FROM HOSPITALISATION h JOIN LIT l ON l.idLit = h.idLit
            JOIN CHAMBRE ch ON ch.idChambre = l.idChambre
            WHERE h.idPatient = %s ORDER BY h.dateAdmission DESC, h.idHospitalisation DESC
        """, (patient_id,))
        hospitalizations = cursor.fetchall()
    return dict(patient=patient, consultations=consultations, hospitalizations=hospitalizations)


def add_patient(values: dict) -> int:
    with database_cursor() as cursor:
        cursor.execute('INSERT INTO PATIENT (nom, prenom, dateNaissance, telephone, adresse) VALUES (%s, %s, %s, %s, %s)',
                       tuple(values[field] for field in FIELDS))
        patient_id = cursor.lastrowid
    return patient_id


def update_patient(patient_id: int, values: dict, original: dict) -> None:
    """Lock and compare the original form snapshot to prevent lost edits, without new columns."""
    with database_cursor() as cursor:
        cursor.execute(f'SELECT {COLUMNS} FROM PATIENT WHERE idPatient = %s FOR UPDATE', (patient_id,))
        current = cursor.fetchone()
        if current is None:
            raise PatientNotFoundError('Ce patient n’est plus disponible. Actualisez le répertoire.')
        if any(current[field] != original[field] for field in FIELDS):
            raise ConcurrentEditError('Ce dossier a été modifié depuis l’ouverture du formulaire. Fermez puis rouvrez le formulaire pour recharger les informations.')
        cursor.execute('UPDATE PATIENT SET nom=%s, prenom=%s, dateNaissance=%s, telephone=%s, adresse=%s WHERE idPatient=%s',
                       (*[values[field] for field in FIELDS], patient_id))
