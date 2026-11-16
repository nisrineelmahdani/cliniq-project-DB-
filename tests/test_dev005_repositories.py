"""Bound SQL, ordered locks, transaction rollback and controlled constraint errors."""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock, patch

import mysql.connector
import pytest

from db.repositories import prescription_repository as repository
from db.repositories.common import ConcurrentEditError, RepositoryError
from tests.test_dev005_services import CONTEXT, VALUES, ORIGINAL


@pytest.fixture
def database():
    connection=MagicMock()
    cursor=connection.cursor.return_value.__enter__.return_value
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
    with patch('db.repositories.common.transaction',transaction):
        yield connection,cursor


def test_add_locks_parent_medication_then_exact_pair_and_commits(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[CONTEXT,{'idMedicament':2},None]
    repository.add_prescription(7,2,VALUES,context=CONTEXT)
    sql=[call.args[0] for call in cursor.execute.call_args_list]
    assert 'CONSULTATION' in sql[0] and 'FOR UPDATE' in sql[0]
    assert 'MEDICAMENT' in sql[1] and 'FOR SHARE' in sql[1]
    assert 'idConsultation=%s AND idMedicament=%s FOR UPDATE' in sql[2]
    assert cursor.execute.call_args.args[1]==(7,2,2,'Instructions fictives',3)
    assert VALUES['posologie'] not in sql[-1]
    connection.commit.assert_called_once()


def test_duplicate_pair_rejected_without_write(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[CONTEXT,{'idMedicament':2},ORIGINAL]
    with pytest.raises(repository.PrescriptionError,match='déjà prescrit'):
        repository.add_prescription(7,2,VALUES,context=CONTEXT)
    assert not any(call.args[0].startswith('INSERT') for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


@pytest.mark.parametrize('operation', ['update','remove'])
@pytest.mark.parametrize('current', [None,{**ORIGINAL,'duree':4}])
def test_missing_or_changed_pair_cannot_be_overwritten_or_removed(database,operation,current):
    connection,cursor=database
    cursor.fetchone.side_effect=[CONTEXT,{'idMedicament':2},current]
    method=getattr(repository,operation+'_prescription')
    with pytest.raises((repository.PrescriptionError,ConcurrentEditError)):
        if operation=='update':
            method(7,2,VALUES,original=ORIGINAL,context=CONTEXT)
        else:
            method(7,2,original=ORIGINAL,context=CONTEXT)
    assert not any(call.args[0].startswith(('UPDATE','DELETE')) for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


@pytest.mark.parametrize('operation', ['update','remove'])
def test_edit_and_removal_bind_both_key_columns(database,operation):
    connection,cursor=database
    cursor.fetchone.side_effect=[CONTEXT,{'idMedicament':2},ORIGINAL]
    if operation=='update':
        repository.update_prescription(7,2,VALUES,original=ORIGINAL,context=CONTEXT)
    else:
        repository.remove_prescription(7,2,original=ORIGINAL,context=CONTEXT)
    sql,params=cursor.execute.call_args.args
    assert 'WHERE idConsultation=%s AND idMedicament=%s' in sql
    assert params[-2:]==(7,2)
    assert not any('UPDATE MEDICAMENT' in call.args[0] for call in cursor.execute.call_args_list)
    connection.commit.assert_called_once()


@pytest.mark.parametrize('context', [None,{**CONTEXT,'idPatient':6},{**CONTEXT,'diagnostic':'Changed'}])
def test_stale_or_missing_consultation_blocks_all_writes(database,context):
    _,cursor=database
    cursor.fetchone.return_value=context
    with pytest.raises((repository.PrescriptionError,ConcurrentEditError)):
        repository.add_prescription(7,2,VALUES,context=CONTEXT)
    assert cursor.execute.call_count==1


@pytest.mark.parametrize('errno,message', [(1062,'déjà prescrit'),(1452,'plus disponible'),(3819,'positives'),(1048,'obligatoires'),(1264,'limites'),(9999,'MySQL impossible')])
def test_raw_mysql_constraint_errors_are_sanitized_and_rolled_back(database,errno,message,caplog):
    connection,cursor=database
    cursor.fetchone.side_effect=[CONTEXT,{'idMedicament':2},None]
    cursor.execute.side_effect=[None,None,None,mysql.connector.Error('private instructions',errno=errno)]
    with pytest.raises(RepositoryError,match=message) as caught:
        repository.add_prescription(7,2,VALUES,context=CONTEXT)
    assert 'private' not in str(caught.value) and 'private' not in caplog.text
    connection.rollback.assert_called_once()


def test_medication_filter_search_and_pagination_are_bound(database):
    _,cursor=database
    cursor.fetchone.return_value={'total':26}
    cursor.fetchall.return_value=[]
    needle="O'Neil %_"
    repository.list_medications(7,needle,form='Crème fictive',page=1)
    sql,params=cursor.execute.call_args.args
    assert needle not in sql and params==(7,needle,'Crème fictive',25,25)
    assert 'rx.idMedicament IS NULL' in sql


def test_consultation_filters_include_zero_medication_option(database):
    _,cursor=database
    cursor.fetchone.return_value={'total':1}
    cursor.fetchall.return_value=[]
    repository.list_consultations('fictif',doctor=5,patient=5,day=datetime(2026,11,5).date(),prescribed=False)
    sql,params=cursor.execute.call_args.args
    assert params==('fictif',5,5,datetime(2026,11,5),datetime(2026,11,6),False,25,0)
    assert 'EXISTS(SELECT 1 FROM PRESCRIRE' in sql


def test_context_and_prescriptions_share_one_snapshot(database):
    connection,cursor=database
    cursor.fetchone.return_value=CONTEXT
    cursor.fetchall.return_value=[]
    assert repository.consultation_detail(7)==dict(consultation=CONTEXT,prescriptions=[])
    assert all(call.args[1]==(7,) for call in cursor.execute.call_args_list)
    connection.start_transaction.assert_called_once()
