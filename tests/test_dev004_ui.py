"""Headless UI workflows; clinical writes and lookup reads are mocked."""

from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from typing import cast

import pytest
from streamlit.testing.v1 import AppTest

from db.repositories.clinical_common import ClinicalRuleError
from db.repositories.common import RepositoryError
from tests.test_dev004_services import APPOINTMENT, CONSULTATION


ROOT = Path(__file__).resolve().parents[1]
OPTIONS = dict(patients=[{'idPatient': 1, 'label': 'Patient fictif'}, {'idPatient': 2, 'label': 'Autre patient fictif'}],
               doctors=[{'idMedecin': 1, 'label': 'Médecin fictif'}, {'idMedecin': 2, 'label': 'Autre médecin fictif'}],
               rooms=[{'idSalle': 1, 'label': 'CONS-01'}], statuses=['Planifié', 'Confirmé', 'Annulé'])
APPT_ROW = {**APPOINTMENT, 'idRDV': 1, 'patient': 'Patient fictif', 'medecin': 'Médecin fictif', 'fin': cast(datetime, APPOINTMENT['dateHeure']) + timedelta(minutes=30)}
CONSULT_ROW = {**CONSULTATION, 'idConsultation': 1, 'patient': 'Patient fictif', 'medecin': 'Médecin fictif', 'codeSalle': None}


@pytest.fixture
def clinical_mocks():
    with patch('db.repositories.clinical_common.lookup_options', return_value=OPTIONS), \
         patch('db.repositories.appointment_repository.list_appointments', return_value=dict(rows=[APPT_ROW], total=1, page=0)) as listing, \
         patch('db.repositories.appointment_repository.get_appointment', return_value={**APPOINTMENT, 'idRDV': 1}), \
         patch('db.repositories.appointment_repository.save_appointment', return_value=2) as save_appt, \
         patch('db.repositories.consultation_repository.list_consultations', return_value=dict(rows=[CONSULT_ROW], total=1, page=0)) as consultations, \
         patch('db.repositories.consultation_repository.get_consultation', return_value={**CONSULTATION, 'idConsultation': 1}), \
         patch('db.repositories.consultation_repository.appointment_options', return_value=[{'idRDV': 6, 'dateHeure': datetime(2030, 1, 1, 9), 'statut': 'Confirmé'}]) as eligible, \
         patch('db.repositories.consultation_repository.save_consultation', return_value=2) as save_consult:
        yield listing, save_appt, consultations, eligible, save_consult


def test_appointment_agenda_filters_and_table(clinical_mocks):
    listing, *_ = clinical_mocks
    app = AppTest.from_file(ROOT / 'pages/appointments.py').run()
    assert not app.exception and any('01/01/2030' in h.value for h in app.subheader)
    app.selectbox(key='appt_filter_doctor').set_value(1)
    app.text_input(key='appt_search').set_value('Fictif')
    app.button(key='appt_filter_submit').click().run()
    assert listing.call_args.kwargs['doctor'] == 1 and listing.call_args.kwargs['search'] == 'Fictif'
    app.segmented_control(key='appt_view').set_value('Tableau').run()
    assert not app.exception and len(app.dataframe) == 1


def test_appointment_registration_validation_success_and_reset(clinical_mocks):
    _, save_appt, *_ = clinical_mocks
    app = AppTest.from_file(ROOT / 'pages/appointments.py').run()
    app.segmented_control(key='appt_mode').set_value('Nouveau rendez-vous').run()
    app.button(key='appt_add_submit').click().run()
    assert app.error and not app.exception
    save_appt.assert_not_called()
    app.selectbox(key='appt_add_0_patient').set_value(1)
    app.selectbox(key='appt_add_0_doctor').set_value(1)
    app.selectbox(key='appt_add_0_status').set_value('Planifié')
    app.button(key='appt_add_submit').click().run()
    assert not app.exception and app.success
    save_appt.assert_called_once()
    assert app.selectbox(key='appt_add_1_patient').value is None


def test_appointment_overlap_feedback_preserves_inputs(clinical_mocks):
    _, save_appt, *_ = clinical_mocks
    save_appt.side_effect = ClinicalRuleError('Ce créneau chevauche un rendez-vous actif.')
    app = AppTest.from_file(ROOT / 'pages/appointments.py').run()
    app.segmented_control(key='appt_mode').set_value('Nouveau rendez-vous').run()
    app.selectbox(key='appt_add_0_patient').set_value(1)
    app.selectbox(key='appt_add_0_doctor').set_value(1)
    app.selectbox(key='appt_add_0_status').set_value('Planifié')
    app.button(key='appt_add_submit').click().run()
    assert app.error and not app.exception
    assert app.selectbox(key='appt_add_0_patient').value == 1


def test_appointment_edit_preserves_owner_and_passes_snapshot(clinical_mocks):
    _, save_appt, *_ = clinical_mocks
    app = AppTest.from_file(ROOT / 'pages/appointments.py').run()
    app.selectbox(key='appt_selected').set_value(1).run()
    app.toggle(key='appt_edit_toggle_1').set_value(True).run()
    assert app.selectbox(key='appt_edit_1_1_patient').disabled
    app.number_input(key='appt_edit_1_1_duration').set_value(45)
    app.button(key='appt_edit_submit').click().run()
    assert not app.exception and app.success
    assert save_appt.call_args.args[0]['dureePrevue'] == 45
    assert save_appt.call_args.kwargs['original'] == {**APPOINTMENT, 'idRDV': 1}


def test_consultation_walkin_create_and_reset(clinical_mocks):
    *_, eligible, save_consult = clinical_mocks
    app = AppTest.from_file(ROOT / 'pages/consultations.py').run()
    app.segmented_control(key='consult_mode').set_value('Nouvelle consultation').run()
    app.selectbox(key='consult_add_0_patient').set_value(1).run()
    app.selectbox(key='consult_add_0_doctor').set_value(1).run()
    assert eligible.call_args.args == (1, 1)
    app.text_area(key='consult_add_0_reason').set_value('Motif fictif')
    app.text_area(key='consult_add_0_diagnosis').set_value('Diagnostic fictif')
    app.button(key='consult_add_submit').click().run()
    assert not app.exception and app.success
    assert save_consult.call_args.args[0]['idRDV'] is None
    assert save_consult.call_args.args[0]['idSalle'] is None
    assert app.text_area(key='consult_add_1_reason').value == ''


def test_consultation_linked_creation_duplicate_error_and_retained_values(clinical_mocks):
    *_, save_consult = clinical_mocks
    save_consult.side_effect = ClinicalRuleError('Ce rendez-vous est déjà lié à une consultation.')
    app = AppTest.from_file(ROOT / 'pages/consultations.py').run()
    app.segmented_control(key='consult_mode').set_value('Nouvelle consultation').run()
    app.selectbox(key='consult_add_0_patient').set_value(1).run()
    app.selectbox(key='consult_add_0_doctor').set_value(1).run()
    app.selectbox(key='consult_add_0_appointment').set_value(6)
    app.selectbox(key='consult_add_0_room').set_value(1)
    app.text_area(key='consult_add_0_reason').set_value('Motif fictif')
    app.text_area(key='consult_add_0_diagnosis').set_value('Diagnostic fictif')
    app.button(key='consult_add_submit').click().run()
    assert not app.exception and app.error
    assert app.text_area(key='consult_add_0_reason').value == 'Motif fictif'
    assert save_consult.call_args.args[0]['idRDV'] == 6


def test_consultation_details_and_edit(clinical_mocks):
    *_, save_consult = clinical_mocks
    app = AppTest.from_file(ROOT / 'pages/consultations.py').run()
    app.selectbox(key='consult_selected').set_value(1).run()
    assert any(CONSULTATION['diagnostic'] in text.value for text in app.text)
    app.toggle(key='consult_edit_toggle_1').set_value(True).run()
    app.text_area(key='consult_edit_1_1_diagnosis').set_value('Diagnostic modifié')
    app.button(key='consult_edit_submit').click().run()
    assert not app.exception and app.success
    assert save_consult.call_args.args[0]['diagnostic'] == 'Diagnostic modifié'
    assert save_consult.call_args.kwargs['consultation_id'] == 1


@pytest.mark.parametrize('page,key', [('appointments.py', 0), ('consultations.py', 2)])
def test_clinical_empty_states_and_database_error(clinical_mocks, page, key):
    listing = clinical_mocks[key]
    listing.return_value = dict(rows=[], total=0, page=0)
    app = AppTest.from_file(ROOT / 'pages' / page).run()
    assert not app.exception and app.info
    listing.side_effect = RepositoryError('Opération MySQL impossible.')
    app.run()
    assert not app.exception and app.error
