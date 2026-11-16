"""Real prescription association workflows, confined to cliniq_test_dev."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import os
from threading import Barrier

import mysql.connector
import pytest

from db.connection import transaction
from db.repositories import prescription_repository as repository
from db.repositories.common import ConcurrentEditError, RepositoryError
from services import prescription_service as service
from services.consultation_service import save_consultation
from services.patient_service import ValidationError


VALUES=dict(quantite=2,posologie='DEV005 instructions fictives',duree=3)


@pytest.fixture
def rx_database(request,monkeypatch):
    if os.getenv('CLINIQ_RUN_DEV005_MYSQL_TESTS')!='1':
        pytest.skip('Set CLINIQ_RUN_DEV005_MYSQL_TESTS=1 and explicitly confirm cliniq_test_dev reset')
    database=request.getfixturevalue('dedicated_mysql_database')
    def connect():
        connection=database.connect()
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION innodb_lock_wait_timeout=5')
        return connection
    monkeypatch.setattr('db.connection.get_connection',connect)
    return database


def new_context():
    consultation_id=save_consultation(dict(dateHeure=datetime(2037,1,1,9),motif='DEV005 scénario fictif',
        diagnostic='DEV005 diagnostic fictif',idPatient=1,idMedecin=1,idRDV=None,idSalle=None))
    return repository.consultation_detail(consultation_id)['consultation']


@pytest.fixture
def context(rx_database):
    return new_context()


def prescriptions(context):
    return repository.consultation_detail(context['idConsultation'])['prescriptions']


def test_zero_multiple_medications_and_independent_consultations(context,rx_database):
    assert prescriptions(context)==[]
    with rx_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM MEDICAMENT ORDER BY idMedicament')
            catalog_before=cursor.fetchall()
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    service.add_prescription(cid,2,VALUES,context=context)
    assert {row['idMedicament'] for row in prescriptions(context)}=={1,2}
    other=new_context()
    service.add_prescription(other['idConsultation'],1,VALUES,context=other)
    original=next(row for row in prescriptions(context) if row['idMedicament']==1)
    updated={**VALUES,'quantite':5,'posologie':'DEV005 instructions modifiées','duree':7}
    service.update_prescription(cid,1,updated,original=original,context=context)
    persisted=next(row for row in prescriptions(context) if row['idMedicament']==1)
    assert all(persisted[key]==updated[key] for key in repository.FIELDS)
    with pytest.raises(ValidationError):
        service.remove_prescription(cid,1,original=persisted,context=context,confirmed=False)
    assert len(prescriptions(context))==2
    service.remove_prescription(cid,1,original=persisted,context=context,confirmed=True)
    assert [row['idMedicament'] for row in prescriptions(context)]==[2]
    assert [row['idMedicament'] for row in prescriptions(other)]==[1]
    with rx_database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT * FROM MEDICAMENT ORDER BY idMedicament')
            assert cursor.fetchall()==catalog_before


def test_duplicate_rejected_by_service_and_mysql_composite_pk(context,rx_database):
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    with pytest.raises(repository.PrescriptionError,match='déjà prescrit'):
        service.add_prescription(cid,1,VALUES,context=context)
    connection=rx_database.connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                cursor.execute('INSERT INTO PRESCRIRE VALUES (%s,%s,%s,%s,%s)',(cid,1,1,'Démo',1))
            assert caught.value.errno==1062
    finally:
        connection.rollback()
        connection.close()
    assert len(prescriptions(context))==1


@pytest.mark.parametrize('field,value',[('quantite',0),('duree',0)])
def test_mysql_check_rejection_is_actionable_and_rolls_back(context,field,value):
    with pytest.raises(repository.PrescriptionError,match='positives'):
        repository.add_prescription(context['idConsultation'],1,{**VALUES,field:value},context=context)
    assert prescriptions(context)==[]


def test_unsigned_numeric_and_unicode_character_boundaries(context):
    values=dict(quantite=4294967295,duree=65535,posologie='é'*255)
    service.add_prescription(context['idConsultation'],1,values,context=context)
    assert all(prescriptions(context)[0][key]==value for key,value in values.items())


def test_edit_and_remove_stale_snapshots_and_missing_pair(context):
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    original=prescriptions(context)[0]
    service.update_prescription(cid,1,{**VALUES,'quantite':3},original=original,context=context)
    with pytest.raises(ConcurrentEditError):
        service.update_prescription(cid,1,VALUES,original=original,context=context)
    with pytest.raises(ConcurrentEditError):
        service.remove_prescription(cid,1,original=original,context=context,confirmed=True)
    current=prescriptions(context)[0]
    assert current['quantite']==3
    service.remove_prescription(cid,1,original=current,context=context,confirmed=True)
    with pytest.raises(repository.PrescriptionError,match='plus prescrit'):
        service.update_prescription(cid,1,VALUES,original=current,context=context)


@pytest.mark.parametrize('operation',['add','update','remove'])
def test_changed_consultation_context_blocks_writes(context,operation):
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    original=prescriptions(context)[0]
    save_consultation({**context,'diagnostic':'DEV005 contexte modifié'},consultation_id=cid,original=context)
    with pytest.raises(ConcurrentEditError,match='consultation a changé'):
        if operation=='add':
            service.add_prescription(cid,2,VALUES,context=context)
        elif operation=='update':
            service.update_prescription(cid,1,{**VALUES,'quantite':3},original=original,context=context)
        else:
            service.remove_prescription(cid,1,original=original,context=context,confirmed=True)
    assert len(prescriptions(context))==1 and prescriptions(context)[0]['quantite']==2


def test_search_filters_and_available_medications(context):
    cid=context['idConsultation']
    assert repository.list_consultations('DEV005',patient=1,doctor=1,day=context['dateHeure'].date(),prescribed=False)['total']>0
    service.add_prescription(cid,1,VALUES,context=context)
    listed=repository.list_consultations('DEV005',prescribed=True)
    assert cid in [row['idConsultation'] for row in listed['rows']]
    assert 1 not in [row['idMedicament'] for row in repository.list_medications(cid)['rows']]
    assert 1 in [row['idMedicament'] for row in repository.list_medications(cid,available_only=False)['rows']]
    assert repository.list_medications(cid,'DemoCalm',available_only=False)['total']==1
    assert repository.list_medications(cid,form='Crème fictive')['total']==1
    assert repository.list_medications(cid,"' OR 1=1 --",available_only=False)['total']==0


@pytest.mark.parametrize('missing',['consultation','medication'])
def test_foreign_keys_and_missing_parent_feedback(context,rx_database,missing):
    cid=context['idConsultation'] if missing=='medication' else 999999
    mid=999999 if missing=='medication' else 1
    expected={**context,'idConsultation':cid}
    with pytest.raises(repository.PrescriptionError,match='plus disponible'):
        service.add_prescription(cid,mid,VALUES,context=expected)
    connection=rx_database.connect()
    try:
        with connection.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                cursor.execute('INSERT INTO PRESCRIRE VALUES (%s,%s,%s,%s,%s)',(cid,mid,1,'Démo',1))
            assert caught.value.errno==1452
    finally:
        connection.rollback()
        connection.close()


def test_failed_multi_statement_transaction_rolls_back_successful_update(context):
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    with pytest.raises(mysql.connector.Error):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE PRESCRIRE SET quantite=%s WHERE idConsultation=%s AND idMedicament=%s',(99,cid,1))
                cursor.execute('INSERT INTO PRESCRIRE VALUES (%s,%s,%s,%s,%s)',(cid,1,1,'Démo',1))
    assert prescriptions(context)[0]['quantite']==2


def race(operation):
    barrier=Barrier(2)
    def contender(index):
        barrier.wait(timeout=5)
        try:
            operation(index)
            return 'saved'
        except RepositoryError:
            return 'rejected'
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs=[pool.submit(contender,index) for index in (1,2)]
        return sorted(job.result(timeout=15) for job in jobs)


def test_concurrent_duplicate_add_has_one_winner(context):
    result=race(lambda index: service.add_prescription(context['idConsultation'],1,VALUES,context=context))
    assert result==['rejected','saved'] and len(prescriptions(context))==1


def test_concurrent_stale_edits_have_one_winner(context):
    cid=context['idConsultation']
    service.add_prescription(cid,1,VALUES,context=context)
    original=prescriptions(context)[0]
    result=race(lambda index: service.update_prescription(cid,1,{**VALUES,'quantite':index+2},original=original,context=context))
    assert result==['rejected','saved']
    assert prescriptions(context)[0]['quantite'] in (3,4)
