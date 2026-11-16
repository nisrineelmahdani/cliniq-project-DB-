"""Patient context, catalog search, association forms and explicit removal consent."""

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db.repositories.common import ConcurrentEditError, RepositoryError
from tests.test_dev005_services import CONTEXT, VALUES, ORIGINAL


ROOT=Path(__file__).resolve().parents[1]
CONTEXT_ROW={**CONTEXT,'patient':'Patient fictif','medecin':'Médecin fictif'}
PRESCRIBED={**ORIGINAL,'nomMedicament':'DemoCard','forme':'Comprimé fictif','dosage':'5 mg fictifs'}
CATALOG_ROW=dict(idMedicament=3,nomMedicament='DemoNasal',forme='Solution fictive',dosage='0,9 % fictif',assigned=0)
OPTIONS=dict(patients=[{'idPatient':5,'label':'Patient fictif'}],doctors=[{'idMedecin':5,'label':'Médecin fictif'}],forms=['Solution fictive'])
CONSULT_ENTRY=dict(idConsultation=7,dateHeure=CONTEXT['dateHeure'],patient='Patient fictif',medecin='Médecin fictif',medications=1)


@pytest.fixture
def mocks():
    with patch('db.repositories.prescription_repository.filter_options',return_value=OPTIONS), \
         patch('db.repositories.prescription_repository.list_consultations',return_value=dict(rows=[CONSULT_ENTRY],total=1,page=0)) as consultations, \
         patch('db.repositories.prescription_repository.consultation_detail',return_value=dict(consultation=CONTEXT_ROW,prescriptions=[PRESCRIBED])) as detail, \
         patch('db.repositories.prescription_repository.list_medications',return_value=dict(rows=[CATALOG_ROW],total=1,page=0)) as medications, \
         patch('db.repositories.prescription_repository.add_prescription') as add, \
         patch('db.repositories.prescription_repository.update_prescription') as update, \
         patch('db.repositories.prescription_repository.remove_prescription') as remove:
        yield consultations,detail,medications,add,update,remove


def open_consultation():
    app=AppTest.from_file(ROOT/'pages/prescriptions.py').run()
    app.selectbox(key='rx_consultation').set_value(7).run()
    assert not app.exception
    return app


def test_context_display_consultation_and_medication_filters(mocks):
    consultations,_,medications,*_=mocks
    app=open_consultation()
    assert any(CONTEXT['diagnostic']==item.value for item in app.text)
    assert len(app.dataframe)==3
    app.selectbox(key='rx_filter_doctor').set_value(5)
    app.selectbox(key='rx_filter_prescribed').set_value(False)
    app.button(key='rx_filter_submit').click().run()
    assert consultations.call_args.kwargs['doctor']==5
    assert consultations.call_args.kwargs['prescribed'] is False
    app.text_input(key='rx_med_search').set_value('%_')
    app.selectbox(key='rx_med_form').set_value('Solution fictive')
    app.button(key='rx_med_filter_submit').click().run()
    assert medications.call_args.kwargs['search']=='%_'
    assert medications.call_args.kwargs['form']=='Solution fictive'


def test_add_validates_then_saves_and_clears_form(mocks):
    *_,add,_,_=mocks
    app=open_consultation()
    app.button(key='rx_add_submit').click().run()
    assert app.error and not app.exception
    add.assert_not_called()
    app.selectbox(key='rx_add_1_medication').set_value(3)
    app.text_area(key='rx_add_1_instructions').set_value('Instructions fictives')
    app.button(key='rx_add_submit').click().run()
    assert app.success and not app.exception
    assert add.call_args.args==(7,3,dict(quantite=1,posologie='Instructions fictives',duree=1))
    assert app.text_area(key='rx_add_2_instructions').value==''


def test_edit_passes_composite_snapshot_and_retains_conflicted_values(mocks):
    *_,update,_=mocks
    update.side_effect=ConcurrentEditError('Cette prescription a été modifiée. Rechargez ses valeurs.')
    app=open_consultation()
    app.segmented_control(key='rx_mode').set_value('Modifier / retirer').run()
    app.selectbox(key='rx_prescribed').set_value(2).run()
    revision=app.session_state['rx_revision']
    app.number_input(key=f'rx_edit_7_2_{revision}_quantity').set_value(4)
    app.button(key='rx_edit_submit').click().run()
    assert not app.exception and app.error
    assert app.number_input(key=f'rx_edit_7_2_{revision}_quantity').value==4
    assert update.call_args.args[:2]==(7,2)
    assert update.call_args.kwargs['original']==PRESCRIBED
    update.side_effect=None
    app.button(key='rx_edit_submit').click().run()
    assert not app.exception and app.success


def test_removal_requires_confirmation_and_only_removes_selected_association(mocks):
    *_,remove=mocks
    app=open_consultation()
    app.segmented_control(key='rx_mode').set_value('Modifier / retirer').run()
    app.selectbox(key='rx_prescribed').set_value(2).run()
    app.segmented_control(key='rx_action_7_2').set_value('Retirer').run()
    app.button(key='rx_remove_submit').click().run()
    assert not app.exception and app.error
    remove.assert_not_called()
    revision=app.session_state['rx_revision']
    app.checkbox(key=f'rx_remove_7_2_{revision}_confirm').set_value(True)
    app.button(key='rx_remove_submit').click().run()
    assert not app.exception and app.success
    assert remove.call_args.args==(7,2)
    assert remove.call_args.kwargs['original']==PRESCRIBED


def test_confirmation_does_not_transfer_to_another_medication(mocks):
    _,detail,*_=mocks
    other={**PRESCRIBED,'idMedicament':4,'nomMedicament':'Autre médicament fictif'}
    detail.return_value=dict(consultation=CONTEXT_ROW,prescriptions=[PRESCRIBED,other])
    app=open_consultation()
    app.segmented_control(key='rx_mode').set_value('Modifier / retirer').run()
    app.selectbox(key='rx_prescribed').set_value(2).run()
    app.segmented_control(key='rx_action_7_2').set_value('Retirer').run()
    revision=app.session_state['rx_revision']
    app.checkbox(key=f'rx_remove_7_2_{revision}_confirm').set_value(True)
    # Checkbox belongs to a form and is not submitted; selecting another record
    # must never carry consent to that different composite key.
    app.selectbox(key='rx_prescribed').set_value(4).run()
    app.segmented_control(key='rx_action_7_4').set_value('Retirer').run()
    new_revision=app.session_state['rx_revision']
    assert not app.checkbox(key=f'rx_remove_7_4_{new_revision}_confirm').value


def test_consultation_without_medications_is_accessible(mocks):
    _,detail,*_=mocks
    detail.return_value=dict(consultation=CONTEXT_ROW,prescriptions=[])
    app=open_consultation()
    assert any('Aucun médicament prescrit' in item.value for item in app.info)
    assert app.button(key='rx_add_submit')


def test_changed_consultation_context_blocks_form_until_refresh(mocks):
    _,detail,*_=mocks
    app=open_consultation()
    detail.return_value=dict(consultation={**CONTEXT_ROW,'diagnostic':'Diagnostic modifié'},prescriptions=[PRESCRIBED])
    app.run()
    assert app.warning and not app.exception
    assert not any(button.key=='rx_add_submit' for button in app.button)
    app.button(key='rx_refresh').click().run()
    assert not app.exception and app.button(key='rx_add_submit')


def test_failed_add_retains_input_and_empty_catalog_feedback(mocks):
    _,_,medications,add,*_=mocks
    add.side_effect=RepositoryError('Ce médicament est déjà prescrit.')
    app=open_consultation()
    app.selectbox(key='rx_add_1_medication').set_value(3)
    app.text_area(key='rx_add_1_instructions').set_value('Instructions fictives')
    app.button(key='rx_add_submit').click().run()
    assert app.error and not app.exception
    assert app.text_area(key='rx_add_1_instructions').value=='Instructions fictives'
    medications.return_value=dict(rows=[],total=0,page=0)
    app.run()
    assert not app.exception and any('Aucun médicament pour ces critères' in item.value for item in app.info)


def test_no_consultations_and_database_error(mocks):
    consultations,*_=mocks
    consultations.return_value=dict(rows=[],total=0,page=0)
    app=AppTest.from_file(ROOT/'pages/prescriptions.py').run()
    assert app.info and not app.exception
    consultations.side_effect=RepositoryError('Opération MySQL impossible.')
    app.run()
    assert app.error and not app.exception
