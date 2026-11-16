"""Hospitalization dates, identity and stale-snapshot validation."""

from datetime import date, datetime

from db.repositories import hospitalization_repository as repository
from services.clinical_validation import identifier, timestamp
from services.patient_service import ValidationError


def validate_interval(admission, discharge):
    start = timestamp(admission)
    end = timestamp(discharge) if discharge is not None else None
    if end is not None and end < start:
        raise ValidationError('La sortie ne peut pas précéder l’admission.')
    return start, end


def validate_period(from_day, to_day):
    for value in (from_day, to_day):
        if value is not None and (not isinstance(value, date) or isinstance(value, datetime) or value.year < 1000):
            raise ValidationError('Indiquez une période d’admission valide.')
    if from_day is not None and to_day is not None and from_day > to_day:
        raise ValidationError('La fin de la période ne peut pas précéder son début.')


def validate_hospitalization(values):
    admission, discharge = validate_interval(values.get('dateAdmission'), values.get('dateSortie'))
    return dict(dateAdmission=admission, dateSortie=discharge,
                idPatient=identifier(values.get('idPatient')), idLit=identifier(values.get('idLit')))


def _original(hospitalization_id, original):
    identifier(hospitalization_id)
    if (not isinstance(original, dict) or original.get('idHospitalisation') != hospitalization_id
            or not all(key in original for key in repository.FIELDS)):
        raise ValidationError('Rechargez le séjour avant de le modifier.')
    identifier(original['idLit'])


def save_hospitalization(values, *, hospitalization_id=None, original=None):
    if hospitalization_id is not None:
        _original(hospitalization_id, original)
    return repository.save_hospitalization(validate_hospitalization(values), hospitalization_id=hospitalization_id, original=original)


def record_discharge(hospitalization_id, discharge, *, original):
    _original(hospitalization_id, original)
    if discharge is None:
        raise ValidationError('Indiquez la date et l’heure de sortie.')
    return save_hospitalization({**original, 'dateSortie': discharge}, hospitalization_id=hospitalization_id, original=original)


def available_beds(admission, discharge=None, *, room=None, exclude_id=None):
    admission, discharge = validate_interval(admission, discharge)
    if room is not None:
        identifier(room)
    if exclude_id is not None:
        identifier(exclude_id)
    return repository.available_beds(admission, discharge, room=room, exclude_id=exclude_id)
