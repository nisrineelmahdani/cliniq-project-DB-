"""Consultation-centered prescribing through the approved PRESCRIRE association."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, surface_form


from db.repositories import prescription_repository as repository
from db.repositories.common import RepositoryError
from services import prescription_service as service
from services.patient_service import ValidationError
from ui.clinical_forms import pagination, record_select, saved
from ui.prescription_form import prescription_fields


page_header('Prescriptions', 'Une consultation, un contexte clair, des traitements bien suivis.', section='PARCOURS PATIENT')
if st.session_state.get('rx_saved'):
    st.success(st.session_state.pop('rx_saved'))
try:
    options = repository.filter_options()
    with surface_form('rx_consultation_filters'):
        search = st.text_input('Rechercher une consultation', placeholder='Patient, médecin, motif, diagnostic ou numéro', max_chars=200, key='rx_search')
        with st.expander('Affiner la recherche', icon=':material/tune:'):
            left, right = st.columns(2)
            with left:
                patient = record_select('Patient', options['patients'], 'idPatient', 'rx_filter_patient')
                day = st.date_input('Date de consultation', value=None, format='DD/MM/YYYY', key='rx_filter_date')
            with right:
                doctor = record_select('Médecin', options['doctors'], 'idMedecin', 'rx_filter_doctor')
                has_medications = st.selectbox('Médicaments prescrits', [None, True, False],
                    format_func=lambda item: 'Toutes les consultations' if item is None else ('Avec médicaments' if item else 'Sans médicament'), key='rx_filter_prescribed')
        apply_filters = st.form_submit_button('Rechercher', icon=':material/search:', key='rx_filter_submit')
    if apply_filters or 'rx_filters' not in st.session_state:
        st.session_state['rx_filters'] = dict(search=search, doctor=doctor, patient=patient, day=day, prescribed=has_medications)
        st.session_state['rx_consults_page'] = 0
    if st.button('Actualiser le contexte et les listes', icon=':material/refresh:', key='rx_refresh'):
        st.session_state.pop('rx_context', None)
        st.session_state.pop('rx_snapshot', None)
    consultations = repository.list_consultations(**st.session_state['rx_filters'], page=st.session_state.get('rx_consults_page', 0))
    pagination('rx_consults', consultations, repository.PAGE_SIZE)
    if not consultations['rows']:
        st.info('Aucune consultation ne correspond à ces critères. Les consultations sans médicament sont également accessibles ici.')
        st.stop()
    labels = {row['idConsultation']: f"{row['dateHeure']:%d/%m/%Y %H:%M} · {row['patient']} · n° {row['idConsultation']}" for row in consultations['rows']}
    selected = st.selectbox('Sélectionner une consultation', list(labels), index=None,
                             format_func=lambda item: labels[item], key='rx_consultation')
    with st.expander('Répertoire des consultations', expanded=selected is None):
        clinical_table(pd.DataFrame(consultations['rows']).rename(columns={
            'idConsultation': 'N°', 'dateHeure': 'Date et heure', 'patient': 'Patient', 'medecin': 'Médecin', 'medications': 'Médicaments',
        }), hide_index=True, alt='Consultations et nombre de médicaments prescrits')
    if selected is None:
        st.stop()
    detail = repository.consultation_detail(selected)
    current_context = detail['consultation']
    context = st.session_state.get('rx_context')
    if context is None or context['idConsultation'] != selected:
        context = current_context.copy()
        st.session_state['rx_context'] = context
        st.session_state.pop('rx_snapshot', None)
        st.session_state['rx_revision'] = st.session_state.get('rx_revision', 0) + 1
    if any(context[key] != current_context[key] for key in repository.CONTEXT_FIELDS):
        st.warning('La consultation a changé depuis son ouverture. Utilisez « Actualiser le contexte et les listes » avant de continuer.')
        st.stop()
    with st.container(border=True, key='panel_prescriptions_1'):
        st.subheader('Contexte de la consultation')
        left, right = st.columns(2)
        with left:
            st.caption('Patient')
            st.text(current_context['patient'])
            st.caption('Consultation')
            st.text(f"{current_context['dateHeure']:%d/%m/%Y %H:%M} · n° {selected}")
        with right:
            st.caption('Médecin')
            st.text(current_context['medecin'])
            st.caption('Diagnostic')
            st.text(current_context['diagnostic'])
    prescribed = detail['prescriptions']
    with st.container(border=True, key='panel_prescriptions_2'):
        st.subheader('Médicaments prescrits')
        if prescribed:
            clinical_table(pd.DataFrame(prescribed)[['nomMedicament', 'forme', 'dosage', 'quantite', 'posologie', 'duree']].rename(columns={
                'nomMedicament': 'Médicament', 'forme': 'Forme', 'dosage': 'Dosage', 'quantite': 'Quantité', 'posologie': 'Posologie', 'duree': 'Durée (jours)',
            }), hide_index=True, alt='Médicaments prescrits pendant la consultation sélectionnée')
        else:
            st.info('Aucun médicament prescrit pour cette consultation. Vous pouvez en ajouter ci-dessous.')
    mode = st.segmented_control('Gérer les médicaments', ['Ajouter', 'Modifier / retirer'], default='Ajouter', key='rx_mode')
    if mode != 'Modifier / retirer':
        st.session_state.pop('rx_snapshot', None)
        with surface_form('rx_medication_filters'):
            med_search = st.text_input('Rechercher un médicament', placeholder='Nom, forme ou dosage', max_chars=200, key='rx_med_search')
            med_form = st.selectbox('Forme', [None, *options['forms']], format_func=lambda item: 'Toutes les formes' if item is None else item, key='rx_med_form')
            available = st.checkbox('Afficher uniquement les médicaments non prescrits ici', value=True, key='rx_available')
            apply_med_filters = st.form_submit_button('Filtrer le catalogue', key='rx_med_filter_submit')
        if apply_med_filters or 'rx_med_filters' not in st.session_state:
            st.session_state['rx_med_filters'] = dict(search=med_search, form=med_form, available_only=available)
            st.session_state['rx_meds_page'] = 0
        medications = repository.list_medications(selected, **st.session_state['rx_med_filters'], page=st.session_state.get('rx_meds_page', 0))
        pagination('rx_meds', medications, repository.PAGE_SIZE)
        if not medications['rows']:
            st.info('Aucun médicament pour ces critères. Modifiez les filtres ; seuls les médicaments existants peuvent être ajoutés.')
            st.stop()
        clinical_table(pd.DataFrame(medications['rows']).rename(columns={
            'idMedicament': 'N°', 'nomMedicament': 'Médicament', 'forme': 'Forme', 'dosage': 'Dosage', 'assigned': 'Déjà prescrit ici',
        }), hide_index=True, alt='Catalogue des médicaments correspondant aux filtres')
        eligible = {row['idMedicament']: f"{row['nomMedicament']} · {row['forme']} · {row['dosage']} · n° {row['idMedicament']}" for row in medications['rows'] if not row['assigned']}
        if not eligible:
            st.info('Les médicaments affichés sont déjà prescrits ici. Passez à « Modifier / retirer » pour les mettre à jour.')
            st.stop()
        revision = st.session_state.get('rx_revision', 0)
        with surface_form('rx_add_form'):
            st.subheader('Ajouter un médicament')
            medication = st.selectbox('Médicament', list(eligible), index=None, format_func=lambda item: eligible[item], key=f'rx_add_{revision}_medication')
            values = prescription_fields(f'rx_add_{revision}')
            submitted = st.form_submit_button('Ajouter à la consultation', type='primary', key='rx_add_submit')
        if submitted:
            try:
                service.add_prescription(selected, medication, values, context=context)
            except (ValidationError, RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('rx', 'Médicament ajouté à la consultation avec succès.')
        st.stop()
    if not prescribed:
        st.info('Aucun médicament à modifier ou à retirer pour cette consultation.')
        st.stop()
    pairs = {row['idMedicament']: row for row in prescribed}
    chosen = st.selectbox('Médicament prescrit', list(pairs), index=None,
                           format_func=lambda item: f"{pairs[item]['nomMedicament']} · n° {item}", key='rx_prescribed')
    if chosen is None:
        st.stop()
    snapshot = st.session_state.get('rx_snapshot')
    if snapshot is None or (snapshot['idConsultation'], snapshot['idMedicament']) != (selected, chosen):
        snapshot = pairs[chosen].copy()
        st.session_state['rx_snapshot'] = snapshot
        st.session_state['rx_revision'] = st.session_state.get('rx_revision', 0) + 1
    if st.button('Recharger les valeurs de ce médicament', key='rx_reload_pair'):
        st.session_state.pop('rx_snapshot', None)
        st.rerun()
    revision = st.session_state['rx_revision']
    action = st.segmented_control('Action', ['Modifier', 'Retirer'], default='Modifier', key=f'rx_action_{selected}_{chosen}')
    if action == 'Retirer':
        with surface_form(f'rx_remove_form_{selected}_{chosen}_{revision}'):
            st.warning('Le retrait supprimera uniquement ce médicament de cette consultation. Le catalogue restera intact.')
            confirmed = st.checkbox('Je confirme le retrait de ce médicament pour cette consultation.', key=f'rx_remove_{selected}_{chosen}_{revision}_confirm')
            submitted = st.form_submit_button('Retirer le médicament', type='primary', key='rx_remove_submit')
        if submitted:
            try:
                service.remove_prescription(selected, chosen, original=snapshot, context=context, confirmed=confirmed)
            except (ValidationError, RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('rx', 'Médicament retiré de cette consultation.')
    else:
        with surface_form(f'rx_edit_form_{selected}_{chosen}_{revision}'):
            st.subheader('Modifier les instructions prescrites')
            values = prescription_fields(f'rx_edit_{selected}_{chosen}_{revision}', snapshot)
            submitted = st.form_submit_button('Enregistrer les modifications', type='primary', key='rx_edit_submit')
        if submitted:
            try:
                service.update_prescription(selected, chosen, values, original=snapshot, context=context)
            except (ValidationError, RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('rx', 'Prescription mise à jour avec succès.')
except RepositoryError as exc:
    st.error(str(exc))
