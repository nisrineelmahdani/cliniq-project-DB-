"""Real appointment agenda, filters, registration and editing."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, status_badge, surface_form, workflow_hint



from db.repositories import appointment_repository as repository
from db.repositories.clinical_common import lookup_options
from db.repositories.common import RepositoryError
from services.appointment_service import save_appointment
from services.patient_service import ValidationError
from ui.clinical_forms import appointment_fields, edit_snapshot, pagination, record_select, saved


page_header('Rendez-vous', 'Un agenda lisible pour coordonner patients et équipes.', section='PARCOURS PATIENT', action='Planifier un rendez-vous', mode_key='appt_mode', mode_value='Nouveau rendez-vous')
if st.session_state.get('appt_saved'):
    st.success(st.session_state.pop('appt_saved'))
mode = st.segmented_control('Espace rendez-vous', ['Agenda', 'Nouveau rendez-vous'], default=None if 'appt_mode' in st.session_state else 'Agenda', key='appt_mode')
try:
    options = lookup_options()
    if mode == 'Nouveau rendez-vous':
        if not options['patients'] or not options['doctors']:
            st.info('Un patient et un médecin doivent exister avant de créer un rendez-vous.')
            st.stop()
        revision = st.session_state.get('appt_revision', 0)
        workflow_hint('Organiser une nouvelle visite', '1 · Patient et médecin   →   2 · Créneau et durée   →   3 · Confirmation')
        with surface_form('appt_add_form'):
            st.subheader('Planifier un rendez-vous')
            values = appointment_fields(f'appt_add_{revision}', options)
            submitted = st.form_submit_button('Enregistrer le rendez-vous', type='primary', key='appt_add_submit')
        if submitted:
            try:
                save_appointment(values)
            except (ValidationError, RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('appt', 'Rendez-vous enregistré avec succès.')
        st.stop()

    with surface_form('appt_filters_form'):
        search = st.text_input('Rechercher', placeholder='Patient, médecin, statut ou numéro', key='appt_search', max_chars=200)
        with st.expander('Affiner la recherche', icon=':material/tune:'):
            left, right = st.columns(2)
            with left:
                doctor = record_select('Filtrer par médecin', options['doctors'], 'idMedecin', 'appt_filter_doctor')
                day = st.date_input('Filtrer par date', value=None, key='appt_filter_date', format='DD/MM/YYYY')
            with right:
                patient = record_select('Filtrer par patient', options['patients'], 'idPatient', 'appt_filter_patient')
                status = st.selectbox('Filtrer par statut', [None, *options['statuses']], format_func=lambda item: 'Tous les statuts' if item is None else item, key='appt_filter_status')
        filter_submit = st.form_submit_button('Appliquer les filtres', icon=':material/filter_list:', key='appt_filter_submit')
    if filter_submit or 'appt_filters' not in st.session_state:
        st.session_state['appt_filters'] = dict(search=search, doctor=doctor, patient=patient, day=day, status=status)
        st.session_state['appt_page'] = 0
    st.button('Actualiser', icon=':material/refresh:', key='appt_refresh')
    result = repository.list_appointments(**st.session_state['appt_filters'], page=st.session_state.get('appt_page', 0))
    rows = result['rows']
    pagination('appt', result, repository.PAGE_SIZE)
    if not rows:
        st.info('Aucun rendez-vous pour ces critères. Modifiez les filtres ou planifiez un nouveau rendez-vous.')
        st.stop()
    labels = {row['idRDV']: f"{row['dateHeure']:%d/%m/%Y %H:%M} · {row['patient']} · n° {row['idRDV']}" for row in rows}
    selected = st.selectbox('Ouvrir un rendez-vous', list(labels), index=None, format_func=lambda item: labels[item], key='appt_selected')
    with st.expander('Planning des rendez-vous', expanded=selected is None):
        view = st.segmented_control('Présentation', ['Planning', 'Tableau'], default='Planning', key='appt_view')
        if view == 'Tableau':
            clinical_table(pd.DataFrame(rows)[['idRDV', 'dateHeure', 'fin', 'patient', 'medecin', 'dureePrevue', 'statut']].rename(columns={
                'idRDV': 'N°', 'dateHeure': 'Début', 'fin': 'Fin', 'patient': 'Patient', 'medecin': 'Médecin', 'dureePrevue': 'Minutes', 'statut': 'Statut',
            }), hide_index=True, alt='Rendez-vous correspondant aux filtres')
        else:
            for day in dict.fromkeys(row['dateHeure'].date() for row in rows):
                with st.container(border=True, key=f'panel_agenda_{day}'):
                    st.subheader(day.strftime('%d/%m/%Y'))
                    for row in rows:
                        if row['dateHeure'].date() == day:
                            time_col, person_col, status_col = st.columns([1, 3, 1.4], vertical_alignment='center')
                            with time_col:
                                st.markdown(f"**{row['dateHeure']:%H:%M}**")
                                st.caption(f"{row['dureePrevue']} min")
                            with person_col:
                                st.text(row['patient'])
                                st.caption(row['medecin'])
                            with status_col:
                                status_badge(row['statut'])
                                st.caption(f"RDV n° {row['idRDV']}")
                            st.divider()
    if selected is None:
        st.stop()
    row = repository.get_appointment(selected)
    selected_row = next(item for item in rows if item['idRDV'] == selected)
    with st.container(border=True, key='panel_appointment_context'):
        st.subheader('Votre rendez-vous')
        st.text(selected_row['patient'])
        st.caption(selected_row['medecin'])
        st.text(f"{row['dateHeure']:%d/%m/%Y à %H:%M} · {row['dureePrevue']} minutes")
        status_badge(row['statut'])
    if not st.toggle('Modifier le rendez-vous', key=f'appt_edit_toggle_{selected}'):
        st.session_state.pop('appt_snapshot', None)
        st.stop()
    snapshot, revision = edit_snapshot('appt', row, 'idRDV')
    with surface_form(f'appt_edit_form_{selected}_{revision}'):
        st.subheader('Modifier le créneau')
        values = appointment_fields(f'appt_edit_{selected}_{revision}', options, snapshot)
        submitted = st.form_submit_button('Enregistrer les modifications', type='primary', key='appt_edit_submit')
    if submitted:
        try:
            save_appointment(values, appointment_id=selected, original=snapshot)
        except (ValidationError, RepositoryError) as exc:
            st.error(str(exc))
        else:
            saved('appt', 'Rendez-vous mis à jour avec succès.')
except RepositoryError as exc:
    st.error(str(exc))
