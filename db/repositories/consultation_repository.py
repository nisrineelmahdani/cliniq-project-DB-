"""Optional appointment/room links with serialized cross-table validation."""

from db.repositories.common import database_cursor
from db.repositories.clinical_common import ClinicalRuleError, check_original, check_patient, lock_doctors


FIELDS = ('dateHeure', 'motif', 'diagnostic', 'idPatient', 'idMedecin', 'idRDV', 'idSalle')
COLUMNS = 'idConsultation, ' + ', '.join(FIELDS)
PAGE_SIZE = 25


def list_consultations(search='', *, page=0):
    join = 'FROM CONSULTATION c JOIN PATIENT p ON p.idPatient=c.idPatient JOIN MEDECIN m ON m.idMedecin=c.idMedecin LEFT JOIN SALLE s ON s.idSalle=c.idSalle'
    where = "LOCATE(%s, CONCAT_WS(' ', p.nom, p.prenom, m.nom, m.prenom, c.motif, c.diagnostic, c.idConsultation)) > 0"
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {join} WHERE {where}', (search.strip(),))
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f"""SELECT c.*, CONCAT(p.nom, ' ', p.prenom) AS patient,
            CONCAT(m.nom, ' ', m.prenom) AS medecin, s.codeSalle
            {join} WHERE {where} ORDER BY c.dateHeure DESC,c.idConsultation DESC LIMIT %s OFFSET %s""",
                       (search.strip(), PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def get_consultation(consultation_id):
    with database_cursor(readonly=True) as cursor:
        cursor.execute("""SELECT c.*, CONCAT(p.nom, ' ', p.prenom) AS patient,
            CONCAT(m.nom, ' ', m.prenom) AS medecin, s.codeSalle
            FROM CONSULTATION c JOIN PATIENT p ON p.idPatient=c.idPatient
            JOIN MEDECIN m ON m.idMedecin=c.idMedecin LEFT JOIN SALLE s ON s.idSalle=c.idSalle
            WHERE c.idConsultation=%s""", (consultation_id,))
        row = cursor.fetchone()
    if row is None:
        raise ClinicalRuleError('Cette consultation n’est plus disponible.')
    return row


def appointment_options(patient_id, doctor_id, *, consultation_id=None):
    with database_cursor(readonly=True) as cursor:
        cursor.execute('''SELECT r.idRDV, r.dateHeure, r.statut FROM RENDEZ_VOUS r
            LEFT JOIN CONSULTATION c ON c.idRDV=r.idRDV
            WHERE r.idPatient=%s AND r.idMedecin=%s
              AND (c.idConsultation IS NULL OR c.idConsultation=%s)
            ORDER BY r.dateHeure DESC,r.idRDV DESC''', (patient_id, doctor_id, consultation_id))
        return cursor.fetchall()


def save_consultation(values, *, consultation_id=None, original=None):
    with database_cursor() as cursor:
        doctors = [values['idMedecin']]
        if original is not None:
            doctors.append(original['idMedecin'])
        lock_doctors(cursor, doctors)
        appointment_ids = {values['idRDV']}
        if original is not None:
            appointment_ids.add(original['idRDV'])
        appointments = {}
        for appointment_id in sorted(key for key in appointment_ids if key is not None):
            cursor.execute('SELECT idRDV,idPatient,idMedecin FROM RENDEZ_VOUS WHERE idRDV=%s FOR UPDATE', (appointment_id,))
            appointments[appointment_id] = cursor.fetchone()
        if consultation_id is not None:
            cursor.execute(f'SELECT {COLUMNS} FROM CONSULTATION WHERE idConsultation=%s FOR UPDATE', (consultation_id,))
            check_original(cursor.fetchone(), original, FIELDS)
        check_patient(cursor, values['idPatient'])
        if values['idRDV'] is not None:
            appointment = appointments[values['idRDV']]
            if appointment is None:
                raise ClinicalRuleError('Le rendez-vous sélectionné n’est plus disponible.')
            if any(appointment[key] != values[key] for key in ('idPatient', 'idMedecin')):
                raise ClinicalRuleError('Le patient et le médecin doivent correspondre à ceux du rendez-vous lié.')
            cursor.execute('SELECT idConsultation FROM CONSULTATION WHERE idRDV=%s AND idConsultation<>%s FOR UPDATE',
                           (values['idRDV'], consultation_id or 0))
            if cursor.fetchone() is not None:
                raise ClinicalRuleError('Ce rendez-vous est déjà lié à une consultation. Choisissez un autre rendez-vous ou aucun lien.')
        if values['idSalle'] is not None:
            cursor.execute('SELECT idSalle FROM SALLE WHERE idSalle=%s', (values['idSalle'],))
            if cursor.fetchone() is None:
                raise ClinicalRuleError('La salle sélectionnée n’est plus disponible.')
        if consultation_id is None:
            cursor.execute('INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV,idSalle) VALUES (%s,%s,%s,%s,%s,%s,%s)',
                           tuple(values[key] for key in FIELDS))
            consultation_id = cursor.lastrowid
        else:
            cursor.execute('UPDATE CONSULTATION SET dateHeure=%s,motif=%s,diagnostic=%s,idPatient=%s,idMedecin=%s,idRDV=%s,idSalle=%s WHERE idConsultation=%s',
                           (*[values[key] for key in FIELDS], consultation_id))
    return consultation_id
