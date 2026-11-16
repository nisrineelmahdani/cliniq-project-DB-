"""Input boundaries and delegation without database side effects."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from services.appointment_service import save_appointment, validate_appointment
from services.consultation_service import save_consultation, validate_consultation
from services.patient_service import ValidationError


APPOINTMENT = dict(dateHeure=datetime(2030, 1, 1, 9), dureePrevue=30, statut='Planifié', idPatient=1, idMedecin=1)
CONSULTATION = dict(dateHeure=datetime(2030, 1, 1, 9), motif='Motif fictif', diagnostic='Diagnostic fictif',
                    idPatient=1, idMedecin=1, idRDV=None, idSalle=None)


@pytest.mark.parametrize('field,value', [('dureePrevue', 0), ('dureePrevue', True), ('dureePrevue', 65536),
    ('dureePrevue', 1.5), ('statut', ''), ('statut', 'x'*41), ('statut', 'a\nb'),
    ('dateHeure', None), ('dateHeure', datetime(999, 1, 1)), ('dateHeure', datetime.now(timezone.utc)),
    ('idPatient', 0), ('idMedecin', True), ('idPatient', '1')])
def test_invalid_appointment_never_writes(field, value):
    with patch('services.appointment_service.appointment_repository.save_appointment') as write:
        with pytest.raises(ValidationError):
            save_appointment({**APPOINTMENT, field: value})
        write.assert_not_called()


def test_timestamp_overflow_and_unsigned_duration_limit():
    with pytest.raises(ValidationError):
        validate_appointment({**APPOINTMENT, 'dateHeure': datetime(9999, 12, 31, 23, 59)})
    assert validate_appointment({**APPOINTMENT, 'dureePrevue': 65535})['dureePrevue'] == 65535


def test_schema_has_no_status_enum_and_unicode_status_is_trimmed():
    assert validate_appointment({**APPOINTMENT, 'statut': '  Suivi personnalisé  '})['statut'] == 'Suivi personnalisé'


@pytest.mark.parametrize('field,value', [('motif', ''), ('diagnostic', ' '), ('motif', 'é'*32768),
    ('diagnostic', 'private\x00value'), ('idRDV', 0), ('idSalle', False), ('idMedecin', None)])
def test_invalid_consultation_never_writes(field, value):
    with patch('services.consultation_service.consultation_repository.save_consultation') as write:
        with pytest.raises(ValidationError) as caught:
            save_consultation({**CONSULTATION, field: value})
        assert 'private' not in str(caught.value)
        write.assert_not_called()


def test_optional_links_and_multiline_text_and_text_byte_boundary():
    values = validate_consultation({**CONSULTATION, 'motif': 'a'*65535, 'diagnostic': 'Ligne 1\nLigne 2'})
    assert values['idRDV'] is None and values['idSalle'] is None
    assert '\n' in values['diagnostic']


@pytest.mark.parametrize('service,values', [(save_appointment, APPOINTMENT), (save_consultation, CONSULTATION)])
def test_edit_requires_original_snapshot(service, values):
    with pytest.raises(ValidationError):
        service(values, **({'appointment_id': 1} if service is save_appointment else {'consultation_id': 1}))


def test_service_delegates_validated_appointment_and_consultation():
    with patch('services.appointment_service.appointment_repository.save_appointment', return_value=8) as write:
        assert save_appointment(APPOINTMENT) == 8
        assert write.call_args.args[0] == APPOINTMENT
    with patch('services.consultation_service.consultation_repository.save_consultation', return_value=9):
        assert save_consultation(CONSULTATION) == 9
