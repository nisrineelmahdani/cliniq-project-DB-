"""Clinic overview; every metric and chart uses the existing SQL snapshot."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, section_heading


from db.repositories.common import RepositoryError
from ui.dashboard_data import dashboard_snapshot

page_header('Vue d’ensemble', 'Un regard sur votre clinique. Plus de temps pour vos patients.', section='PILOTAGE / AUJOURD’HUI')
try:
    refresh = st.button('Actualiser', icon=':material/refresh:', key='dashboard_refresh')
    data = dashboard_snapshot(refresh=refresh)
except RepositoryError:
    st.error('Le tableau de bord est indisponible. Vérifiez la connexion MySQL et le chargement du schéma, puis actualisez.')
    st.stop()

with st.container(border=True, key='panel_welcome'):
    welcome, actions = st.columns([3, 2], vertical_alignment='center')
    with welcome:
        st.caption('BIENVENUE CHEZ CLINIQ')
        st.subheader('Une journée bien organisée, des patients bien accompagnés.')
        st.write('Votre activité, vos équipes et vos capacités de soins, réunies au même endroit.')
    with actions:
        if st.session_state.get('cliniq_shell'):
            st.page_link('pages/appointments.py', label='Ouvrir l’agenda', icon=':material/arrow_forward:')
            st.page_link('pages/patients.py', label='Retrouver un patient', icon=':material/person_search:')

st.space('small')
labels = [('patients', 'Patients', 'group'), ('doctors', 'Médecins', 'stethoscope'),
          ('appointments', 'Rendez-vous du jour', 'calendar_month'),
          ('hospitalized', 'Patients hospitalisés', 'ward'), ('occupied_beds', 'Lits occupés', 'bed'),
          ('available_beds', 'Lits disponibles', 'check_circle')]
for offset in (0, 3):
    for column, (field, label, icon) in zip(st.columns(3), labels[offset:offset+3]):
        with column, st.container(border=True, key=f'panel_metric_{field}'):
            st.caption(f':material/{icon}: {"ÉQUIPE & PATIENTS" if offset == 0 else "CAPACITÉ D’ACCUEIL"}')
            st.metric(label, int(data['metrics'][field]))
st.caption('Rendez-vous du jour : tous statuts. Occupation à l’instant indiqué : admission incluse, sortie exclue.')

activity, capacity = st.columns([3, 2])
with activity, st.container(border=True, key='panel_daily'):
    section_heading('Le rythme de votre clinique', 'Consultations quotidiennes · 30 derniers jours', icon='monitoring')
    daily = pd.DataFrame(data['daily']).rename(columns={'jour':'Date','consultations':'Consultations'})
    if not daily.empty and daily['Consultations'].sum() > 0:
        st.area_chart(daily, x='Date', y='Consultations', color='#E84C71', height=230,
                      alt='Nombre réel de consultations par jour sur les trente derniers jours')
    else:
        st.info('Aucune consultation enregistrée sur cette période.')
with capacity, st.container(border=True, key='panel_capacity'):
    section_heading('Des places pour accueillir', 'Occupation au moment de la mise à jour', icon='bed')
    occupied = int(data['metrics']['occupied_beds'])
    available = int(data['metrics']['available_beds'])
    total = occupied + available
    st.subheader(f'{available} lits disponibles')
    if total:
        st.progress(min(1.0, max(0.0, occupied/total)), text=f'{occupied} lits occupés sur {total}')
    else:
        st.info('Aucun lit enregistré dans la clinique.')
    st.caption('La disponibilité tient compte des admissions et des sorties, pas seulement des séjours sans date de fin.')
    if st.session_state.get('cliniq_shell'):
        st.page_link('pages/hospitalizations.py', label='Consulter les chambres et les lits', icon=':material/arrow_forward:')

recent, services = st.columns([3, 2])
with recent, st.container(border=True, key='panel_recent'):
    section_heading('Les derniers rendez-vous de soin', 'Les 10 consultations les plus récentes', icon='stethoscope')
    if data['recent']:
        clinical_table(pd.DataFrame(data['recent']).rename(columns={
            'idConsultation':'N°','dateHeure':'Date et heure','patient':'Patient','medecin':'Médecin','codeSalle':'Salle',
        }), hide_index=True, width='stretch', alt='Consultations récentes avec leurs patients et médecins')
    else:
        st.info('Aucune consultation enregistrée pour le moment.')
with services, st.container(border=True, key='panel_services'):
    section_heading('Les équipes en action', 'Consultations par service · 30 derniers jours', icon='medical_services')
    by_service = pd.DataFrame(data['by_service']).rename(columns={'service':'Service','consultations':'Consultations'})
    if not by_service.empty and by_service['Consultations'].sum() > 0:
        st.bar_chart(by_service, x='Service', y='Consultations', color='#C93F55', horizontal=True, height=240,
                     alt='Nombre réel de consultations par service sur les trente derniers jours')
    else:
        st.info('Aucune activité à afficher sur cette période.')
with st.expander('À propos de ces données'):
    st.caption(f"Données MySQL · {data['as_of']:%d/%m/%Y à %H:%M:%S} · Africa/Casablanca · Cache de session : 30 s · Actualiser pour relire MySQL")
