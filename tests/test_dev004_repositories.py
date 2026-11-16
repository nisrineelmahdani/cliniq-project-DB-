"""SQL binding, current-read lock order, rejected conflicts and safe failures."""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import mysql.connector
import pytest

from db.repositories import appointment_repository as appointments, consultation_repository as consultations
from db.repositories.clinical_common import ClinicalRuleError
from db.repositories.common import ConcurrentEditError, RepositoryError
from tests.test_dev004_services import APPOINTMENT, CONSULTATION


@pytest.fixture
def database():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value

    @contextmanager
    def transaction():
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    with patch('db.repositories.common.transaction', transaction):
        yield connection, cursor


def test_appointment_locks_doctor_before_checking_empty_schedule(database):
    connection, cursor = database
    cursor.fetchone.side_effect = [{'idMedecin': 1}, {'idPatient': 1}, None]
    cursor.lastrowid = 10
    assert appointments.save_appointment(APPOINTMENT) == 10
    calls = cursor.execute.call_args_list
    assert 'MEDECIN' in calls[0].args[0] and 'FOR UPDATE' in calls[0].args[0]
    assert 'dateHeure < %s' in calls[2].args[0] and ' > %s' in calls[2].args[0]
    assert calls[2].args[1] == (1, 0, 'Annulé', datetime(2030, 1, 1, 9, 30), datetime(2030, 1, 1, 9))
    connection.commit.assert_called_once()


def test_overlap_rolls_back_without_insert(database):
    connection, cursor = database
    cursor.fetchone.side_effect = [{'idMedecin': 1}, {'idPatient': 1}, {'idRDV': 99}]
    with pytest.raises(ClinicalRuleError, match='chevauche'):
        appointments.save_appointment(APPOINTMENT)
    assert not any(call.args[0].startswith('INSERT') for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


def test_cancelled_slot_does_not_block_and_edit_excludes_self(database):
    _, cursor = database
    current = {**APPOINTMENT, 'idRDV': 3}
    cursor.fetchone.side_effect = [{'idMedecin': 1}, current, {'idPatient': 1}]
    appointments.save_appointment({**APPOINTMENT, 'statut': 'Annulé'}, appointment_id=3, original=current)
    assert not any('TIMESTAMPADD' in call.args[0] for call in cursor.execute.call_args_list)
    cursor.reset_mock()
    cursor.fetchone.side_effect = [{'idMedecin': 1}, current, {'idPatient': 1}, None]
    appointments.save_appointment(APPOINTMENT, appointment_id=3, original=current)
    assert cursor.execute.call_args_list[3].args[1][1] == 3


def test_stale_appointment_rejected(database):
    _, cursor = database
    cursor.fetchone.side_effect = [{'idMedecin': 1}, {**APPOINTMENT, 'statut': 'Confirmé'}]
    with pytest.raises(ConcurrentEditError):
        appointments.save_appointment(APPOINTMENT, appointment_id=3, original=APPOINTMENT)


def test_appointment_filter_values_are_bound(database):
    _, cursor = database
    cursor.fetchone.return_value = {'total': 1}
    cursor.fetchall.return_value = []
    needle = "O'Neil %_"
    appointments.list_appointments(needle, doctor=1, patient=2, day=datetime(2030, 1, 1).date(), status='Confirmé')
    sql, params = cursor.execute.call_args.args
    assert needle not in sql and params[:4] == (needle, 1, 2, 'Confirmé')
    assert params[4:6] == (datetime(2030, 1, 1), datetime(2030, 1, 2))


@pytest.mark.parametrize('appointment,existing,message', [
    ({'idPatient': 2, 'idMedecin': 1}, None, 'correspondre'),
    ({'idPatient': 1, 'idMedecin': 2}, None, 'correspondre'),
    ({'idPatient': 1, 'idMedecin': 1}, {'idConsultation': 4}, 'déjà lié'),
    (None, None, 'plus disponible'),
])
def test_consultation_link_validation_is_transactional(database, appointment, existing, message):
    connection, cursor = database
    cursor.fetchone.side_effect = [{'idMedecin': 1}, appointment, {'idPatient': 1}, existing]
    with pytest.raises(ClinicalRuleError, match=message):
        consultations.save_consultation({**CONSULTATION, 'idRDV': 3})
    connection.rollback.assert_called_once()
    assert not any(call.args[0].startswith('INSERT') for call in cursor.execute.call_args_list)


def test_consultation_edit_locks_doctors_then_appointments_in_ascending_order(database):
    _, cursor = database
    original = {**CONSULTATION, 'idMedecin': 2, 'idRDV': 6}
    cursor.fetchone.side_effect = [{'idMedecin': 1}, {'idMedecin': 2},
        {'idRDV': 3, 'idPatient': 1, 'idMedecin': 1}, {'idRDV': 6, 'idPatient': 1, 'idMedecin': 2},
        original, {'idPatient': 1}, None]
    consultations.save_consultation({**CONSULTATION, 'idRDV': 3}, consultation_id=8, original=original)
    first_calls = cursor.execute.call_args_list[:4]
    assert [call.args[1][0] for call in first_calls] == [1, 2, 3, 6]
    assert all('FOR UPDATE' in call.args[0] for call in first_calls)


def test_consultation_walkin_uses_null_links_and_bound_text(database):
    _, cursor = database
    cursor.fetchone.side_effect = [{'idMedecin': 1}, {'idPatient': 1}]
    cursor.lastrowid = 11
    assert consultations.save_consultation(CONSULTATION) == 11
    sql, params = cursor.execute.call_args.args
    assert CONSULTATION['diagnostic'] not in sql
    assert params[-2:] == (None, None)


def test_connector_failures_never_log_or_expose_clinical_details(database, caplog):
    _, cursor = database
    cursor.execute.side_effect = mysql.connector.Error('private diagnosis')
    with pytest.raises(RepositoryError) as caught:
        consultations.save_consultation(CONSULTATION)
    assert 'private' not in str(caught.value) and 'private' not in caplog.text
