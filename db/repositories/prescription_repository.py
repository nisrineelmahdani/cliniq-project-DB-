"""PRESCRIRE association operations; never creates a PRESCRIPTION entity."""

from datetime import datetime, time, timedelta

import mysql.connector
from mysql.connector import errorcode

from db.repositories.common import ConcurrentEditError, RepositoryError, database_cursor


PAGE_SIZE = 25
FIELDS = ('quantite', 'posologie', 'duree')
CONTEXT_FIELDS = ('idPatient', 'idMedecin', 'dateHeure', 'motif', 'diagnostic')
PAIR_COLUMNS = 'idConsultation,idMedicament,quantite,posologie,duree'


class PrescriptionError(RepositoryError):
    """Safe feedback without SQL text, medication instructions or patient values."""


def filter_options():
    with database_cursor(readonly=True) as cursor:
        cursor.execute("SELECT idPatient, CONCAT(nom,' ',prenom) AS label FROM PATIENT ORDER BY nom,prenom,idPatient")
        patients = cursor.fetchall()
        cursor.execute("SELECT idMedecin, CONCAT(nom,' ',prenom) AS label FROM MEDECIN ORDER BY nom,prenom,idMedecin")
        doctors = cursor.fetchall()
        cursor.execute('SELECT DISTINCT forme FROM MEDICAMENT ORDER BY forme')
        forms = [row['forme'] for row in cursor.fetchall()]
    return dict(patients=patients, doctors=doctors, forms=forms)


def list_consultations(search='', *, doctor=None, patient=None, day=None, prescribed=None, page=0):
    join = 'FROM CONSULTATION c JOIN PATIENT p ON p.idPatient=c.idPatient JOIN MEDECIN m ON m.idMedecin=c.idMedecin'
    clauses = ["LOCATE(%s,CONCAT_WS(' ',c.idConsultation,p.nom,p.prenom,m.nom,m.prenom,c.motif,c.diagnostic))>0"]
    params = [search.strip()]
    for column, value in [('c.idMedecin', doctor), ('c.idPatient', patient)]:
        if value is not None:
            clauses.append(f'{column}=%s')
            params.append(value)
    if day is not None:
        start = datetime.combine(day, time.min)
        clauses.append('c.dateHeure >= %s AND c.dateHeure < %s')
        params.extend((start, start + timedelta(days=1)))
    if prescribed is not None:
        clauses.append('EXISTS(SELECT 1 FROM PRESCRIRE rx WHERE rx.idConsultation=c.idConsultation)=%s')
        params.append(prescribed)
    where = ' AND '.join(clauses)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {join} WHERE {where}', tuple(params))
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f"""SELECT c.idConsultation,c.dateHeure,
            CONCAT(p.nom,' ',p.prenom) AS patient,CONCAT(m.nom,' ',m.prenom) AS medecin,
            (SELECT COUNT(*) FROM PRESCRIRE rx WHERE rx.idConsultation=c.idConsultation) AS medications
            {join} WHERE {where} ORDER BY c.dateHeure DESC,c.idConsultation DESC LIMIT %s OFFSET %s""",
                       (*params, PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def consultation_detail(consultation_id):
    with database_cursor(readonly=True) as cursor:
        cursor.execute("""SELECT c.*,CONCAT(p.nom,' ',p.prenom) AS patient,CONCAT(m.nom,' ',m.prenom) AS medecin
            FROM CONSULTATION c JOIN PATIENT p ON p.idPatient=c.idPatient
            JOIN MEDECIN m ON m.idMedecin=c.idMedecin WHERE c.idConsultation=%s""", (consultation_id,))
        consultation = cursor.fetchone()
        if consultation is None:
            raise PrescriptionError('Cette consultation n’est plus disponible. Actualisez la liste.')
        cursor.execute('''SELECT rx.*,m.nomMedicament,m.forme,m.dosage
            FROM PRESCRIRE rx JOIN MEDICAMENT m ON m.idMedicament=rx.idMedicament
            WHERE rx.idConsultation=%s ORDER BY m.nomMedicament,m.idMedicament''', (consultation_id,))
        prescriptions = cursor.fetchall()
    return dict(consultation=consultation, prescriptions=prescriptions)


def list_medications(consultation_id, search='', *, form=None, available_only=True, page=0):
    join = 'FROM MEDICAMENT m LEFT JOIN PRESCRIRE rx ON rx.idMedicament=m.idMedicament AND rx.idConsultation=%s'
    clauses = ["LOCATE(%s,CONCAT_WS(' ',m.nomMedicament,m.forme,m.dosage))>0"]
    params = [consultation_id, search.strip()]
    if form is not None:
        clauses.append('m.forme=%s')
        params.append(form)
    if available_only:
        clauses.append('rx.idMedicament IS NULL')
    where = ' AND '.join(clauses)
    with database_cursor(readonly=True) as cursor:
        cursor.execute(f'SELECT COUNT(*) AS total {join} WHERE {where}', tuple(params))
        total = cursor.fetchone()['total']
        page = min(max(0, page), max(0, (total - 1) // PAGE_SIZE))
        cursor.execute(f'''SELECT m.*,rx.idMedicament IS NOT NULL AS assigned
            {join} WHERE {where} ORDER BY m.nomMedicament,m.idMedicament LIMIT %s OFFSET %s''',
                       (*params, PAGE_SIZE, page * PAGE_SIZE))
        rows = cursor.fetchall()
    return dict(rows=rows, total=total, page=page)


def _lock_context(cursor, consultation_id, context):
    # Parent-first locking serializes even concurrent first inserts of the same
    # pair and guards against consultation edits while the form was open.
    cursor.execute('SELECT * FROM CONSULTATION WHERE idConsultation=%s FOR UPDATE', (consultation_id,))
    current = cursor.fetchone()
    if current is None:
        raise PrescriptionError('Cette consultation n’est plus disponible.')
    if any(current[key] != context[key] for key in CONTEXT_FIELDS):
        raise ConcurrentEditError('La consultation a changé. Actualisez son contexte avant de modifier les médicaments.')


def _lock_medication(cursor, medication_id):
    cursor.execute('SELECT idMedicament FROM MEDICAMENT WHERE idMedicament=%s FOR SHARE', (medication_id,))
    if cursor.fetchone() is None:
        raise PrescriptionError('Ce médicament n’est plus disponible dans le catalogue.')


def _lock_pair(cursor, consultation_id, medication_id):
    cursor.execute(f'SELECT {PAIR_COLUMNS} FROM PRESCRIRE WHERE idConsultation=%s AND idMedicament=%s FOR UPDATE',
                   (consultation_id, medication_id))
    return cursor.fetchone()


def _check_original(current, original):
    if current is None:
        raise PrescriptionError('Ce médicament n’est plus prescrit pour cette consultation. Actualisez la liste.')
    if any(current[key] != original[key] for key in FIELDS):
        raise ConcurrentEditError('Cette prescription a été modifiée. Rechargez ses valeurs avant de réessayer.')


def _execute_write(cursor, sql, params):
    try:
        cursor.execute(sql, params)
    except mysql.connector.Error as exc:
        messages = {
            errorcode.ER_DUP_ENTRY: 'Ce médicament est déjà prescrit pour cette consultation. Modifiez la ligne existante.',
            errorcode.ER_NO_REFERENCED_ROW_2: 'La consultation ou le médicament n’est plus disponible. Actualisez les listes.',
            errorcode.ER_CHECK_CONSTRAINT_VIOLATED: 'La quantité et la durée doivent être strictement positives.',
            errorcode.ER_BAD_NULL_ERROR: 'Tous les attributs de la prescription sont obligatoires.',
            errorcode.ER_WARN_DATA_OUT_OF_RANGE: 'La quantité ou la durée dépasse les limites autorisées.',
        }
        if exc.errno in messages:
            raise PrescriptionError(messages[exc.errno]) from None
        raise  # database_cursor sanitizes any other connector/commit failure


def add_prescription(consultation_id, medication_id, values, *, context):
    with database_cursor() as cursor:
        _lock_context(cursor, consultation_id, context)
        _lock_medication(cursor, medication_id)
        if _lock_pair(cursor, consultation_id, medication_id) is not None:
            raise PrescriptionError('Ce médicament est déjà prescrit pour cette consultation. Modifiez la ligne existante.')
        _execute_write(cursor, 'INSERT INTO PRESCRIRE (idConsultation,idMedicament,quantite,posologie,duree) VALUES (%s,%s,%s,%s,%s)',
                       (consultation_id, medication_id, *[values[key] for key in FIELDS]))


def update_prescription(consultation_id, medication_id, values, *, original, context):
    with database_cursor() as cursor:
        _lock_context(cursor, consultation_id, context)
        _lock_medication(cursor, medication_id)
        _check_original(_lock_pair(cursor, consultation_id, medication_id), original)
        _execute_write(cursor, 'UPDATE PRESCRIRE SET quantite=%s,posologie=%s,duree=%s WHERE idConsultation=%s AND idMedicament=%s',
                       (*[values[key] for key in FIELDS], consultation_id, medication_id))


def remove_prescription(consultation_id, medication_id, *, original, context):
    with database_cursor() as cursor:
        _lock_context(cursor, consultation_id, context)
        _lock_medication(cursor, medication_id)
        _check_original(_lock_pair(cursor, consultation_id, medication_id), original)
        _execute_write(cursor, 'DELETE FROM PRESCRIRE WHERE idConsultation=%s AND idMedicament=%s', (consultation_id, medication_id))
