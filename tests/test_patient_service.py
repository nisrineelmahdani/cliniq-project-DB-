"""Business validation must pass before a repository can write."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest

from services.patient_service import ValidationError, add_patient, update_patient, validate_patient


VALID = dict(nom='  Démo  ', prenom='Zoë', dateNaissance=date(1990, 1, 1), telephone='+212 000 000 000', adresse='Rue fictive')


def test_unicode_names_and_strings_are_trimmed():
    assert validate_patient(VALID)['nom'] == 'Démo'
    assert validate_patient(VALID)['prenom'] == 'Zoë'


@pytest.mark.parametrize('field,value', [
    ('nom', ''), ('prenom', '   '), ('telephone', None), ('adresse', ''),
    ('nom', 'n' * 101), ('prenom', 'p' * 101), ('telephone', '1' * 31), ('adresse', 'a' * 256),
    ('nom', 'private\x00value'), ('dateNaissance', None), ('dateNaissance', '1990-01-01'),
    ('dateNaissance', date(999, 1, 1)), ('dateNaissance', datetime(1990, 1, 1)),
    ('dateNaissance', date.today() + timedelta(days=2)),
])
def test_invalid_patient_never_reaches_database(field, value):
    with patch('services.patient_service.patient_repository.add_patient') as write:
        with pytest.raises(ValidationError) as caught:
            add_patient({**VALID, field: value})
        write.assert_not_called()
    assert 'private' not in str(caught.value)


def test_add_and_edit_delegate_normalized_values():
    with patch('services.patient_service.patient_repository.add_patient', return_value=8) as create:
        assert add_patient(VALID) == 8
        assert create.call_args.args[0]['nom'] == 'Démo'
    with patch('services.patient_service.patient_repository.update_patient') as update:
        update_patient(8, VALID, VALID)
        assert update.call_args.args[0] == 8
        assert update.call_args.args[1]['nom'] == 'Démo'
        assert update.call_args.args[2] is VALID


@pytest.mark.parametrize('patient_id', [0, -1, True, '1', 4294967296])
def test_edit_rejects_invalid_id(patient_id):
    with patch('services.patient_service.patient_repository.update_patient') as update:
        with pytest.raises(ValidationError):
            update_patient(patient_id, VALID, VALID)
        update.assert_not_called()
