"""Direct SQL enforcement, current-read concurrency, query correctness and indexes."""

from concurrent.futures import ThreadPoolExecutor,TimeoutError
from datetime import datetime
import os
from threading import Event

import mysql.connector
import pytest

from database.setup import run_script
from tests.mysql_support import reset_schema,DEV008_TRIGGERS
from tests.sql_validation_support import queries,INDEXES,index_inventory,trigger_restriction_probe


@pytest.fixture
def sql_database(request,monkeypatch):
    if os.getenv('CLINIQ_RUN_DEV008_MYSQL_TESTS')!='1':
        pytest.skip('Set CLINIQ_RUN_DEV008_MYSQL_TESTS=1 and confirm cliniq_test_dev reset')
    monkeypatch.setenv('CLINIQ_TEST_SQL_EXTENSIONS','1')
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


@pytest.fixture
def connection(sql_database):
    connection=sql_database.connect()
    try:
        yield connection
    finally:
        connection.rollback()
        connection.close()


QUERY_IDS=[f'Q{index:02d}' for index in range(1,13)]


@pytest.mark.parametrize('query_id',QUERY_IDS)
def test_advanced_query_results_match_approved_seed(connection,query_id):
    query=next(query for query in queries() if query['id']==query_id)
    with connection.cursor(dictionary=True) as cursor:
        cursor.execute(query['sql'])
        rows=cursor.fetchall()
    expected_counts=dict(zip(QUERY_IDS,[5,8,2,5,2,2,5,7,7,5,4,5]))
    assert len(rows)==expected_counts[query_id]
    if query_id=='Q01':
        assert {row['idPatient'] for row in rows}=={1,2,4,5,7}
    elif query_id=='Q02':
        assert {row['idRDV'] for row in rows}==set(range(1,9))
    elif query_id=='Q03':
        assert [row['idPatient'] for row in rows]==[6,7]
    elif query_id=='Q04':
        assert {row['idMedecin']:row['consultations'] for row in rows}=={1:2,2:1,3:1,4:1,5:2}
    elif query_id in ('Q05','Q06'):
        assert {row['idMedecin'] for row in rows}=={1,5}
    elif query_id=='Q07':
        assert {row['idHospitalisation'] for row in rows if row['dateSortie'] is None}=={4,5}
    elif query_id=='Q08':
        assert {(row['idConsultation'],row['idMedicament']) for row in rows}=={(1,1),(1,5),(2,2),(3,3),(4,1),(5,5),(6,4)}
    elif query_id=='Q09':
        assert {(row['idHospitalisation'],row['idActe'],row['idMedecin']) for row in rows}=={(1,1,1),(2,1,2),(2,2,2),(3,3,4),(4,4,5),(4,5,5),(5,1,1)}
    elif query_id=='Q10':
        assert {row['idMedecin']:row['rang'] for row in rows}=={1:1,5:1,2:2,3:2,4:2}
    elif query_id=='Q11':
        assert [int(row['cumul']) for row in rows]==[3,5,6,7]
    elif query_id=='Q12':
        assert sum(row['lits'] for row in rows)==7
        assert sum(row['occupes'] for row in rows)==2
        assert sum(row['disponibles'] for row in rows)==5


def test_trigger_metadata_and_secondary_indexes_do_not_change_model(connection):
    with connection.cursor() as cursor:
        cursor.execute('SELECT TRIGGER_NAME,EVENT_OBJECT_TABLE,ACTION_TIMING,EVENT_MANIPULATION FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE()')
        assert {name:(table,timing,event) for name,table,timing,event in cursor.fetchall()}==DEV008_TRIGGERS
        cursor.execute("SELECT COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='DESIGNER_RESPONSABLE' AND CONSTRAINT_NAME='PRIMARY' ORDER BY ORDINAL_POSITION")
        assert cursor.fetchall()==[('idHospitalisation',),('idActe',)]
        cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()')
        assert cursor.fetchone()[0]==15
    inventory=index_inventory(connection)
    for name,(table,columns) in INDEXES.items():
        entries=[row for row in inventory[table] if row['Key_name']==name]
        assert tuple(row['Column_name'] for row in sorted(entries,key=lambda row:row['Seq_in_index']))==columns
        assert all(row['Non_unique']==1 for row in entries)
        shapes={}
        for row in inventory[table]:
            shapes.setdefault(row['Key_name'],[]).append((row['Seq_in_index'],row['Column_name']))
        assert sum(tuple(column for _,column in sorted(shape))==columns for shape in shapes.values())==1


def insert_consultation(cursor,patient=1,doctor=1,rdv=6):
    cursor.execute('INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin,idRDV) VALUES (%s,%s,%s,%s,%s,%s)',
                   ('2082-01-01 09:00:00','DEV008 fictif','DEV008 fictif',patient,doctor,rdv))
    return cursor.lastrowid


@pytest.mark.parametrize('patient,doctor',[(2,1),(1,2)])
def test_direct_insert_rejects_mismatched_appointment(connection,patient,doctor):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as caught:
            insert_consultation(cursor,patient,doctor)
    assert (caught.value.errno,caught.value.sqlstate)==(1644,'45000')


def test_direct_valid_insert_optional_link_and_unlink(connection):
    with connection.cursor() as cursor:
        cid=insert_consultation(cursor)
        insert_consultation(cursor,patient=7,rdv=None)
        cursor.execute('UPDATE CONSULTATION SET idRDV=NULL WHERE idConsultation=%s',(cid,))
        cursor.execute('UPDATE RENDEZ_VOUS SET idPatient=2,idMedecin=2 WHERE idRDV=6')


@pytest.mark.parametrize('column', ['idPatient','idMedecin'])
def test_direct_consultation_update_is_guarded(connection,column):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as caught:
            cursor.execute(f'UPDATE CONSULTATION SET `{column}`=%s WHERE idConsultation=%s',(2,1))
    assert (caught.value.errno,caught.value.sqlstate)==(1644,'45000')


@pytest.mark.parametrize('column', ['idPatient','idMedecin'])
def test_direct_appointment_update_cannot_break_existing_consultation(connection,column):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as caught:
            cursor.execute(f'UPDATE RENDEZ_VOUS SET `{column}`=%s WHERE idRDV=%s',(2,1))
    assert (caught.value.errno,caught.value.sqlstate)==(1644,'45000')


def test_valid_parent_edits_and_correct_link_update_remain_possible(connection):
    with connection.cursor() as cursor:
        cursor.execute("UPDATE RENDEZ_VOUS SET statut='Confirmé',dureePrevue=45 WHERE idRDV=1")
        cursor.execute('UPDATE CONSULTATION SET idPatient=1,idMedecin=1,idRDV=6 WHERE idConsultation=6')


def test_trigger_does_not_replace_fk_or_unique_checks(connection):
    with connection.cursor() as cursor:
        with pytest.raises(mysql.connector.Error) as fk:
            insert_consultation(cursor,rdv=999999)
        assert fk.value.errno==1452
        with pytest.raises(mysql.connector.Error) as unique:
            insert_consultation(cursor,rdv=1)
        assert unique.value.errno==1062


def new_appointment(database):
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('INSERT INTO RENDEZ_VOUS (dateHeure,dureePrevue,statut,idPatient,idMedecin) VALUES (%s,%s,%s,%s,%s)',
                           ('2082-01-01 09:00:00',30,'Planifié',1,1))
            rid=cursor.lastrowid
        connection.commit()
    return rid


def assert_no_mismatch(database,rid):
    with database.connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM CONSULTATION c JOIN RENDEZ_VOUS r ON r.idRDV=c.idRDV WHERE r.idRDV=%s AND (c.idPatient<>r.idPatient OR c.idMedecin<>r.idMedecin)',(rid,))
            assert cursor.fetchone()[0]==0


def test_parent_change_first_blocks_then_rejects_direct_child_insert(sql_database):
    rid=new_appointment(sql_database)
    parent=sql_database.connect()
    started=Event()
    def insert():
        with sql_database.connect() as child:
            with child.cursor() as cursor:
                started.set()
                try:
                    insert_consultation(cursor,rdv=rid)
                    child.commit()
                    return 0
                except mysql.connector.Error as exc:
                    child.rollback()
                    return exc.errno
    try:
        with parent.cursor() as cursor:
            cursor.execute('UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=%s',(rid,))
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(insert)
            assert started.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            parent.commit()
            assert future.result(timeout=8)==1644
    finally:
        parent.rollback(); parent.close()
    assert_no_mismatch(sql_database,rid)


def test_child_insert_first_blocks_then_rejects_direct_parent_change(sql_database):
    rid=new_appointment(sql_database)
    child=sql_database.connect()
    started=Event()
    def update():
        with sql_database.connect() as parent:
            with parent.cursor() as cursor:
                started.set()
                try:
                    cursor.execute('UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=%s',(rid,))
                    parent.commit()
                    return 0
                except mysql.connector.Error as exc:
                    parent.rollback()
                    return exc.errno
    try:
        with child.cursor() as cursor:
            insert_consultation(cursor,rdv=rid)
        with ThreadPoolExecutor(max_workers=1) as pool:
            future=pool.submit(update)
            assert started.wait(2)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.1)
            child.commit()
            assert future.result(timeout=8)==1644
    finally:
        child.rollback(); child.close()
    assert_no_mismatch(sql_database,rid)


@pytest.mark.parametrize('direction',['parent','child'])
def test_trigger_reads_current_values_despite_preexisting_repeatable_read_snapshot(sql_database,direction):
    rid=new_appointment(sql_database)
    stale=sql_database.connect()
    try:
        stale.start_transaction(isolation_level='REPEATABLE READ',consistent_snapshot=True)
        with stale.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM CONSULTATION WHERE idRDV=%s',(rid,)); cursor.fetchone()
            cursor.execute('SELECT idPatient FROM RENDEZ_VOUS WHERE idRDV=%s',(rid,)); cursor.fetchone()
        with sql_database.connect() as concurrent:
            with concurrent.cursor() as cursor:
                if direction=='parent':
                    insert_consultation(cursor,rdv=rid)
                else:
                    cursor.execute('UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=%s',(rid,))
            concurrent.commit()
        with stale.cursor() as cursor:
            with pytest.raises(mysql.connector.Error) as caught:
                if direction=='parent':
                    cursor.execute('UPDATE RENDEZ_VOUS SET idPatient=2 WHERE idRDV=%s',(rid,))
                else:
                    insert_consultation(cursor,rdv=rid)
        assert caught.value.errno==1644
    finally:
        stale.rollback(); stale.close()
    assert_no_mismatch(sql_database,rid)


def test_failed_trigger_statement_rolls_back_whole_application_transaction(sql_database):
    from db.connection import transaction
    with pytest.raises(mysql.connector.Error):
        with transaction() as active:
            with active.cursor() as cursor:
                cursor.execute('UPDATE RENDEZ_VOUS SET dureePrevue=40 WHERE idRDV=6')
                insert_consultation(cursor,patient=2,rdv=6)
    with sql_database.connect() as check:
        with check.cursor() as cursor:
            cursor.execute('SELECT dureePrevue FROM RENDEZ_VOUS WHERE idRDV=6')
            assert cursor.fetchone()[0]==30


def test_invoking_table_locking_trigger_restriction_is_verified(connection):
    probe=trigger_restriction_probe(connection)
    assert probe==dict(accepted=False,errno=1442,sqlstate='HY000')
