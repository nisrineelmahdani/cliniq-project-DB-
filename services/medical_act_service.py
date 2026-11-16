"""CIF assignment workflows; no act execution or new entity is represented."""

from db.repositories import medical_act_repository as repository
from services.clinical_validation import identifier
from services.patient_service import ValidationError


def _validate(hospitalization_id,act_id,context,original=None,*,editing=False):
    identifier(hospitalization_id)
    identifier(act_id)
    if (not isinstance(context,dict) or context.get('idHospitalisation')!=hospitalization_id
            or not all(key in context for key in repository.CONTEXT_FIELDS)):
        raise ValidationError('Sélectionnez et rechargez le contexte du séjour.')
    if editing:
        if (not isinstance(original,dict) or original.get('idHospitalisation')!=hospitalization_id
                or original.get('idActe')!=act_id or 'idMedecin' not in original):
            raise ValidationError('Rechargez l’affectation correspondant au couple séjour–acte.')
        identifier(original['idMedecin'])


def add_assignment(hospitalization_id,act_id,doctor_id,*,context):
    _validate(hospitalization_id,act_id,context)
    identifier(doctor_id)
    repository.add_assignment(hospitalization_id,act_id,doctor_id,context=context)


def reassign(hospitalization_id,act_id,doctor_id,*,original,context):
    _validate(hospitalization_id,act_id,context,original,editing=True)
    identifier(doctor_id)
    repository.reassign(hospitalization_id,act_id,doctor_id,original=original,context=context)


def remove_assignment(hospitalization_id,act_id,*,original,context,confirmed=False):
    if confirmed is not True:
        raise ValidationError('Confirmez explicitement le retrait de cette responsabilité avant de continuer.')
    _validate(hospitalization_id,act_id,context,original,editing=True)
    repository.remove_assignment(hospitalization_id,act_id,original=original,context=context)
