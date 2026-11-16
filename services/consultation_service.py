"""Consultation validation and public write workflow."""

from db.repositories import consultation_repository
from services.clinical_validation import identifier, text, timestamp
from services.patient_service import ValidationError


def validate_consultation(values):
    return dict(dateHeure=timestamp(values.get('dateHeure')),
                motif=text(values.get('motif'), 'Le motif'), diagnostic=text(values.get('diagnostic'), 'Le diagnostic'),
                idPatient=identifier(values.get('idPatient')), idMedecin=identifier(values.get('idMedecin')),
                idRDV=identifier(values.get('idRDV'), optional=True), idSalle=identifier(values.get('idSalle'), optional=True))


def save_consultation(values, *, consultation_id=None, original=None):
    if consultation_id is not None:
        identifier(consultation_id)
        if original is None:
            raise ValidationError('Rouvrez la consultation avant de la modifier.')
    return consultation_repository.save_consultation(validate_consultation(values), consultation_id=consultation_id, original=original)
