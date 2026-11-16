"""Real hospitalization intervals/concurrency using only cliniq_test_dev."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
import os
from threading import Barrier

import mysql.connector
import pytest

from db.connection import transaction
from db.repositories import hospitalization_repository as repository
from db.repositories.dashboard_repository import load_dashboard
from db.repositories.common import ConcurrentEditError
from services import hospitalization_service as service
from services.patient_service import ValidationError
from tests.mysql_support import reset_schema


BASE=datetime(2038,1,1,9)


@pytest.fixture
def hospital_database(request,monkeypatch):
    if os.getenv('CLINIQ_RUN_DEV006_MYSQL_TESTS')!='1':
        pytest.skip('Set CLINIQ_RUN_DEV006_MYSQL_TESTS=1 and explicitly confirm cliniq_test_dev reset')
    database=request.getfixturevalue('dedicated_mysql_database')
    # Isolate open-ended interval probes from other cases, under the module's
    # existing advisory lock and the same explicit target/reset safety checks.
    with database.connect() as connection:
        reset_schema(connection)
    def connect():
        connection=database.connect()
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION innodb_lock_wait_timeout=5')
        return connection
    monkeypatch.setattr('db.connection.get_connection',connect)
    return database


def stay(start=BASE,end=None,*,bed=3,patient=1):
    return dict(dateAdmission=start,dateSortie=end,idPatient=patient,idLit=bed)


def bed_ids(rows):
    return {row['idLit'] for row in rows}


def test_admit_read_edit_discharge_and_history_preserve_records(hospital_database):
    hid=service.save_hospitalization(stay())
    original=repository.get_hospitalization(hid,BASE)
    assert original['statut']=='En cours' and original['numeroChambre']=='102'
    assert hid in [row['idHospitalisation'] for row in repository.patient_history(1,BASE)]
    service.save_hospitalization({**original,'idLit':6},hospitalization_id=hid,original=original)
    moved=repository.get_hospitalization(hid,BASE)
    assert moved['idLit']==6 and moved['idPatient']==1
    service.record_discharge(hid,BASE+timedelta(days=1),original=moved)
    closed=repository.get_hospitalization(hid,BASE+timedelta(days=1))
    assert closed['statut']=='Terminée' and closed['dateSortie']==BASE+timedelta(days=1)
    assert repository.list_hospitalizations(BASE+timedelta(days=1),patient=1)['total']==2


@pytest.mark.parametrize('offset,duration,allowed',[(-2,1,True),(-1,1,True),(1,1,True),(-1,2,False),(0,1,False),(0,2,False),(0.5,0.25,False)])
def test_completed_stay_conflict_boundaries(hospital_database,offset,duration,allowed):
    service.save_hospitalization(stay(BASE,BASE+timedelta(days=1)))
    start=BASE+timedelta(days=offset)
    values=stay(start,start+timedelta(days=duration),patient=2)
    available=bed_ids(service.available_beds(values['dateAdmission'],values['dateSortie']))
    assert (3 in available)==allowed
    if allowed:
        assert service.save_hospitalization(values)
    else:
        with pytest.raises(repository.HospitalizationError,match='occupé'):
            service.save_hospitalization(values)
    assert service.save_hospitalization({**values,'idLit':6})


def test_open_ended_stays_block_all_later_periods_and_ignore_ended_history(hospital_database):
    # Seed bed 1 has BOTH a discharged historic stay and an ongoing later stay.
    assert 1 not in bed_ids(service.available_beds(datetime(2026,11,7),datetime(2026,11,8)))
    service.save_hospitalization(stay())
    for values in (stay(BASE+timedelta(days=100),BASE+timedelta(days=101),patient=2),
                   stay(BASE-timedelta(days=1),None,patient=2)):
        assert 3 not in bed_ids(service.available_beds(values['dateAdmission'],values['dateSortie']))
        with pytest.raises(repository.HospitalizationError,match='occupé'):
            service.save_hospitalization(values)


def test_future_reservation_blocks_open_candidate_even_when_bed_available_now(hospital_database):
    service.save_hospitalization(stay(BASE+timedelta(days=3),BASE+timedelta(days=4)))
    data=repository.occupancy(BASE)
    assert next(row for row in data['beds'] if row['idLit']==3)['occupied']==0
    assert 3 not in bed_ids(service.available_beds(BASE,None))
    assert 3 in bed_ids(service.available_beds(BASE,BASE+timedelta(days=3)))
    with pytest.raises(repository.HospitalizationError):
        service.save_hospitalization(stay(BASE,None,patient=2))


def test_empty_intervals_are_valid_and_never_occupy_or_block(hospital_database):
    # The approved CHECK explicitly permits admission == discharge.
    zero=service.save_hospitalization(stay(BASE,BASE,bed=1))
    assert repository.get_hospitalization(zero,BASE)['statut']=='Terminée'
    service.save_hospitalization(stay(BASE,BASE))
    assert 3 in bed_ids(service.available_beds(BASE-timedelta(hours=1),BASE+timedelta(hours=1)))
    service.save_hospitalization(stay(BASE-timedelta(hours=1),BASE+timedelta(hours=1),patient=2))
    assert 3 in bed_ids(service.available_beds(BASE,BASE))
    assert next(row for row in repository.occupancy(BASE)['beds'] if row['idLit']==3)['occupied']==1


def test_occupancy_matches_dashboard_and_excludes_future_and_exact_discharge(hospital_database):
    service.save_hospitalization(stay(BASE,BASE+timedelta(hours=1)))
    service.save_hospitalization(stay(BASE+timedelta(days=1),None,bed=6,patient=2))
    for instant,occupied in [(BASE-timedelta(seconds=1),2),(BASE,3),(BASE+timedelta(hours=1),2)]:
        data=repository.occupancy(instant)
        metrics=load_dashboard(instant)['metrics']
        assert sum(row['occupied'] for row in data['rooms'])==occupied==metrics['occupied_beds']
        assert sum(row['available'] for row in data['rooms'])==7-occupied==metrics['available_beds']
    assert repository.get_hospitalization(7,BASE)['statut']=='Prévue'


def test_reopen_extend_and_bed_move_recheck_full_intervals(hospital_database):
    hid=service.save_hospitalization(stay(BASE,BASE+timedelta(days=1)))
    service.save_hospitalization(stay(BASE+timedelta(days=2),None,patient=2))
    original=repository.get_hospitalization(hid,BASE)
    for end in (None,BASE+timedelta(days=3)):
        with pytest.raises(repository.HospitalizationError,match='occupé'):
            service.save_hospitalization({**original,'dateSortie':end},hospitalization_id=hid,original=original)
    service.save_hospitalization(stay(BASE,BASE+timedelta(days=1),bed=6,patient=2))
    with pytest.raises(repository.HospitalizationError,match='occupé'):
        service.save_hospitalization({**original,'idLit':6},hospitalization_id=hid,original=original)
    assert repository.get_hospitalization(hid,BASE)['idLit']==3


def test_stale_edits_and_discharges_fail_and_patient_is_fixed(hospital_database):
    hid=service.save_hospitalization(stay())
    original=repository.get_hospitalization(hid,BASE)
    service.record_discharge(hid,BASE+timedelta(days=1),original=original)
    with pytest.raises(ConcurrentEditError):
        service.record_discharge(hid,BASE+timedelta(days=2),original=original)
    with pytest.raises(ConcurrentEditError):
        service.save_hospitalization(original,hospitalization_id=hid,original=original)
    current=repository.get_hospitalization(hid,BASE)
    with pytest.raises(repository.HospitalizationError,match='patient'):
        service.save_hospitalization({**current,'idPatient':2},hospitalization_id=hid,original=current)
    assert repository.get_hospitalization(hid,BASE)['dateSortie']==BASE+timedelta(days=1)


def test_invalid_dates_checked_by_service_and_mysql_with_no_insert(hospital_database):
    values=stay(BASE,BASE-timedelta(seconds=1))
    with pytest.raises(ValidationError):
        service.save_hospitalization(values)
    with pytest.raises(repository.HospitalizationError,match='précéder'):
        repository.save_hospitalization(values)
    assert repository.list_hospitalizations(BASE)['total']==5


@pytest.mark.parametrize('field,value',[('idPatient',999999),('idLit',999999)])
def test_existing_parent_records_are_required(hospital_database,field,value):
    with pytest.raises(repository.HospitalizationError,match='plus disponible'):
        service.save_hospitalization({**stay(),field:value})
    assert repository.list_hospitalizations(BASE)['total']==5


def test_search_admission_period_status_room_and_patient_filters(hospital_database):
    hid=service.save_hospitalization(stay())
    params=dict(patient=1,room=2,from_day=BASE.date(),to_day=BASE.date())
    rows=repository.list_hospitalizations(BASE,'Demo-Alami',status='En cours',**params)['rows']
    assert [row['idHospitalisation'] for row in rows]==[hid]
    assert repository.list_hospitalizations(BASE-timedelta(seconds=1),status='Prévue',**params)['total']==1
    assert repository.list_hospitalizations(BASE,status='Terminée',**params)['total']==0
    assert repository.list_hospitalizations(BASE,"' OR 1=1 --")['total']==0
    assert all(row['idChambre']==2 for row in service.available_beds(BASE,BASE,room=2))


def test_updates_preserve_linked_medical_act_associations(hospital_database):
    with hospital_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=%s ORDER BY idActe',(4,))
            original_links=cursor.fetchall()
    original=repository.get_hospitalization(4,BASE)
    service.record_discharge(4,datetime(2026,11,6),original=original)
    with hospital_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM DESIGNER_RESPONSABLE WHERE idHospitalisation=%s ORDER BY idActe',(4,))
            assert cursor.fetchall()==original_links


def race(operation):
    barrier=Barrier(2)
    def contender(index):
        barrier.wait(timeout=5)
        try:
            operation(index)
            return 'saved'
        except (repository.HospitalizationError,ConcurrentEditError):
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(contender,index) for index in (1,2)]
        return sorted(job.result(timeout=15) for job in jobs)


def test_concurrent_first_admissions_same_bed_have_one_winner(hospital_database):
    assert race(lambda index:service.save_hospitalization(stay(patient=index)))==['rejected','saved']
    assert repository.list_hospitalizations(BASE,room=2)['total']==2  # one seed + one new


def test_concurrent_nonoverlapping_reuse_and_different_beds_can_both_succeed(hospital_database):
    assert race(lambda index:service.save_hospitalization(stay(BASE+timedelta(days=index-1),BASE+timedelta(days=index),patient=index)))==['saved','saved']
    assert race(lambda index:service.save_hospitalization(stay(BASE+timedelta(days=10),BASE+timedelta(days=11),bed=6 if index==1 else 7,patient=index)))==['saved','saved']


def test_concurrent_stale_edits_have_one_winner(hospital_database):
    hid=service.save_hospitalization(stay())
    original=repository.get_hospitalization(hid,BASE)
    assert race(lambda index:service.record_discharge(hid,BASE+timedelta(days=index),original=original))==['rejected','saved']


def test_successful_update_is_rolled_back_if_later_statement_fails(hospital_database):
    hid=service.save_hospitalization(stay())
    with pytest.raises(mysql.connector.Error):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE HOSPITALISATION SET dateSortie=%s WHERE idHospitalisation=%s',(BASE+timedelta(days=1),hid))
                cursor.execute('INSERT INTO EXERCER VALUES (%s,%s)',(1,1))
    assert repository.get_hospitalization(hid,BASE)['dateSortie'] is None
