"""Headless Streamlit workflows; all writes use mocked repositories."""

from datetime import date, datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db.repositories.common import ConcurrentEditError, RepositoryError


ROOT = Path(__file__).resolve().parents[1]

PATIENT = dict(idPatient=1, nom='Demo', prenom='Test', dateNaissance=date(1990, 1, 1),
               telephone='DEMO', adresse='Rue fictive')


def dashboard_data():
    return dict(as_of=datetime(2026, 11, 16, 12), metrics=dict(patients=7, doctors=5,
        appointments=3, hospitalized=2, occupied_beds=2, available_beds=5),
        recent=[], daily=[], by_service=[])


@pytest.fixture
def patient_mocks():
    with patch('db.repositories.patient_repository.list_patients', return_value=dict(rows=[PATIENT], total=1, page=0)) as listing, \
         patch('db.repositories.patient_repository.patient_detail', return_value=dict(patient=PATIENT, consultations=[], hospitalizations=[])), \
         patch('db.repositories.patient_repository.add_patient', return_value=2) as add, \
         patch('db.repositories.patient_repository.update_patient') as update:
        yield listing, add, update


def test_navigation_and_real_metric_rendering(patient_mocks):
    with patch('ui.dashboard_data.load_dashboard', return_value=dashboard_data()):
        app = AppTest.from_file(ROOT / 'app.py').run()
        assert not app.exception
        assert [m.value for m in app.metric] == ['7', '5', '3', '2', '2', '5']
        app.switch_page('pages/patients.py').run()
        assert not app.exception
        assert app.title[0].value == 'Patients'


def test_dashboard_query_failure_is_sanitized():
    with patch('ui.dashboard_data.load_dashboard', side_effect=RepositoryError('safe')):
        app = AppTest.from_file(ROOT / 'app.py').run()
        assert not app.exception
        assert app.error and len(app.metric) == 0


def test_directory_search_detail_and_empty_history(patient_mocks):
    listing, _, _ = patient_mocks
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    app.text_input(key='patient_search_input').set_value("Demo %_")
    app.button(key='FormSubmitter:patient_search_form-Rechercher').click().run()
    assert listing.call_args.args == ('Demo %_', 0)
    app.selectbox(key='patient_selected').set_value(1).run()
    assert not app.exception
    assert any('Aucune consultation' in info.value for info in app.info)
    assert any('Aucune hospitalisation' in info.value for info in app.info)


def fill_add_form(app):
    for field, value in [('nom', 'New'), ('prenom', 'Demo'), ('telephone', 'DEMO'), ('adresse', 'Rue fictive')]:
        app.text_input(key=f'add_0_{field}').set_value(value)
    app.date_input(key='add_0_birth').set_value(date(2000, 1, 1))


def test_registration_validation_success_and_form_reset(patient_mocks):
    _, add, _ = patient_mocks
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    app.segmented_control(key='patient_mode').set_value('Nouveau patient').run()
    app.button(key='patient_add_submit').click().run()
    assert app.warning and not app.exception
    add.assert_not_called()
    fill_add_form(app)
    app.button(key='patient_add_submit').click().run()
    assert not app.exception
    add.assert_called_once()
    assert app.success
    assert app.text_input(key='add_1_nom').value == ''


def test_failed_registration_retains_values(patient_mocks):
    _, add, _ = patient_mocks
    add.side_effect = RepositoryError('safe')
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    app.segmented_control(key='patient_mode').set_value('Nouveau patient').run()
    fill_add_form(app)
    app.button(key='patient_add_submit').click().run()
    assert not app.exception and app.error
    assert app.text_input(key='add_0_nom').value == 'New'


def test_edit_saves_selected_patient_with_original_snapshot(patient_mocks):
    _, _, update = patient_mocks
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    app.selectbox(key='patient_selected').set_value(1).run()
    app.toggle(key='patient_edit_toggle_1').set_value(True).run()
    app.text_input(key='edit_1_1_adresse').set_value('Nouvelle adresse fictive')
    app.button(key='patient_edit_submit').click().run()
    assert not app.exception and app.success
    args = update.call_args.args
    assert args[0] == 1 and args[1]['adresse'] == 'Nouvelle adresse fictive'
    assert args[2] == PATIENT


def test_edit_conflict_keeps_typed_values(patient_mocks):
    _, _, update = patient_mocks
    update.side_effect = ConcurrentEditError('Le dossier a été modifié ; rechargez le formulaire.')
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    app.selectbox(key='patient_selected').set_value(1).run()
    app.toggle(key='patient_edit_toggle_1').set_value(True).run()
    app.text_input(key='edit_1_1_adresse').set_value('Nouvelle adresse fictive')
    app.button(key='patient_edit_submit').click().run()
    assert not app.exception and app.error
    assert app.text_input(key='edit_1_1_adresse').value == 'Nouvelle adresse fictive'


def test_empty_directory_and_connection_error(patient_mocks):
    listing, _, _ = patient_mocks
    listing.return_value = dict(rows=[], total=0, page=0)
    app = AppTest.from_file(ROOT / 'pages/patients.py').run()
    assert not app.exception and app.info
    listing.side_effect = RepositoryError('safe')
    app.run()
    assert not app.exception and app.error
