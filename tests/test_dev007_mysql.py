"""Actual ternary CIF and concurrent assignments in protected cliniq_test_dev."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta
import os
from threading import Barrier

import mysql.connector
import pytest

from db.connection import transaction
from db.repositories import medical_act_repository as repository
from db.repositories.common import ConcurrentEditError
from services import medical_act_service as service
from services.hospitalization_service import save_hospitalization,record_discharge
from services.patient_service import ValidationError
from tests.mysql_support import reset_schema


BASE=datetime(2080,1,1,9)


@pytest.fixture
def medical_database(request,monkeypatch):
    if os.getenv('CLINIQ_RUN_DEV007_MYSQL_TESTS')!='1':
        pytest.skip('Set CLINIQ_RUN_DEV007_MYSQL_TESTS=1 and explicitly confirm cliniq_test_dev reset')
    database=request.getfixturevalue('dedicated_mysql_database')
    with database.connect() as connection:
        reset_schema(connection)
    def connect():
        connection=database.connect()
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION innodb_lock_wait_timeout=5')
        return connection
    monkeypatch.setattr('db.connection.get_connection',connect)
    return database


def new_context(*,bed=7,patient=1):
    hid=save_hospitalization(dict(dateAdmission=BASE,dateSortie=BASE+timedelta(days=1),idPatient=patient,idLit=bed))
    return repository.hospitalization_detail(hid)['hospitalization']


@pytest.fixture
def context(medical_database):
    return new_context()


def rows(context):
    return repository.hospitalization_detail(context['idHospitalisation'])['assignments']


def test_database_pk_is_exact_pair_doctor_mandatory_and_three_foreign_keys(medical_database):
    with medical_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("""SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE()
                AND TABLE_NAME='DESIGNER_RESPONSABLE' AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION""")
            assert cursor.fetchall()==[('idHospitalisation',),('idActe',)]
            cursor.execute("""SELECT IS_NULLABLE FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE()
                AND TABLE_NAME='DESIGNER_RESPONSABLE' AND COLUMN_NAME='idMedecin'""")
            assert cursor.fetchone()[0]=='NO'
            cursor.execute("""SELECT COLUMN_NAME,REFERENCED_TABLE_NAME FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='DESIGNER_RESPONSABLE' AND REFERENCED_TABLE_NAME IS NOT NULL""")
            assert set(cursor.fetchall())=={('idHospitalisation','HOSPITALISATION'),('idActe','ACTE_MEDICAL'),('idMedecin','MEDECIN')}


def test_zero_multiple_acts_same_doctor_and_cross_hospitalization_reuse(context,medical_database):
    assert rows(context)==[]
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    service.add_assignment(hid,2,1,context=context)
    other=new_context(bed=6,patient=2)
    service.add_assignment(other['idHospitalisation'],1,1,context=other)
    assert {(row['idActe'],row['idMedecin']) for row in rows(context)}=={(1,1),(2,1)}
    assert len(rows(other))==1
    assert repository.list_assignments(patient=1,hospitalization=hid,act=2,doctor=1)['total']==1
    assert repository.list_assignments("' OR 1=1 --")['total']==0
    assert any(row['idHospitalisation']==hid for row in repository.hospitalizations(patient=1))
    assert repository.list_acts('offert')['rows'][0]['cout']==0


def test_duplicate_different_doctor_rejected_by_service_and_mysql(context,medical_database):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    with pytest.raises(repository.CIFViolationError,match='CIF'):
        service.add_assignment(hid,1,2,context=context)
    connection=medical_database.connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                cursor.execute('INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)',(hid,1,2))
            assert caught.value.errno==1062
    finally:
        connection.rollback()
        connection.close()
    assert len(rows(context))==1 and rows(context)[0]['idMedecin']==1


def test_reassignment_updates_existing_row_without_creating_an_execution(context,medical_database):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    original=rows(context)[0]
    service.reassign(hid,1,2,original=original,context=context)
    updated=rows(context)[0]
    assert (updated['idHospitalisation'],updated['idActe'],updated['idMedecin'])==(hid,1,2)
    assert len(rows(context))==1
    # Reassigning to the already responsible doctor is a safe no-op.
    service.reassign(hid,1,2,original=updated,context=context)
    with medical_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')
            assert cursor.fetchone()[0]==15


def test_confirmed_removal_preserves_other_pairs_and_parent_records(context,medical_database):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    service.add_assignment(hid,2,1,context=context)
    original=rows(context)[0]
    original=next(row for row in rows(context) if row['idActe']==1)
    with pytest.raises(ValidationError):
        service.remove_assignment(hid,1,original=original,context=context)
    assert len(rows(context))==2
    service.remove_assignment(hid,1,original=original,context=context,confirmed=True)
    assert [row['idActe'] for row in rows(context)]==[2]
    assert repository.hospitalization_detail(hid)['hospitalization']['idHospitalisation']==hid
    with medical_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM ACTE_MEDICAL')
            assert cursor.fetchone()[0]==5
            cursor.execute('SELECT COUNT(*) FROM MEDECIN')
            assert cursor.fetchone()[0]==5


def test_stale_reassignment_and_removal_leave_current_doctor_intact(context):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    original=rows(context)[0]
    service.reassign(hid,1,2,original=original,context=context)
    with pytest.raises(ConcurrentEditError):
        service.reassign(hid,1,3,original=original,context=context)
    with pytest.raises(ConcurrentEditError):
        service.remove_assignment(hid,1,original=original,context=context,confirmed=True)
    assert rows(context)[0]['idMedecin']==2
    current=rows(context)[0]
    service.remove_assignment(hid,1,original=current,context=context,confirmed=True)
    with pytest.raises(repository.AssignmentError,match='existe plus'):
        service.reassign(hid,1,3,original=current,context=context)


@pytest.mark.parametrize('missing',['hospitalization','act','doctor'])
def test_each_foreign_key_rejects_missing_parent_and_service_is_actionable(context,medical_database,missing):
    hid=context['idHospitalisation'] if missing!='hospitalization' else 999999
    act=999999 if missing=='act' else 1
    doctor=999999 if missing=='doctor' else 1
    with pytest.raises(repository.AssignmentError,match='plus disponible'):
        service.add_assignment(hid,act,doctor,context={**context,'idHospitalisation':hid})
    connection=medical_database.connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                cursor.execute('INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)',(hid,act,doctor))
            assert caught.value.errno==1452
    finally:
        connection.rollback()
        connection.close()


def test_mysql_rejects_null_responsible_doctor(context,medical_database):
    connection=medical_database.connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                cursor.execute('INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)',(context['idHospitalisation'],1,None))
            assert caught.value.errno==1048
    finally:
        connection.rollback()
        connection.close()


@pytest.mark.parametrize('operation',['add','reassign','remove'])
def test_changed_stay_context_blocks_mutation(context,operation):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    original=rows(context)[0]
    record_discharge(hid,BASE+timedelta(days=2),original=context)
    with pytest.raises(ConcurrentEditError,match='séjour a changé'):
        if operation=='add':
            service.add_assignment(hid,2,1,context=context)
        elif operation=='reassign':
            service.reassign(hid,1,2,original=original,context=context)
        else:
            service.remove_assignment(hid,1,original=original,context=context,confirmed=True)
    assert len(rows(context))==1 and rows(context)[0]['idMedecin']==1


def race(operation):
    barrier=Barrier(2)
    def contender(index):
        barrier.wait(timeout=5)
        try:
            operation(index)
            return 'saved'
        except (repository.AssignmentError,ConcurrentEditError):
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(contender,index) for index in (1,2)]
        return sorted(job.result(timeout=15) for job in jobs)


def test_concurrent_pair_assignments_have_one_responsible_doctor(context):
    hid=context['idHospitalisation']
    assert race(lambda index:service.add_assignment(hid,1,index,context=context))==['rejected','saved']
    assert len(rows(context))==1


def test_same_doctor_can_concurrently_accept_independent_stays(context):
    other=new_context(bed=6,patient=2)
    contexts={1:context,2:other}
    assert race(lambda index:service.add_assignment(contexts[index]['idHospitalisation'],1,1,context=contexts[index]))==['saved','saved']
    assert len(rows(context))==len(rows(other))==1


def test_concurrent_reassignments_and_remove_vs_update_are_stale_safe(context):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    original=rows(context)[0]
    assert race(lambda index:service.reassign(hid,1,index+1,original=original,context=context))==['rejected','saved']
    original=rows(context)[0]
    def update_or_remove(index):
        if index==1:
            service.reassign(hid,1,4,original=original,context=context)
        else:
            service.remove_assignment(hid,1,original=original,context=context,confirmed=True)
    assert race(update_or_remove)==['rejected','saved']
    assert len(rows(context))<=1


def test_successful_reassignment_rolls_back_when_later_statement_fails(context):
    hid=context['idHospitalisation']
    service.add_assignment(hid,1,1,context=context)
    with pytest.raises(mysql.connector.Error):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE DESIGNER_RESPONSABLE SET idMedecin=%s WHERE idHospitalisation=%s AND idActe=%s',(2,hid,1))
                cursor.execute('INSERT INTO DESIGNER_RESPONSABLE VALUES (%s,%s,%s)',(hid,1,3))
    assert rows(context)[0]['idMedecin']==1
