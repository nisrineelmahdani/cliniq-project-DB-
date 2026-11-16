"""Appointment validation and public write workflow."""

from datetime import timedelta

from db.repositories import appointment_repository
from services.clinical_validation import identifier, text, timestamp
from services.patient_service import ValidationError


def validate_appointment(values):
    duration = values.get('dureePrevue')
    if type(duration) is not int or not 1 <= duration <= 65535:
        raise ValidationError('La durée doit être un nombre entier de minutes entre 1 et 65535.')
    start = timestamp(values.get('dateHeure'))
    try:
        start + timedelta(minutes=duration)
    except OverflowError:
        raise ValidationError('La fin du rendez-vous dépasse les dates autorisées.') from None
    status = text(values.get('statut'), 'Le statut', maximum=40)
    if any(ord(char) < 32 for char in status):
        raise ValidationError('Le statut contient des caractères non autorisés.')
    return dict(dateHeure=start, dureePrevue=duration, statut=status,
                idPatient=identifier(values.get('idPatient')), idMedecin=identifier(values.get('idMedecin')))


def save_appointment(values, *, appointment_id=None, original=None):
    if appointment_id is not None:
        identifier(appointment_id)
        if original is None:
            raise ValidationError('Rouvrez le rendez-vous avant de le modifier.')
    return appointment_repository.save_appointment(validate_appointment(values), appointment_id=appointment_id, original=original)
