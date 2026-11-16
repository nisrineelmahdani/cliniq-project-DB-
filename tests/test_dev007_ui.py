"""CIF education, filters, responsibility actions and a strictly read-only view."""

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from db.repositories.medical_act_repository import CIFViolationError
from db.repositories.common import ConcurrentEditError,RepositoryError
from tests.test_dev007_services import CONTEXT,ORIGINAL


ROOT=Path(__file__).resolve().parents[1]
CONTEXT_ROW={**CONTEXT,'patient':'Patient fictif','numeroChambre':'201','numeroLit':'A','label':'Séjour fictif'}
ASSIGNMENT={**ORIGINAL,'idPatient':5,'dateAdmission':CONTEXT['dateAdmission'],'dateSortie':None,
    'patient':'Patient fictif','libelleActe':'Acte fictif','cout':0,'medecin':'Médecin fictif'}
OPTIONS=dict(patients=[{'idPatient':5,'label':'Patient fictif'}],
    doctors=[{'idMedecin':1,'label':'Médecin fictif'},{'idMedecin':2,'label':'Autre médecin fictif'}],
    acts=[{'idActe':2,'label':'Acte fictif'},{'idActe':3,'label':'Autre acte fictif'}])


@pytest.fixture
def mocks():
    with patch('db.repositories.medical_act_repository.filter_options',return_value=OPTIONS), \
         patch('db.repositories.medical_act_repository.hospitalizations',return_value=[CONTEXT_ROW]) as stays, \
         patch('db.repositories.medical_act_repository.list_assignments',return_value=dict(rows=[ASSIGNMENT],total=1,page=0)) as listing, \
         patch('db.repositories.medical_act_repository.hospitalization_detail',return_value=dict(hospitalization=CONTEXT_ROW,assignments=[ASSIGNMENT])) as detail, \
         patch('db.repositories.medical_act_repository.list_acts',return_value=dict(rows=[dict(idActe=2,libelleActe='Acte fictif',cout=0)],total=1,page=0)) as catalog, \
         patch('db.repositories.medical_act_repository.add_assignment') as add, \
         patch('db.repositories.medical_act_repository.reassign') as reassign, \
         patch('db.repositories.medical_act_repository.remove_assignment') as remove:
        yield stays,listing,detail,catalog,add,reassign,remove


def open_assignment():
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    app.selectbox(key='ma_selected_pair').set_value((4,2)).run()
    assert not app.exception
    return app


def test_assignment_filters_without_technical_explanation(mocks):
    _,listing,*_=mocks
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    assert not app.exception
    assert not app.code
    assert not any('comprendre la CIF' in item.label for item in app.expander)
    app.selectbox(key='ma_filter_patient').set_value(5)
    app.selectbox(key='ma_filter_stay').set_value(4)
    app.selectbox(key='ma_filter_act').set_value(2)
    app.selectbox(key='ma_filter_doctor').set_value(1)
    app.text_input(key='ma_search').set_value('%_fictif')
    app.button(key='ma_filter_submit').click().run()
    assert listing.call_args.kwargs==dict(search='%_fictif',patient=5,hospitalization=4,act=2,doctor=1,page=0)


def test_new_assignment_validates_then_saves_and_resets(mocks):
    *_,add,_,_=mocks
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    app.segmented_control(key='ma_mode').set_value('Nouvelle affectation').run()
    app.selectbox(key='ma_add_stay').set_value(4).run()
    app.button(key='ma_add_submit').click().run()
    assert app.error and not app.exception
    add.assert_not_called()
    app.selectbox(key='ma_add_1_act').set_value(3)
    app.selectbox(key='ma_add_1_doctor').set_value(2)
    app.button(key='ma_add_submit').click().run()
    assert app.success and not app.exception
    assert add.call_args.args==(4,3,2)
    assert app.selectbox(key='ma_add_2_act').value is None


def test_duplicate_cif_feedback_retains_selected_values(mocks):
    *_,add,_,_=mocks
    add.side_effect=CIFViolationError('CIF : le couple possède déjà un médecin. Utilisez Réaffecter.')
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    app.segmented_control(key='ma_mode').set_value('Nouvelle affectation').run()
    app.selectbox(key='ma_add_stay').set_value(4).run()
    app.selectbox(key='ma_add_1_act').set_value(2)
    app.selectbox(key='ma_add_1_doctor').set_value(2)
    app.button(key='ma_add_submit').click().run()
    assert app.error and 'CIF' in app.error[0].value and not app.exception
    assert app.selectbox(key='ma_add_1_doctor').value==2


def test_reassign_uses_original_and_preserves_stale_form(mocks):
    *_,reassign,_=mocks
    reassign.side_effect=ConcurrentEditError('Le responsable a changé. Rechargez l’affectation.')
    app=open_assignment()
    revision=app.session_state['ma_revision']
    key=f'ma_reassign_4_2_{revision}_doctor'
    app.selectbox(key=key).set_value(2)
    app.button(key='ma_reassign_submit').click().run()
    assert app.error and not app.exception and app.selectbox(key=key).value==2
    assert reassign.call_args.args==(4,2,2)
    assert reassign.call_args.kwargs['original']==ASSIGNMENT
    reassign.side_effect=None
    app.button(key='ma_reassign_submit').click().run()
    assert app.success and not app.exception


def test_removal_requires_confirmation_before_repository_access(mocks):
    *_,remove=mocks
    app=open_assignment()
    app.segmented_control(key='ma_action_4_2').set_value('Retirer').run()
    app.button(key='ma_remove_submit').click().run()
    assert app.error and not app.exception
    remove.assert_not_called()
    revision=app.session_state['ma_revision']
    app.checkbox(key=f'ma_remove_4_2_{revision}_confirm').set_value(True)
    app.button(key='ma_remove_submit').click().run()
    assert app.success and not app.exception
    assert remove.call_args.args==(4,2)
    assert remove.call_args.kwargs['original']==ASSIGNMENT


def test_confirmation_never_transfers_to_another_pair(mocks):
    _,listing,detail,*_=mocks
    other={**ASSIGNMENT,'idActe':3,'libelleActe':'Autre acte fictif'}
    listing.return_value=dict(rows=[ASSIGNMENT,other],total=2,page=0)
    detail.return_value=dict(hospitalization=CONTEXT_ROW,assignments=[ASSIGNMENT,other])
    app=open_assignment()
    app.segmented_control(key='ma_action_4_2').set_value('Retirer').run()
    revision=app.session_state['ma_revision']
    app.checkbox(key=f'ma_remove_4_2_{revision}_confirm').set_value(True)
    app.selectbox(key='ma_selected_pair').set_value((4,3)).run()
    app.segmented_control(key='ma_action_4_3').set_value('Retirer').run()
    revision=app.session_state['ma_revision']
    assert not app.checkbox(key=f'ma_remove_4_3_{revision}_confirm').value


def test_read_only_stay_view_and_catalog_never_expose_write_actions(mocks):
    stays,_,_,catalog,add,reassign,remove=mocks
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    app.segmented_control(key='ma_mode').set_value('Vue par séjour').run()
    app.selectbox(key='ma_read_patient').set_value(5).run()
    assert stays.call_args.args==(5,)
    app.selectbox(key='ma_read_stay').set_value(4).run()
    assert app.dataframe and not app.exception
    assert not any(button.key in ('ma_add_submit','ma_reassign_submit','ma_remove_submit') for button in app.button)
    app.segmented_control(key='ma_mode').set_value('Types d’actes').run()
    app.text_input(key='ma_catalog_search').set_value('fictif')
    app.button(key='ma_catalog_search_submit').click().run()
    assert catalog.call_args.args==('fictif',)
    add.assert_not_called(); reassign.assert_not_called(); remove.assert_not_called()


def test_changed_stay_requires_explicit_context_reload(mocks):
    _,_,detail,*_=mocks
    app=open_assignment()
    detail.return_value=dict(hospitalization={**CONTEXT_ROW,'idLit':6},assignments=[ASSIGNMENT])
    app.run()
    assert app.warning and not app.exception
    assert not any(button.key=='ma_reassign_submit' for button in app.button)
    app.button(key='ma_refresh').click().run()
    assert not app.exception and app.button(key='ma_reassign_submit')


def test_empty_assignments_and_safe_database_error(mocks):
    _,listing,*_=mocks
    listing.return_value=dict(rows=[],total=0,page=0)
    app=AppTest.from_file(ROOT/'pages/medical_acts.py').run()
    assert app.info and not app.exception
    listing.side_effect=RepositoryError('Opération MySQL impossible.')
    app.run()
    assert app.error and not app.exception
