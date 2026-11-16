"""New presentation interactions preserve existing workflows and safe rendering."""

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

from tests.test_dev003_ui import patient_mocks, dashboard_data
from tests.test_dev004_ui import clinical_mocks
from tests.test_dev006_ui import mocks as hospitalization_mocks
from tests.test_dev007_ui import mocks as act_mocks

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('page,fixture,key,value,submit', [
    ('patients','patient_mocks','patient_mode','Nouveau patient','patient_add_submit'),
    ('appointments','clinical_mocks','appt_mode','Nouveau rendez-vous','appt_add_submit'),
    ('consultations','clinical_mocks','consult_mode','Nouvelle consultation','consult_add_submit'),
    ('hospitalizations','hospitalization_mocks','hosp_mode','Nouvelle admission','hosp_add_submit'),
    ('medical_acts','act_mocks','ma_mode','Nouvelle affectation',None),
])
def test_primary_header_action_opens_workflow(request,page,fixture,key,value,submit):
    request.getfixturevalue(fixture)
    app = AppTest.from_file(ROOT/'pages'/f'{page}.py').run()
    app.button(key=f'{key}_primary').click().run()
    assert not app.exception
    assert app.segmented_control(key=key).value == value
    if submit:
        assert app.button(key=submit)
    else:
        assert app.selectbox(key='ma_add_stay')


def test_zero_capacity_is_a_true_empty_state_without_invented_metrics():
    data = dashboard_data()
    data['metrics'] = {key:0 for key in data['metrics']}
    with patch('ui.dashboard_data.load_dashboard',return_value=data):
        app = AppTest.from_file(ROOT/'app.py').run()
    assert not app.exception
    assert [metric.value for metric in app.metric] == ['0'] * 6
    assert any('Aucun lit enregistré' in info.value for info in app.info)


def test_custom_status_value_cannot_inject_html():
    from ui.design import status_badge
    with patch('ui.design.st.html') as html:
        status_badge('<script>alert("test")</script>')
    value = html.call_args.args[0]
    assert '<script>' not in value
    assert '&lt;script&gt;' in value
    assert 'status-neutral' in value


def test_single_page_has_no_inert_pagination(clinical_mocks):
    app = AppTest.from_file(ROOT/'pages/appointments.py').run()
    assert not app.exception
    assert not any(button.key in ('appt_previous','appt_next') for button in app.button)


def test_multiple_pages_keep_functional_pagination(clinical_mocks):
    listing, *_ = clinical_mocks
    listing.return_value['total'] = 26
    app = AppTest.from_file(ROOT/'pages/appointments.py').run()
    assert app.button(key='appt_previous').disabled
    assert not app.button(key='appt_next').disabled
    app.button(key='appt_next').click().run()
    assert not app.exception
    assert listing.call_args.kwargs['page'] == 1
