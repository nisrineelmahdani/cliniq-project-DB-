"""Headless hospitalization admission, discharge, corrections and occupancy."""

from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db.repositories.common import ConcurrentEditError,RepositoryError
from tests.test_dev006_services import VALUES,ORIGINAL


ROOT=Path(__file__).resolve().parents[1]
ROW={**ORIGINAL,'patient':'Patient fictif','idChambre':2,'numeroChambre':'102','typeChambre':'Double','numeroLit':'B','statut':'En cours'}
BED=dict(idLit=3,numeroLit='B',idChambre=2,numeroChambre='102',typeChambre='Double',label='Chambre 102 · Lit B · Double')
OPTIONS=dict(patients=[{'idPatient':1,'label':'Patient fictif'}],rooms=[{'idChambre':2,'label':'102 · Double'}])
OCCUPANCY=dict(beds=[{key:BED[key] for key in ('idLit','numeroLit','idChambre','numeroChambre','typeChambre')}|{'occupied':1}],
    rooms=[dict(idChambre=2,numeroChambre='102',typeChambre='Double',total=2,occupied=1,available=1)])


@pytest.fixture
def mocks():
    with patch('db.repositories.hospitalization_repository.filter_options',return_value=OPTIONS), \
         patch('db.repositories.hospitalization_repository.list_hospitalizations',return_value=dict(rows=[ROW],total=1,page=0)) as listing, \
         patch('db.repositories.hospitalization_repository.get_hospitalization',return_value=ROW), \
         patch('db.repositories.hospitalization_repository.patient_history',return_value=[ROW]) as history, \
         patch('db.repositories.hospitalization_repository.available_beds',return_value=[BED]) as available, \
         patch('db.repositories.hospitalization_repository.occupancy',return_value=OCCUPANCY), \
         patch('db.repositories.hospitalization_repository.save_hospitalization',return_value=8) as save:
        yield listing,history,available,save


def test_stay_listing_filters_and_patient_history(mocks):
    listing,history,*_=mocks
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    assert not app.exception and app.dataframe
    app.selectbox(key='hosp_filter_patient').set_value(1)
    app.selectbox(key='hosp_filter_status').set_value('En cours')
    app.button(key='hosp_filter_submit').click().run()
    assert listing.call_args.kwargs['patient']==1 and listing.call_args.kwargs['status']=='En cours'
    app.selectbox(key='hosp_selected').set_value(8).run()
    assert not app.exception and history.call_args.args[0]==1
    assert any('Patient fictif'==text.value for text in app.text)


def test_new_admission_requires_selection_and_resets_on_success(mocks):
    *_,save=mocks
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.segmented_control(key='hosp_mode').set_value('Nouvelle admission').run()
    app.button(key='hosp_add_submit').click().run()
    assert app.error and not app.exception
    save.assert_not_called()
    app.selectbox(key='hosp_add_0_patient').set_value(1).run()
    app.selectbox(key='hosp_add_0_bed').set_value(3)
    app.button(key='hosp_add_submit').click().run()
    assert not app.exception and app.success
    assert save.call_args.args[0]['idPatient']==1 and save.call_args.args[0]['idLit']==3
    assert save.call_args.args[0]['dateSortie'] is None
    assert app.selectbox(key='hosp_add_1_patient').value is None


def test_interval_changes_refresh_availability_and_invalid_dates_block_submit(mocks):
    _,_,available,_=mocks
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.segmented_control(key='hosp_mode').set_value('Nouvelle admission').run()
    app.date_input(key='hosp_add_0_admission_date').set_value(datetime(2038,1,2).date()).run()
    assert available.call_args.args[0].date()==datetime(2038,1,2).date()
    app.toggle(key='hosp_add_0_has_discharge').set_value(True).run()
    app.date_input(key='hosp_add_0_discharge_date').set_value(datetime(2038,1,1).date()).run()
    assert not app.exception and app.warning
    assert not any(button.key=='hosp_add_submit' for button in app.button)


def test_no_available_beds_and_failed_save_feedback(mocks):
    _,_,available,save=mocks
    save.side_effect=RepositoryError('Ce lit est occupé pendant une partie du séjour.')
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.segmented_control(key='hosp_mode').set_value('Nouvelle admission').run()
    app.selectbox(key='hosp_add_0_patient').set_value(1).run()
    app.selectbox(key='hosp_add_0_bed').set_value(3)
    app.button(key='hosp_add_submit').click().run()
    assert app.error and not app.exception
    assert app.selectbox(key='hosp_add_0_bed').value==3
    available.return_value=[]
    app.run()
    assert app.info and not app.exception
    assert not any(button.key=='hosp_add_submit' for button in app.button)


def test_edit_passes_snapshot_and_stale_feedback_preserves_inputs(mocks):
    *_,save=mocks
    save.side_effect=ConcurrentEditError('Ce séjour a été modifié. Rechargez ses informations.')
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.selectbox(key='hosp_selected').set_value(8).run()
    app.segmented_control(key='hosp_action_8').set_value('Modifier').run()
    revision=app.session_state['hosp_revision']
    assert app.selectbox(key=f'hosp_edit_8_{revision}_patient').disabled
    app.button(key='hosp_edit_submit').click().run()
    assert app.error and not app.exception
    assert save.call_args.kwargs['original']==ROW
    assert save.call_args.kwargs['hospitalization_id']==8
    assert app.selectbox(key=f'hosp_edit_8_{revision}_bed').value==3


def test_record_discharge_from_selected_stay(mocks):
    *_,save=mocks
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.selectbox(key='hosp_selected').set_value(8).run()
    app.segmented_control(key='hosp_action_8').set_value('Sortie').run()
    revision=app.session_state['hosp_revision']
    app.date_input(key=f'hosp_exit_8_{revision}_date').set_value(datetime(2038,1,2).date()).run()
    app.button(key='hosp_discharge_submit').click().run()
    assert not app.exception and app.success
    assert save.call_args.args[0]['dateSortie'].date()==datetime(2038,1,2).date()


def test_occupancy_and_independent_patient_history(mocks):
    _,history,*_=mocks
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    app.segmented_control(key='hosp_mode').set_value('Occupation').run()
    assert not app.exception and [item.value for item in app.metric]==['2','1','1']
    assert len(app.dataframe)==2
    app.segmented_control(key='hosp_mode').set_value('Historique patient').run()
    app.selectbox(key='hosp_history_patient').set_value(1).run()
    assert history.call_args.args[0]==1 and not app.exception
    history.return_value=[]
    app.run()
    assert app.info and not app.exception


def test_empty_listing_and_safe_database_failure(mocks):
    listing,*_=mocks
    listing.return_value=dict(rows=[],total=0,page=0)
    app=AppTest.from_file(ROOT/'pages/hospitalizations.py').run()
    assert app.info and not app.exception
    listing.side_effect=RepositoryError('Opération MySQL impossible.')
    app.run()
    assert app.error and not app.exception
