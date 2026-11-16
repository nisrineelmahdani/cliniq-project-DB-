"""Repository parameter binding, lifecycle, and patient-safe failures."""

from contextlib import contextmanager
from datetime import date, datetime
from unittest.mock import MagicMock, patch

import mysql.connector
import pytest

from db.repositories import dashboard_repository as dashboard, patient_repository as patients
from db.repositories.common import ConcurrentEditError, PatientNotFoundError, RepositoryError


PATIENT = dict(idPatient=1, nom='Demo', prenom='Test', dateNaissance=date(1990, 1, 1),
               telephone='DEMO', adresse='Adresse fictive')


@pytest.fixture
def db():
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value

    @contextmanager
    def fake_transaction():
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    with patch('db.repositories.common.transaction', fake_transaction):
        yield connection, cursor


def test_search_and_pagination_bind_untrusted_values(db):
    connection, cursor = db
    cursor.fetchone.return_value = {'total': 51}
    cursor.fetchall.return_value = [PATIENT]
    needle = "O'Neil %_\\ OR 1=1"
    result = patients.list_patients(needle, 99)
    assert result == dict(rows=[PATIENT], total=51, page=2)
    sql, params = cursor.execute.call_args.args
    assert needle not in sql
    assert 'LOCATE' in sql and 'ORDER BY nom, prenom, idPatient' in sql
    assert params == (needle, needle, 25, 50)
    connection.start_transaction.assert_called_once_with(isolation_level='REPEATABLE READ', consistent_snapshot=True, readonly=True)
    connection.close.assert_called_once()


def test_create_binds_all_fields_and_commits(db):
    connection, cursor = db
    cursor.lastrowid = 9
    assert patients.add_patient(PATIENT) == 9
    sql, params = cursor.execute.call_args.args
    assert params == tuple(PATIENT[field] for field in patients.FIELDS)
    assert 'Adresse fictive' not in sql
    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()


def test_update_locks_original_and_allows_unchanged_rows(db):
    connection, cursor = db
    cursor.fetchone.return_value = PATIENT.copy()
    patients.update_patient(1, PATIENT, PATIENT)
    assert 'FOR UPDATE' in cursor.execute.call_args_list[0].args[0]
    assert cursor.execute.call_args_list[0].args[1] == (1,)
    assert cursor.execute.call_args.args[1][-1] == 1
    connection.commit.assert_called_once()


@pytest.mark.parametrize('current,error', [(None, PatientNotFoundError), ({**PATIENT, 'adresse': 'Changed'}, ConcurrentEditError)])
def test_edit_rejects_missing_or_stale_patient(db, current, error):
    connection, cursor = db
    cursor.fetchone.return_value = current
    with pytest.raises(error):
        patients.update_patient(1, PATIENT, PATIENT)
    assert cursor.execute.call_count == 1
    connection.rollback.assert_called_once()


def test_patient_histories_bind_id_and_include_optional_room(db):
    _, cursor = db
    cursor.fetchone.return_value = PATIENT
    cursor.fetchall.side_effect = [[], []]
    assert patients.patient_detail(1) == dict(patient=PATIENT, consultations=[], hospitalizations=[])
    assert all(call.args[1] == (1,) for call in cursor.execute.call_args_list)
    assert 'LEFT JOIN SALLE' in cursor.execute.call_args_list[1].args[0]


@pytest.mark.parametrize('stage', ['execute', 'commit'])
def test_database_failures_never_expose_patient_details(db, stage, caplog):
    connection, cursor = db
    target = cursor.execute if stage == 'execute' else connection.commit
    target.side_effect = mysql.connector.Error('secret diagnosis for a named patient')
    with pytest.raises(RepositoryError) as caught:
        patients.add_patient(PATIENT)
    assert 'secret' not in str(caught.value)
    assert caught.value.__suppress_context__
    assert 'secret' not in caplog.text
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_dashboard_uses_one_snapshot_and_bound_clinic_time(db):
    connection, cursor = db
    instant = datetime(2026, 11, 16, 12, 30)
    cursor.fetchone.return_value = dict(patients=7, doctors=5, appointments=0, hospitalized=2, occupied_beds=2, available_beds=5)
    cursor.fetchall.side_effect = [[], [], []]
    result = dashboard.load_dashboard(instant)
    assert result['metrics']['available_beds'] == 5
    assert result['as_of'] == instant
    sql, params = cursor.execute.call_args_list[0].args
    assert 'COUNT(DISTINCT idPatient)' in sql and 'COUNT(DISTINCT idLit)' in sql
    assert 'dateAdmission <= %s' in sql and 'dateSortie > %s' in sql
    assert params == (instant, instant, datetime(2026, 11, 16), datetime(2026, 11, 17))
    assert cursor.execute.call_args_list[1].args[1] == (instant,)
    connection.start_transaction.assert_called_once()
