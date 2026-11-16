"""Shared current-read locks for scheduling; no schema or trigger changes."""

from db.repositories.common import ConcurrentEditError, RepositoryError


class ClinicalRuleError(RepositoryError):
    """Controlled business feedback, never SQL or patient information."""


def lock_doctors(cursor, doctor_ids):
    # Every clinical writer follows doctor IDs ascending, appointment IDs
    # ascending, then consultation. Locking an existing parent serializes even
    # the first appointment in an otherwise empty schedule (no gap-only race).
    for doctor_id in sorted(set(doctor_ids)):
        cursor.execute('SELECT idMedecin FROM MEDECIN WHERE idMedecin=%s FOR UPDATE', (doctor_id,))
        if cursor.fetchone() is None:
            raise ClinicalRuleError('Le médecin sélectionné n’est plus disponible.')


def check_original(current, original, fields):
    if current is None:
        raise ClinicalRuleError('Cet enregistrement n’est plus disponible. Actualisez la liste.')
    if any(current[field] != original[field] for field in fields):
        raise ConcurrentEditError('Cet enregistrement a été modifié. Fermez puis rouvrez le formulaire avant de réessayer.')


def check_patient(cursor, patient_id):
    cursor.execute('SELECT idPatient FROM PATIENT WHERE idPatient=%s', (patient_id,))
    if cursor.fetchone() is None:
        raise ClinicalRuleError('Le patient sélectionné n’est plus disponible.')


def lookup_options():
    from db.repositories.common import database_cursor
    with database_cursor(readonly=True) as cursor:
        cursor.execute("SELECT idPatient, CONCAT(nom, ' ', prenom) AS label FROM PATIENT ORDER BY nom, prenom, idPatient")
        patients = cursor.fetchall()
        cursor.execute("SELECT idMedecin, CONCAT(nom, ' ', prenom) AS label FROM MEDECIN ORDER BY nom, prenom, idMedecin")
        doctors = cursor.fetchall()
        cursor.execute('SELECT idSalle, codeSalle AS label FROM SALLE ORDER BY codeSalle, idSalle')
        rooms = cursor.fetchall()
        cursor.execute('SELECT DISTINCT statut FROM RENDEZ_VOUS ORDER BY statut')
        statuses = [row['statut'] for row in cursor.fetchall()]
    return dict(patients=patients, doctors=doctors, rooms=rooms, statuses=statuses)
