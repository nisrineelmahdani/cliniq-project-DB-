"""Patient input validation; error messages never echo submitted values."""

from datetime import date, datetime

from db.repositories import patient_repository
from services.clinic_clock import clinic_now


class ValidationError(ValueError):
    """A safe, actionable validation message for the form."""


def validate_patient(values: dict, *, today: date | None = None) -> dict:
    cleaned: dict[str, object] = {}
    labels = {'nom': ('Le nom', 100), 'prenom': ('Le prénom', 100),
              'telephone': ('Le téléphone', 30), 'adresse': ('L’adresse', 255)}
    for field, (label, maximum) in labels.items():
        value = values.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f'{label} est obligatoire.')
        value = value.strip()
        if len(value) > maximum:
            raise ValidationError(f'{label} doit contenir au maximum {maximum} caractères.')
        if any(ord(char) < 32 for char in value):
            raise ValidationError(f'{label} contient des caractères non autorisés.')
        cleaned[field] = value
    birth = values.get('dateNaissance')
    today = today or clinic_now().date()
    if (not isinstance(birth, date) or isinstance(birth, datetime)
            or not date(1000, 1, 1) <= birth <= today):
        raise ValidationError('Indiquez une date de naissance valide, non future.')
    cleaned['dateNaissance'] = birth
    return cleaned


def _validate_id(patient_id: int) -> None:
    if type(patient_id) is not int or not 1 <= patient_id <= 4294967295:
        raise ValidationError('Sélectionnez un patient valide.')


def add_patient(values: dict) -> int:
    return patient_repository.add_patient(validate_patient(values))


def update_patient(patient_id: int, values: dict, original: dict) -> None:
    _validate_id(patient_id)
    patient_repository.update_patient(patient_id, validate_patient(values), original)
