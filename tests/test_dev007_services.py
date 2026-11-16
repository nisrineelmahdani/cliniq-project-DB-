"""Composite identity, mandatory doctor, snapshots and explicit removal consent."""

from datetime import datetime
from unittest.mock import patch

import pytest

from services import medical_act_service as service
from services.patient_service import ValidationError


CONTEXT=dict(idHospitalisation=4,idPatient=5,idLit=5,dateAdmission=datetime(2026,11,5,9),dateSortie=None)
ORIGINAL=dict(idHospitalisation=4,idActe=2,idMedecin=1)


@pytest.mark.parametrize('hospitalization,act,doctor',[(0,2,1),(4,0,1),(4,2,None),(True,2,1),(4,'2',1),(4,2,False),(4,2,4294967296)])
def test_invalid_identity_never_writes(hospitalization,act,doctor):
    with patch('services.medical_act_service.repository.add_assignment') as write:
        with pytest.raises(ValidationError):
            service.add_assignment(hospitalization,act,doctor,context=CONTEXT)
    write.assert_not_called()


@pytest.mark.parametrize('context',[None,{}, {**CONTEXT,'idHospitalisation':5}])
def test_context_is_required(context):
    with pytest.raises(ValidationError):
        service.add_assignment(4,2,1,context=context)


@pytest.mark.parametrize('original',[None,{}, {**ORIGINAL,'idActe':3},{**ORIGINAL,'idHospitalisation':5},{**ORIGINAL,'idMedecin':None}])
def test_reassignment_requires_exact_pair_snapshot(original):
    with patch('services.medical_act_service.repository.reassign') as write:
        with pytest.raises(ValidationError):
            service.reassign(4,2,2,original=original,context=CONTEXT)
    write.assert_not_called()


@pytest.mark.parametrize('confirmed',[False,None,1,'yes'])
def test_removal_requires_literal_confirmation(confirmed):
    with patch('services.medical_act_service.repository.remove_assignment') as remove:
        with pytest.raises(ValidationError):
            service.remove_assignment(4,2,original=ORIGINAL,context=CONTEXT,confirmed=confirmed)
    remove.assert_not_called()


def test_add_reassign_and_removal_delegate_existing_composite_pair():
    with patch('services.medical_act_service.repository.add_assignment') as add, \
         patch('services.medical_act_service.repository.reassign') as reassign, \
         patch('services.medical_act_service.repository.remove_assignment') as remove:
        service.add_assignment(4,2,1,context=CONTEXT)
        add.assert_called_once_with(4,2,1,context=CONTEXT)
        service.reassign(4,2,2,original=ORIGINAL,context=CONTEXT)
        reassign.assert_called_once_with(4,2,2,original=ORIGINAL,context=CONTEXT)
        service.remove_assignment(4,2,original=ORIGINAL,context=CONTEXT,confirmed=True)
        remove.assert_called_once_with(4,2,original=ORIGINAL,context=CONTEXT)
