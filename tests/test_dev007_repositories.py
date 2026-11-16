"""Lock ordering, bound keys, CIF feedback and rollback without raw values."""

from contextlib import contextmanager
from unittest.mock import MagicMock,patch

import mysql.connector
import pytest

from db.repositories import medical_act_repository as repository
from db.repositories.common import ConcurrentEditError,RepositoryError
from tests.test_dev007_services import CONTEXT,ORIGINAL


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


def test_creation_locks_parents_before_pair_and_uses_exact_three_columns(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idMedecin':1},CONTEXT,{'idActe':2},None]
    repository.add_assignment(4,2,1,context=CONTEXT)
    calls=cursor.execute.call_args_list
    assert 'MEDECIN' in calls[0].args[0] and 'FOR SHARE' in calls[0].args[0]
    assert 'HOSPITALISATION' in calls[1].args[0] and 'FOR UPDATE' in calls[1].args[0]
    assert 'ACTE_MEDICAL' in calls[2].args[0] and 'FOR SHARE' in calls[2].args[0]
    assert calls[3].args[1]==(4,2) and 'FOR UPDATE' in calls[3].args[0]
    assert calls[4].args[1]==(4,2,1)
    connection.start_transaction.assert_called_once_with(isolation_level='READ COMMITTED')
    connection.commit.assert_called_once()


def test_duplicate_pair_with_different_doctor_is_cif_violation(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idMedecin':2},CONTEXT,{'idActe':2},ORIGINAL]
    with pytest.raises(repository.CIFViolationError,match='clé primaire'):
        repository.add_assignment(4,2,2,context=CONTEXT)
    assert not any(call.args[0].startswith('INSERT') for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


def test_reassign_updates_only_doctor_and_orders_shared_doctor_locks(database):
    connection,cursor=database
    original={**ORIGINAL,'idMedecin':3}
    cursor.fetchone.side_effect=[{'idMedecin':1},{'idMedecin':3},CONTEXT,{'idActe':2},original]
    repository.reassign(4,2,1,original=original,context=CONTEXT)
    calls=cursor.execute.call_args_list
    assert [call.args[1][0] for call in calls[:2]]==[1,3]
    assert calls[-1].args==('UPDATE DESIGNER_RESPONSABLE SET idMedecin=%s WHERE idHospitalisation=%s AND idActe=%s',(1,4,2))
    assert not any(call.args[0].startswith(('INSERT','DELETE')) for call in calls)
    connection.commit.assert_called_once()


@pytest.mark.parametrize('operation',['reassign','remove'])
@pytest.mark.parametrize('current',[None,{**ORIGINAL,'idMedecin':3}])
def test_missing_and_stale_pairs_never_change(database,operation,current):
    connection,cursor=database
    responses=[{'idMedecin':1}]
    if operation=='reassign':
        responses.append({'idMedecin':2})
    cursor.fetchone.side_effect=[*responses,CONTEXT,{'idActe':2},current]
    with pytest.raises((repository.AssignmentError,ConcurrentEditError)):
        if operation=='reassign':
            repository.reassign(4,2,2,original=ORIGINAL,context=CONTEXT)
        else:
            repository.remove_assignment(4,2,original=ORIGINAL,context=CONTEXT)
    connection.rollback.assert_called_once()
    assert not any(call.args[0].startswith(('UPDATE','DELETE')) for call in cursor.execute.call_args_list)


def test_remove_binds_both_composite_key_columns(database):
    _,cursor=database
    cursor.fetchone.side_effect=[{'idMedecin':1},CONTEXT,{'idActe':2},ORIGINAL]
    repository.remove_assignment(4,2,original=ORIGINAL,context=CONTEXT)
    assert cursor.execute.call_args.args==('DELETE FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=%s AND idActe=%s',(4,2))


@pytest.mark.parametrize('responses',[[None],[{'idMedecin':1},None],[{'idMedecin':1},CONTEXT,None]])
def test_missing_foreign_key_parents_are_actionable(database,responses):
    _,cursor=database
    cursor.fetchone.side_effect=responses
    with pytest.raises(repository.AssignmentError,match='plus disponible'):
        repository.add_assignment(4,2,1,context=CONTEXT)


def test_stay_change_rejected_before_pair_write(database):
    _,cursor=database
    cursor.fetchone.side_effect=[{'idMedecin':1},{**CONTEXT,'idLit':6}]
    with pytest.raises(ConcurrentEditError,match='séjour a changé'):
        repository.add_assignment(4,2,1,context=CONTEXT)
    assert cursor.execute.call_count==2


@pytest.mark.parametrize('errno,message',[(1062,'CIF'),(1452,'plus disponible'),(1048,'obligatoires'),(9999,'MySQL impossible')])
def test_mysql_rejections_sanitized_and_rolled_back(database,errno,message,caplog):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idMedecin':1},CONTEXT,{'idActe':2},None]
    cursor.execute.side_effect=[None,None,None,None,mysql.connector.Error('private patient details',errno=errno)]
    with pytest.raises(RepositoryError,match=message) as caught:
        repository.add_assignment(4,2,1,context=CONTEXT)
    assert 'private' not in str(caught.value) and 'private' not in caplog.text
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_filters_and_search_are_bound_and_doctor_never_part_of_row_identity(database):
    _,cursor=database
    cursor.fetchone.return_value={'total':1}
    cursor.fetchall.return_value=[]
    needle="O'Neil %_"
    repository.list_assignments(needle,patient=5,hospitalization=4,act=2,doctor=1)
    sql,params=cursor.execute.call_args.args
    assert needle not in sql and params==(needle,5,4,2,1,25,0)


def test_readonly_stay_view_preserves_zero_assignments(database):
    connection,cursor=database
    cursor.fetchone.return_value=CONTEXT
    cursor.fetchall.return_value=[]
    assert repository.hospitalization_detail(4)==dict(hospitalization=CONTEXT,assignments=[])
    assert all(call.args[1]==(4,) for call in cursor.execute.call_args_list)
    connection.start_transaction.assert_called_once()
