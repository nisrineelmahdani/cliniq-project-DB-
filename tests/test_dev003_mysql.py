"""Opt-in real repository workflow using only cliniq_test_dev.

CLINIQ_RUN_DEV003_MYSQL_TESTS=1 python -m pytest tests/test_dev003_mysql.py -v -s
Supply CLINIQ_TEST_* and an exact reset confirmation. The database is never dropped.
"""

from datetime import date, datetime
import os

import pytest
import mysql.connector

from db.connection import transaction

from db.repositories.common import ConcurrentEditError, RepositoryError
from db.repositories.dashboard_repository import load_dashboard
from db.repositories.patient_repository import list_patients, patient_detail
from services.patient_service import add_patient, update_patient


@pytest.fixture
def isolated_database(monkeypatch, request):
    if os.getenv('CLINIQ_RUN_DEV003_MYSQL_TESTS') != '1':
        pytest.skip('Live repository test not enabled; set CLINIQ_RUN_DEV003_MYSQL_TESTS=1 and confirm the dedicated database reset')
    database = request.getfixturevalue('dedicated_mysql_database')
    monkeypatch.setattr('db.connection.get_connection', database.connect)
    return database.connect


def test_live_patient_workflow_and_dashboard_boundaries(isolated_database):
    connect = isolated_database
    now = datetime(2099, 1, 2, 12)
    original_metrics = load_dashboard(now)['metrics']
    assert original_metrics == dict(patients=7, doctors=5, appointments=0,
                                   hospitalized=2, occupied_beds=2, available_beds=5)
    values = dict(nom='DEV003-Fiction', prenom='Test', dateNaissance=date(2000, 1, 1),
                  telephone='DEMO-TEST', adresse='Adresse fictive de test')
    patient_id = add_patient(values)
    listing = list_patients('DEV003-Fiction')
    assert listing['total'] == 1 and listing['rows'][0]['idPatient'] == patient_id
    original = patient_detail(patient_id)['patient']
    assert patient_detail(patient_id)['consultations'] == []
    changed = {**values, 'adresse': 'Nouvelle adresse fictive'}
    update_patient(patient_id, changed, original)
    assert patient_detail(patient_id)['patient']['adresse'] == changed['adresse']
    with pytest.raises(ConcurrentEditError):
        update_patient(patient_id, values, original)
    assert patient_detail(patient_id)['patient']['adresse'] == changed['adresse']
    assert patient_detail(5)['consultations'] and patient_detail(5)['hospitalizations']

    # Real SQL failure rolls back without exposing the submitted identifying values.
    from db.repositories.patient_repository import add_patient as unchecked_add
    with pytest.raises(RepositoryError) as caught:
        unchecked_add({**values, 'telephone': None})
    assert 'DEV003-Fiction' not in str(caught.value)
    assert list_patients('DEV003-Fiction')['total'] == 1

    # Prove rollback of a preceding successful write, not just a rejected INSERT.
    with pytest.raises(mysql.connector.Error):
        with transaction() as connection:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE PATIENT SET adresse=%s WHERE idPatient=%s',
                               ('This fictional update must roll back', patient_id))
                cursor.execute('INSERT INTO EXERCER (idMedecin,idSpecialite) VALUES (%s,%s)', (1, 1))
    assert patient_detail(patient_id)['patient']['adresse'] == changed['adresse']

    connection = connect()
    try:
        with connection.cursor() as cursor:
            cursor.executemany('INSERT INTO HOSPITALISATION (dateAdmission,dateSortie,idPatient,idLit) VALUES (%s,%s,%s,%s)', [
                ('2099-01-01 00:00:00', '2099-01-02 11:00:00', 1, 7),  # already discharged
                ('2099-01-03 00:00:00', None, 2, 6),  # future admission
                ('2099-01-02 12:00:00', '2099-01-02 13:00:00', 1, 2),  # exactly admitted
                ('2099-01-02 12:00:00', '2099-01-02 13:00:00', 2, 2),  # deliberate overlap tests DISTINCT
            ])
            cursor.executemany('INSERT INTO RENDEZ_VOUS (dateHeure,dureePrevue,statut,idPatient,idMedecin) VALUES (%s,%s,%s,%s,%s)', [
                ('2099-01-02 00:00:00', 30, 'Planifié', 1, 1),
                ('2099-01-02 23:59:59', 30, 'Annulé', 2, 2),
                ('2099-01-03 00:00:00', 30, 'Planifié', 1, 1),
                ('2099-01-01 23:59:59', 30, 'Terminé', 1, 1),
            ])
        connection.commit()
    finally:
        connection.close()
    metrics = load_dashboard(now)['metrics']
    assert metrics == dict(patients=8, doctors=5, appointments=2, hospitalized=4, occupied_beds=3, available_beds=4)
    after_discharge = load_dashboard(datetime(2099, 1, 2, 13))['metrics']
    assert (after_discharge['hospitalized'], after_discharge['occupied_beds'], after_discharge['available_beds']) == (2, 2, 5)
    historical = load_dashboard(datetime(2026, 11, 16, 12))
    assert len(historical['recent']) == 7 and len(historical['daily']) == 30
    assert sum(row['consultations'] for row in historical['daily']) == 7
    assert sum(row['consultations'] for row in historical['by_service']) == 7
