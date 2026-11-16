"""Validation compatible with existing unsigned IDs, DATETIME and text columns."""

from datetime import datetime

from services.patient_service import ValidationError


def identifier(value, *, optional=False):
    if optional and value is None:
        return None
    if type(value) is not int or not 1 <= value <= 4294967295:
        raise ValidationError('Sélectionnez un enregistrement valide.')
    return value


def timestamp(value):
    if not isinstance(value, datetime) or value.tzinfo is not None or value.year < 1000:
        raise ValidationError('Indiquez une date et une heure locales valides.')
    return value.replace(microsecond=0)


def text(value, label, *, maximum=None):
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f'{label} est obligatoire.')
    value = value.strip()
    if '\x00' in value or (maximum is not None and len(value) > maximum) or (maximum is None and len(value.encode('utf-8')) > 65535):
        raise ValidationError(f'{label} est trop long ou contient des caractères non autorisés.')
    return value
