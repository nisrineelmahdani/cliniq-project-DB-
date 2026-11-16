"""CLINIQ healthcare workspace; explicit navigation keeps unfinished pages hidden."""

import streamlit as st

from ui.design import apply_design

st.set_page_config(page_title='CLINIQ · Votre espace de soins',
                   page_icon=':material/health_and_safety:', layout='wide')
apply_design()
st.session_state['cliniq_shell'] = True

with st.sidebar, st.container(key='cliniq_brand'):
    st.markdown('### :material/health_and_safety: CLINIQ')
    st.caption('LE SOIN COMMENCE ICI')

pages = {
    'Pilotage': [st.Page('pages/dashboard.py', title='Vue d’ensemble', icon=':material/space_dashboard:', default=True)],
    'Parcours patient': [
        st.Page('pages/patients.py', title='Patients', icon=':material/group:'),
        st.Page('pages/appointments.py', title='Rendez-vous', icon=':material/calendar_month:'),
        st.Page('pages/consultations.py', title='Consultations', icon=':material/stethoscope:'),
        st.Page('pages/prescriptions.py', title='Prescriptions', icon=':material/medication:')],
    'Séjours & soins': [
        st.Page('pages/hospitalizations.py', title='Hospitalisations', icon=':material/bed:'),
        st.Page('pages/medical_acts.py', title='Actes médicaux', icon=':material/medical_services:')],
}
page = st.navigation(pages, position='hidden')
with st.sidebar, st.container(key='cliniq_nav'):
    for group, links in pages.items():
        st.caption(group.upper())
        for link in links:
            nav_key = 'cliniq_active_nav' if link.url_path == page.url_path else f'cliniq_nav_{link.url_path or "overview"}'
            with st.container(key=nav_key):
                st.page_link(link)
        st.space('small')
with st.sidebar, st.container(key='cliniq_footer'):
    st.markdown(':material/health_and_safety: **Au service de vos patients.**')

with st.container(key='workspace'):
    page.run()
