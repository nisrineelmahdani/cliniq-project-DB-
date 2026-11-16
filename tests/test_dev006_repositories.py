"""Parent locks, current interval reads, bound SQL and rollback guarantees."""

from contextlib import contextmanager
from datetime import datetime
from unittest.mock import MagicMock,patch

import mysql.connector
import pytest

from db.repositories import hospitalization_repository as repository
from db.repositories.common import ConcurrentEditError,RepositoryError
from tests.test_dev006_services import VALUES,ORIGINAL


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


def test_new_admission_locks_bed_before_current_overlap_read(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},{'idPatient':1},None]
    cursor.lastrowid=8
    assert repository.save_hospitalization(VALUES)==8
    calls=cursor.execute.call_args_list
    assert 'LIT' in calls[0].args[0] and 'FOR UPDATE' in calls[0].args[0]
    assert 'FOR UPDATE' in calls[2].args[0] and 'h.dateSortie>h.dateAdmission' in calls[2].args[0]
    assert calls[2].args[1]==(3,0,None,None,VALUES['dateAdmission'])
    assert calls[3].args[1]==(VALUES['dateAdmission'],None,1,3)
    connection.commit.assert_called_once()
    connection.start_transaction.assert_called_once_with(isolation_level='READ COMMITTED')


def test_conflict_rejects_without_inserting(database):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},{'idPatient':1},{'idHospitalisation':99}]
    with pytest.raises(repository.HospitalizationError,match='occupé'):
        repository.save_hospitalization(VALUES)
    assert not any(call.args[0].startswith('INSERT') for call in cursor.execute.call_args_list)
    connection.rollback.assert_called_once()


def test_bed_correction_locks_old_and_new_beds_in_order_then_stay(database):
    _,cursor=database
    original={**ORIGINAL,'idLit':5}
    cursor.fetchone.side_effect=[{'idLit':3},{'idLit':5},original,{'idPatient':1},None]
    repository.save_hospitalization(VALUES,hospitalization_id=8,original=original)
    calls=cursor.execute.call_args_list
    assert [call.args[1][0] for call in calls[:3]]==[3,5,8]
    assert all('FOR UPDATE' in call.args[0] for call in calls[:3])
    assert calls[4].args[1][1]==8


@pytest.mark.parametrize('current',[None,{**ORIGINAL,'dateSortie':datetime(2038,1,2)}])
def test_missing_or_stale_record_is_not_updated(database,current):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},current]
    with pytest.raises((repository.HospitalizationError,ConcurrentEditError)):
        repository.save_hospitalization(VALUES,hospitalization_id=8,original=ORIGINAL)
    connection.rollback.assert_called_once()


def test_existing_stay_patient_is_immutable(database):
    _,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},ORIGINAL]
    with pytest.raises(repository.HospitalizationError,match='patient'):
        repository.save_hospitalization({**VALUES,'idPatient':2},hospitalization_id=8,original=ORIGINAL)


def test_zero_length_interval_does_not_reserve_a_bed(database):
    _,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},{'idPatient':1}]
    repository.save_hospitalization({**VALUES,'dateSortie':VALUES['dateAdmission']})
    assert not any('LIMIT 1 FOR UPDATE' in call.args[0] for call in cursor.execute.call_args_list)


def test_availability_examines_all_stays_with_exclusion_and_bound_room(database):
    _,cursor=database
    cursor.fetchall.return_value=[]
    repository.available_beds(VALUES['dateAdmission'],None,room=2,exclude_id=8)
    sql,params=cursor.execute.call_args.args
    assert 'NOT EXISTS' in sql and 'h.dateSortie>h.dateAdmission' in sql
    assert params==(2,2,8,None,None,VALUES['dateAdmission'])


def test_occupancy_uses_same_date_predicate_for_rooms_and_beds(database):
    connection,cursor=database
    cursor.fetchall.side_effect=[[],[]]
    now=datetime(2038,1,1,12)
    repository.occupancy(now)
    assert all('h.dateAdmission<=%s AND (h.dateSortie IS NULL OR h.dateSortie>%s)' in call.args[0] for call in cursor.execute.call_args_list)
    assert all(call.args[1]==(now,now,None,None) for call in cursor.execute.call_args_list)
    connection.start_transaction.assert_called_once()


def test_search_filters_are_parameterized(database):
    _,cursor=database
    cursor.fetchone.return_value={'total':1}
    cursor.fetchall.return_value=[]
    needle="O'Neil %_"
    now=datetime(2038,1,1,12)
    repository.list_hospitalizations(now,needle,patient=1,room=2,status='En cours',from_day=now.date(),to_day=now.date())
    sql,params=cursor.execute.call_args.args
    assert needle not in sql
    assert params[:5]==(now,now,needle,1,2)
    assert params[-3:]==('En cours',25,0)


@pytest.mark.parametrize('errno,message',[(1452,'plus disponible'),(3819,'précéder'),(9999,'MySQL impossible')])
def test_mysql_errors_are_safe_and_roll_back(database,errno,message,caplog):
    connection,cursor=database
    cursor.fetchone.side_effect=[{'idLit':3},{'idPatient':1},None]
    cursor.execute.side_effect=[None,None,None,mysql.connector.Error('private patient information',errno=errno)]
    with pytest.raises(RepositoryError,match=message) as caught:
        repository.save_hospitalization(VALUES)
    assert 'private' not in str(caught.value) and 'private' not in caplog.text
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()
