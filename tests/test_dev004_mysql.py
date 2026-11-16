"""Live clinical workflows and concurrent writers, confined to cliniq_test_dev."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
import os
from threading import Barrier

import pytest

from db.repositories import appointment_repository as appointments, consultation_repository as consultations
from db.repositories.clinical_common import ClinicalRuleError
from db.repositories.common import ConcurrentEditError
from services.appointment_service import save_appointment
from services.consultation_service import save_consultation


@pytest.fixture
def clinical_database(request, monkeypatch):
    if os.getenv('CLINIQ_RUN_DEV004_MYSQL_TESTS') != '1':
        pytest.skip('Set CLINIQ_RUN_DEV004_MYSQL_TESTS=1 and explicitly confirm cliniq_test_dev reset')
    database = request.getfixturevalue('dedicated_mysql_database')

    def connect():
        connection = database.connect()
        with connection.cursor() as cursor:
            cursor.execute('SET SESSION innodb_lock_wait_timeout=5')
        return connection

    monkeypatch.setattr('db.connection.get_connection', connect)
    return database


def appointment(when, *, doctor=1, patient=1, duration=30, status='Confirmé'):
    return dict(dateHeure=when, dureePrevue=duration, statut=status, idPatient=patient, idMedecin=doctor)


def consultation(when, *, doctor=1, patient=1, linked=None, room=None, reason='DEV004 scénario fictif'):
    return dict(dateHeure=when, motif=reason, diagnostic='Diagnostic éducatif fictif',
                idPatient=patient, idMedecin=doctor, idRDV=linked, idSalle=room)


def test_appointment_create_filter_edit_and_persistence(clinical_database):
    when = datetime(2031, 1, 1, 9)
    record_id = save_appointment(appointment(when))
    original = appointments.get_appointment(record_id)
    found = appointments.list_appointments(doctor=1, patient=1, day=when.date(), status='Confirmé')
    assert [row['idRDV'] for row in found['rows']] == [record_id]
    assert found['rows'][0]['fin'] == when + timedelta(minutes=30)
    save_appointment({**original, 'dateHeure': when + timedelta(hours=1), 'dureePrevue': 45, 'statut': 'Suivi personnalisé'},
                     appointment_id=record_id, original=original)
    persisted = appointments.get_appointment(record_id)
    assert persisted['dateHeure'].hour == 10 and persisted['dureePrevue'] == 45
    assert persisted['statut'] == 'Suivi personnalisé'
    with pytest.raises(ConcurrentEditError):
        save_appointment(original, appointment_id=record_id, original=original)
    with pytest.raises(ClinicalRuleError):
        save_appointment({**persisted, 'idPatient': 2}, appointment_id=record_id, original=persisted)
    assert appointments.get_appointment(record_id)['idPatient'] == 1
    assert appointments.list_appointments("' OR 1=1 --").get('total') == 0


@pytest.mark.parametrize('case,offset,allowed', [(1, -30, True), (2, 30, True), (3, -15, False), (4, 15, False), (5, 0, False)])
def test_overlap_half_open_boundaries(clinical_database, case, offset, allowed):
    when = datetime(2032, 1, case, 9)
    save_appointment(appointment(when))
    values = appointment(when + timedelta(minutes=offset), patient=2)
    if allowed:
        assert save_appointment(values)
    else:
        with pytest.raises(ClinicalRuleError, match='chevauche'):
            save_appointment(values)
        assert appointments.list_appointments(day=when.date())['total'] == 1
    # Another doctor can use exactly the same slot.
    assert save_appointment(appointment(when, doctor=2, patient=3))


def test_cancel_reactivate_and_self_edit(clinical_database):
    when = datetime(2033, 1, 1, 9)
    cancelled_id = save_appointment(appointment(when, status='Annulé'))
    active_id = save_appointment(appointment(when, patient=2))
    cancelled = appointments.get_appointment(cancelled_id)
    with pytest.raises(ClinicalRuleError, match='chevauche'):
        save_appointment({**cancelled, 'statut': 'Confirmé'}, appointment_id=cancelled_id, original=cancelled)
    assert appointments.get_appointment(cancelled_id)['statut'] == 'Annulé'
    active = appointments.get_appointment(active_id)
    save_appointment(active, appointment_id=active_id, original=active)


def race(function):
    barrier = Barrier(2)
    def contender(index):
        barrier.wait(timeout=5)
        try:
            return ('saved', function(index))
        except ClinicalRuleError:
            return ('rejected', None)
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(contender, index) for index in (1, 2)]
        return [job.result(timeout=15) for job in jobs]


def test_concurrent_first_appointments_are_serialized(clinical_database):
    when = datetime(2034, 1, 1, 9)
    result = race(lambda index: save_appointment(appointment(when, patient=index)))
    assert sorted(state for state, _ in result) == ['rejected', 'saved']
    assert appointments.list_appointments(doctor=1, day=when.date())['total'] == 1


def test_consultation_optional_links_search_and_edit(clinical_database):
    when = datetime(2035, 1, 1, 9)
    linked = save_appointment(appointment(when))
    record_id = save_consultation(consultation(when, linked=linked, room=1, reason='DEV004 literal 100%_fictif'))
    original = consultations.get_consultation(record_id)
    assert original['idRDV'] == linked and original['idSalle'] == 1
    assert consultations.list_consultations('%_fictif')['total'] == 1
    assert not consultations.appointment_options(1, 1) or linked not in [row['idRDV'] for row in consultations.appointment_options(1, 1)]
    assert linked in [row['idRDV'] for row in consultations.appointment_options(1, 1, consultation_id=record_id)]
    save_consultation({**original, 'motif': 'DEV004 motif modifié', 'diagnostic': 'Diagnostic modifié', 'idRDV': None, 'idSalle': None},
                      consultation_id=record_id, original=original)
    updated = consultations.get_consultation(record_id)
    assert updated['idRDV'] is None and updated['idSalle'] is None and updated['motif'] == 'DEV004 motif modifié'
    assert linked in [row['idRDV'] for row in consultations.appointment_options(1, 1)]
    with pytest.raises(ConcurrentEditError):
        save_consultation(original, consultation_id=record_id, original=original)
    # Multiple NULL appointment links are valid, with or without a room.
    assert save_consultation(consultation(when, room=2))
    assert save_consultation(consultation(when))


@pytest.mark.parametrize('case,patient,doctor', [(1, 2, 1), (2, 1, 2)])
def test_mismatched_appointment_ownership_rejected(clinical_database, case, patient, doctor):
    when = datetime(2035, 2, case, 9)
    linked = save_appointment(appointment(when))
    before = consultations.list_consultations()['total']
    with pytest.raises(ClinicalRuleError, match='correspondre'):
        save_consultation(consultation(when, patient=patient, doctor=doctor, linked=linked))
    assert consultations.list_consultations()['total'] == before


def test_consultation_duplicate_link_edit_and_owner_change_roll_back(clinical_database):
    when = datetime(2035, 3, 1, 9)
    first = save_appointment(appointment(when))
    second = save_appointment(appointment(when, doctor=2, patient=2))
    first_consult = save_consultation(consultation(when, linked=first))
    other_consult = save_consultation(consultation(when))
    original = consultations.get_consultation(first_consult)
    other = consultations.get_consultation(other_consult)
    with pytest.raises(ClinicalRuleError, match='déjà lié'):
        save_consultation({**other, 'idRDV': first}, consultation_id=other_consult, original=other)
    with pytest.raises(ClinicalRuleError, match='correspondre'):
        save_consultation({**original, 'idMedecin': 2}, consultation_id=first_consult, original=original)
    assert consultations.get_consultation(first_consult) == original
    assert consultations.get_consultation(other_consult) == other
    save_consultation({**original, 'idRDV': second, 'idMedecin': 2, 'idPatient': 2}, consultation_id=first_consult, original=original)
    assert consultations.get_consultation(first_consult)['idMedecin'] == 2


def test_concurrent_consultations_cannot_share_appointment(clinical_database):
    when = datetime(2036, 1, 1, 9)
    linked = save_appointment(appointment(when))
    result = race(lambda index: save_consultation(consultation(when, linked=linked, reason=f'DEV004 concurrent fictif {index}')))
    assert sorted(state for state, _ in result) == ['rejected', 'saved']


def test_consultation_missing_reference_is_actionable_and_does_not_persist(clinical_database):
    when = datetime(2036, 2, 1, 9)
    before = consultations.list_consultations()['total']
    for values in (consultation(when, linked=999999), consultation(when, room=999999), consultation(when, patient=999999), consultation(when, doctor=999999)):
        with pytest.raises(ClinicalRuleError):
            save_consultation(values)
    assert consultations.list_consultations()['total'] == before
