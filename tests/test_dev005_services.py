"""Association attribute limits, composite identity and explicit removal consent."""

from datetime import datetime
from unittest.mock import patch

import pytest

from services import prescription_service as service
from services.patient_service import ValidationError


CONTEXT = dict(idConsultation=7, idPatient=5, idMedecin=5, dateHeure=datetime(2026,11,5,16), motif='Motif fictif', diagnostic='Diagnostic fictif')
VALUES = dict(quantite=2, posologie='Instructions fictives', duree=3)
ORIGINAL = dict(idConsultation=7, idMedicament=2, **VALUES)


@pytest.mark.parametrize('field,value', [('quantite',0), ('quantite',-1), ('quantite',True), ('quantite',1.5),
    ('quantite',4294967296), ('duree',0), ('duree',-1), ('duree',True), ('duree',65536),
    ('posologie',''), ('posologie','  '), ('posologie','x'*256), ('posologie','secret\x00value')])
def test_invalid_attributes_never_reach_repository(field,value):
    with patch('services.prescription_service.repository.add_prescription') as write:
        with pytest.raises(ValidationError) as caught:
            service.add_prescription(7,2,{**VALUES,field:value},context=CONTEXT)
    assert 'secret' not in str(caught.value)
    write.assert_not_called()


def test_exact_unsigned_and_varchar_boundaries_and_trimmed_unicode():
    cleaned = service.validate_attributes(dict(quantite=4294967295,duree=65535,posologie='é'*255))
    assert cleaned['quantite']==4294967295 and cleaned['duree']==65535 and len(cleaned['posologie'])==255
    assert service.validate_attributes({**VALUES,'posologie':'  Démo\nuniquement  '})['posologie']=='Démo\nuniquement'


@pytest.mark.parametrize('consultation,medication', [(0,2),(7,0),(True,2),(7,'2')])
def test_invalid_composite_identity(consultation,medication):
    with pytest.raises(ValidationError):
        service.add_prescription(consultation,medication,VALUES,context=CONTEXT)


@pytest.mark.parametrize('context', [None, {}, {**CONTEXT,'idConsultation':8}])
def test_context_is_required(context):
    with pytest.raises(ValidationError):
        service.add_prescription(7,2,VALUES,context=context)


@pytest.mark.parametrize('original', [None, {}, {**ORIGINAL,'idMedicament':3}, {**ORIGINAL,'idConsultation':8}])
def test_edit_requires_snapshot_for_both_composite_key_columns(original):
    with pytest.raises(ValidationError):
        service.update_prescription(7,2,VALUES,original=original,context=CONTEXT)


@pytest.mark.parametrize('confirmation', [False,None,1,'yes'])
def test_removal_requires_literal_true(confirmation):
    with patch('services.prescription_service.repository.remove_prescription') as delete:
        with pytest.raises(ValidationError):
            service.remove_prescription(7,2,original=ORIGINAL,context=CONTEXT,confirmed=confirmation)
    delete.assert_not_called()


def test_delegates_only_association_attributes_and_confirmed_removal():
    with patch('services.prescription_service.repository.add_prescription') as add, \
         patch('services.prescription_service.repository.update_prescription') as update, \
         patch('services.prescription_service.repository.remove_prescription') as delete:
        service.add_prescription(7,2,{**VALUES,'nomMedicament':'must not update catalog'},context=CONTEXT)
        assert add.call_args.args==(7,2,VALUES)
        service.update_prescription(7,2,VALUES,original=ORIGINAL,context=CONTEXT)
        assert update.call_args.kwargs['original']==ORIGINAL
        service.remove_prescription(7,2,original=ORIGINAL,context=CONTEXT,confirmed=True)
        delete.assert_called_once_with(7,2,original=ORIGINAL,context=CONTEXT)
