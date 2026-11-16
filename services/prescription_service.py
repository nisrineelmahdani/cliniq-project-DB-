"""Validated association workflows; keys and MEDICAMENT attributes are immutable."""

from db.repositories import prescription_repository as repository
from services.clinical_validation import identifier, text
from services.patient_service import ValidationError


def validate_attributes(values):
    quantity, duration = values.get('quantite'), values.get('duree')
    if type(quantity) is not int or not 1 <= quantity <= 4294967295:
        raise ValidationError('La quantité doit être un entier entre 1 et 4294967295.')
    if type(duration) is not int or not 1 <= duration <= 65535:
        raise ValidationError('La durée doit être un entier entre 1 et 65535 jours.')
    return dict(quantite=quantity, posologie=text(values.get('posologie'), 'La posologie', maximum=255), duree=duration)


def _validate_context(consultation_id, medication_id, context, original=None, *, require_original=False):
    identifier(consultation_id)
    identifier(medication_id)
    if (not isinstance(context, dict) or context.get('idConsultation') != consultation_id
            or not all(key in context for key in repository.CONTEXT_FIELDS)):
        raise ValidationError('Sélectionnez et rechargez le contexte de la consultation.')
    if require_original and (not isinstance(original, dict) or
            original.get('idConsultation') != consultation_id or original.get('idMedicament') != medication_id
            or not all(key in original for key in repository.FIELDS)):
        raise ValidationError('Rechargez la prescription avant de la modifier ou de la retirer.')


def add_prescription(consultation_id, medication_id, values, *, context):
    _validate_context(consultation_id, medication_id, context)
    repository.add_prescription(consultation_id, medication_id, validate_attributes(values), context=context)


def update_prescription(consultation_id, medication_id, values, *, original, context):
    _validate_context(consultation_id, medication_id, context, original, require_original=True)
    repository.update_prescription(consultation_id, medication_id, validate_attributes(values), original=original, context=context)


def remove_prescription(consultation_id, medication_id, *, original, context, confirmed=False):
    if confirmed is not True:
        raise ValidationError('Confirmez explicitement le retrait de ce médicament avant de continuer.')
    _validate_context(consultation_id, medication_id, context, original, require_original=True)
    repository.remove_prescription(consultation_id, medication_id, original=original, context=context)
