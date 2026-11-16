"""Consultation directory, details, optional links and conflict-safe editing."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, surface_form, workflow_hint



from db.repositories import consultation_repository as repository
from db.repositories.clinical_common import lookup_options
from db.repositories.common import RepositoryError
from services.consultation_service import save_consultation
from services.patient_service import ValidationError
from ui.clinical_forms import consultation_fields, consultation_owners, edit_snapshot, pagination, saved


page_header('Consultations', 'Du premier échange au diagnostic, gardez le fil des soins.', section='PARCOURS PATIENT', action='Nouvelle consultation', mode_key='consult_mode', mode_value='Nouvelle consultation')
if st.session_state.get('consult_saved'):
    st.success(st.session_state.pop('consult_saved'))
mode = st.segmented_control('Espace consultations', ['Historique', 'Nouvelle consultation'], default=None if 'consult_mode' in st.session_state else 'Historique', key='consult_mode')
try:
    options = lookup_options()
    if mode == 'Nouvelle consultation':
        if not options['patients'] or not options['doctors']:
            st.info('Un patient et un médecin doivent exister avant de créer une consultation.')
            st.stop()
        revision = st.session_state.get('consult_revision', 0)
        prefix = f'consult_add_{revision}'
        workflow_hint('Commencer par le contexte', '1 · Patient et médecin   →   2 · Rendez-vous facultatif   →   3 · Compte rendu')
        patient, doctor = consultation_owners(prefix, options)
        with surface_form('consult_add_form'):
            st.subheader('Enregistrer une consultation')
            values = consultation_fields(prefix, options, patient, doctor)
            submitted = st.form_submit_button('Enregistrer la consultation', type='primary', key='consult_add_submit')
        if submitted:
            try:
                save_consultation(values)
            except (ValidationError, RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('consult', 'Consultation enregistrée avec succès.')
        st.stop()

    with surface_form('consult_search_form'):
        search = st.text_input('Rechercher', placeholder='Patient, médecin, motif, diagnostic ou numéro', key='consult_search', max_chars=200)
        search_submit = st.form_submit_button('Rechercher', icon=':material/search:', key='consult_search_submit')
    if search_submit or 'consult_search_applied' not in st.session_state:
        st.session_state['consult_search_applied'] = search
        st.session_state['consult_page'] = 0
    st.button('Actualiser', icon=':material/refresh:', key='consult_refresh')
    result = repository.list_consultations(st.session_state['consult_search_applied'], page=st.session_state.get('consult_page', 0))
    pagination('consult', result, repository.PAGE_SIZE)
    rows = result['rows']
    if not rows:
        st.info('Aucune consultation ne correspond à votre recherche.')
        st.stop()
    labels = {row['idConsultation']: f"{row['dateHeure']:%d/%m/%Y %H:%M} · {row['patient']} · n° {row['idConsultation']}" for row in rows}
    selected = st.selectbox('Ouvrir une consultation', list(labels), index=None, format_func=lambda item: labels[item], key='consult_selected')
    with st.expander('Répertoire des consultations', expanded=selected is None):
        clinical_table(pd.DataFrame(rows)[['idConsultation', 'dateHeure', 'patient', 'medecin', 'motif', 'codeSalle', 'idRDV']].rename(columns={
            'idConsultation': 'N°', 'dateHeure': 'Date et heure', 'patient': 'Patient', 'medecin': 'Médecin',
            'motif': 'Motif', 'codeSalle': 'Salle', 'idRDV': 'Rendez-vous',
        }), hide_index=True, alt='Historique des consultations correspondant à la recherche')
    if selected is None:
        st.stop()
    row = repository.get_consultation(selected)
    selected_row = next(item for item in rows if item['idConsultation'] == selected)
    with st.container(border=True, key='panel_consultations_1'):
        st.subheader('Détail de la consultation')
        st.text(f"{row['dateHeure']:%d/%m/%Y %H:%M} · {row.get('patient', selected_row['patient'])} · {row.get('medecin', selected_row['medecin'])}")
        st.text(f"Rendez-vous : {row['idRDV'] if row['idRDV'] is not None else 'Aucun'} · Salle : {row.get('codeSalle', selected_row['codeSalle']) or 'Aucune'}")
        st.caption('Motif')
        st.text(row['motif'])
        st.caption('Diagnostic')
        st.text(row['diagnostic'])
    if not st.toggle('Modifier la consultation', key=f'consult_edit_toggle_{selected}'):
        st.session_state.pop('consult_snapshot', None)
        st.stop()
    snapshot, revision = edit_snapshot('consult', row, 'idConsultation')
    prefix = f'consult_edit_{selected}_{revision}'
    patient, doctor = consultation_owners(prefix, options, snapshot)
    st.caption('En changeant le patient ou le médecin, vérifiez de nouveau le lien au rendez-vous.')
    with surface_form(f'consult_edit_form_{selected}_{revision}'):
        values = consultation_fields(prefix, options, patient, doctor, snapshot)
        submitted = st.form_submit_button('Enregistrer les modifications', type='primary', key='consult_edit_submit')
    if submitted:
        try:
            save_consultation(values, consultation_id=selected, original=snapshot)
        except (ValidationError, RepositoryError) as exc:
            st.error(str(exc))
        else:
            saved('consult', 'Consultation mise à jour avec succès.')
except RepositoryError as exc:
    st.error(str(exc))
