"""Reproducible DEV-008 SQL inspection helpers; no application feature code."""

from datetime import datetime,timedelta
from pathlib import Path
import re

import mysql.connector

from database.setup import SQL_DIRECTORY
from tests.mysql_support import TABLES,verify_environment,verify_selected_database


INDEXES = {
    'idx_rdv_medecin_dateheure': ('RENDEZ_VOUS',('idMedecin','dateHeure')),
    'idx_consultation_dateheure': ('CONSULTATION',('dateHeure',)),
}
PLAN_QUERIES = {
    'agenda_medecin': '''SELECT idRDV,dateHeure,dureePrevue,statut,idPatient FROM RENDEZ_VOUS
        WHERE idMedecin=%s AND dateHeure>=%s AND dateHeure<%s ORDER BY dateHeure,idRDV''',
    'consultations_recentes': '''SELECT idConsultation,dateHeure,idPatient,idMedecin FROM CONSULTATION
        WHERE dateHeure<=%s ORDER BY dateHeure DESC,idConsultation DESC LIMIT 10''',
}
SEED_PARAMS = {'agenda_medecin': (1,datetime(2026,11,20),datetime(2026,11,21)),
               'consultations_recentes': (datetime(2026,11,16,12),)}
BENCHMARK_PARAMS = {'agenda_medecin': (3,datetime(2040,6,1),datetime(2040,6,2)),
                    'consultations_recentes': (datetime(2040,6,1,12),)}


def queries():
    text=(SQL_DIRECTORY/'04_queries.sql').read_text(encoding='utf-8')
    markers=list(re.finditer(r'^-- (Q\d{2}) : (.+)$',text,re.M))
    result=[]
    for index,match in enumerate(markers):
        block=text[match.end():markers[index+1].start() if index+1<len(markers) else len(text)]
        sql=re.sub(r'--[^\n]*','',block).strip().rstrip(';')
        result.append(dict(id=match[1],objective=match[2],sql=sql))
    return result


def validate_target(connection):
    verify_environment()
    verify_selected_database(connection)


def index_inventory(connection):
    result={}
    with connection.cursor(dictionary=True) as cursor:
        for table in TABLES:
            cursor.execute(f'SHOW INDEX FROM `{table}`')
            result[table]=cursor.fetchall()
    return result


def explain(connection,params):
    result={}
    with connection.cursor(dictionary=True) as cursor:
        for name,sql in PLAN_QUERIES.items():
            cursor.execute('EXPLAIN FORMAT=TRADITIONAL '+sql,params[name])
            plan=cursor.fetchall()
            cursor.execute(sql,params[name])
            rows=cursor.fetchall()
            result[name]=dict(sql=sql,parameters=params[name],plan=plan,result_count=len(rows))
    return result


def analyze(connection):
    with connection.cursor() as cursor:
        cursor.execute('ANALYZE TABLE RENDEZ_VOUS,CONSULTATION')
        cursor.fetchall()


def populate_benchmark(connection,count=12000):
    validate_target(connection)
    start=datetime(2040,1,1)
    with connection.cursor() as cursor:
        for offset in range(0,count,1000):
            indices=range(offset,min(offset+1000,count))
            appointments=[(start+timedelta(hours=i),30,'Planifié',i%7+1,i%5+1) for i in indices]
            consultations=[(start+timedelta(hours=i),'DEV008 scénario synthétique','Donnée fictive de test',i%7+1,i%5+1) for i in indices]
            cursor.executemany('INSERT INTO RENDEZ_VOUS (dateHeure,dureePrevue,statut,idPatient,idMedecin) VALUES (%s,%s,%s,%s,%s)',appointments)
            cursor.executemany('INSERT INTO CONSULTATION (dateHeure,motif,diagnostic,idPatient,idMedecin) VALUES (%s,%s,%s,%s,%s)',consultations)
    connection.commit()


def trigger_restriction_probe(connection):
    validate_target(connection)
    with connection.cursor() as cursor:
        cursor.execute('''CREATE TRIGGER cliniq_probe_hosp_overlap BEFORE INSERT ON HOSPITALISATION
            FOR EACH ROW BEGIN
              DECLARE found_id INT DEFAULT NULL;
              SELECT idHospitalisation INTO found_id FROM HOSPITALISATION WHERE idLit=NEW.idLit LIMIT 1 FOR UPDATE;
            END''')
        try:
            try:
                cursor.execute('INSERT INTO HOSPITALISATION (dateAdmission,dateSortie,idPatient,idLit) VALUES (%s,%s,%s,%s)',
                               ('2081-01-01','2081-01-02',1,1))
                result=dict(accepted=True)
            except mysql.connector.Error as exc:
                result=dict(accepted=False,errno=exc.errno,sqlstate=exc.sqlstate)
        finally:
            connection.rollback()
            cursor.execute('DROP TRIGGER cliniq_test_dev.cliniq_probe_hosp_overlap')
    return result


def workload_counts(connection):
    result={}
    with connection.cursor() as cursor:
        for table in ('RENDEZ_VOUS','CONSULTATION'):
            cursor.execute(f'SELECT COUNT(*) FROM `{table}`')
            result[table]=cursor.fetchone()[0]
    return result
