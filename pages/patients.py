"""Patient directory, registration, conflict-safe editing and clinical histories."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, empty_state, page_header, section_heading, surface_form, workflow_hint



from db.repositories import patient_repository
from db.repositories.common import RepositoryError
from services import patient_service
from ui.patient_form import patient_fields


page_header('Patients', 'Le bon dossier. Le bon suivi. À chaque étape.', section='PARCOURS PATIENT', action='Nouveau patient', mode_key='patient_mode', mode_value='Nouveau patient')

# Only non-identifying flash messages persist across a successful submit/rerun.
if st.session_state.get('patient_saved'):
    st.success(st.session_state.pop('patient_saved'))
mode = st.segmented_control('Espace patients', ['Répertoire', 'Nouveau patient'],
                            default=None if 'patient_mode' in st.session_state else 'Répertoire', key='patient_mode')
if mode == 'Nouveau patient':
    workflow_hint('Un nouveau dossier, en quelques instants', '1 · Identité   →   2 · Coordonnées   →   3 · Enregistrement')
    with surface_form('patient_add_form', clear_on_submit=False):
        st.subheader('Enregistrer un patient')
        revision = st.session_state.get('patient_add_revision', 0)
        values = patient_fields(f'add_{revision}')
        submitted = st.form_submit_button('Enregistrer le patient', type='primary', key='patient_add_submit')
    if submitted:
        try:
            patient_service.add_patient(values)
        except patient_service.ValidationError as exc:
            st.warning(str(exc))
        except RepositoryError:
            st.error('Enregistrement impossible. Les informations saisies sont conservées ; réessayez après vérification de la connexion.')
        else:
            st.session_state['patient_add_revision'] = revision + 1
            st.session_state['patient_saved'] = 'Patient enregistré avec succès.'
            st.session_state.pop('dashboard_snapshot', None)
            st.rerun()
    st.stop()

with surface_form('patient_search_form'):
    search_col, button_col = st.columns([4, 1], vertical_alignment='bottom')
    with search_col:
        search = st.text_input('Rechercher par nom ou prénom', key='patient_search_input', max_chars=201,
                               placeholder='Nom, prénom ou nom complet')
    with button_col:
        search_submitted = st.form_submit_button('Rechercher', icon=':material/search:', width='stretch')
if search_submitted or 'patient_search' not in st.session_state:
    st.session_state['patient_search'] = search.strip()
    st.session_state['patient_page'] = 0
if st.button('Actualiser le répertoire', icon=':material/refresh:', key='patients_refresh'):
    st.session_state.pop('patient_edit_snapshot', None)

try:
    listing = patient_repository.list_patients(st.session_state['patient_search'], st.session_state.get('patient_page', 0))
except RepositoryError:
    st.error('Le répertoire est indisponible. Vérifiez la connexion MySQL et réessayez.')
    st.stop()

st.session_state['patient_page'] = listing['page']
rows = listing['rows']
st.caption(f"{listing['total']} patient(s) · Page {listing['page'] + 1}")
if not rows:
    st.info('Aucun patient ne correspond à votre recherche. Vous pouvez modifier la recherche ou enregistrer un nouveau patient.')
    st.stop()

directory, record = st.columns([1.15, 1], gap='large')
with directory:
    section_heading('Répertoire', 'Recherchez puis ouvrez le dossier à consulter.', icon='group')
    options = {row['idPatient']: f"{row['nom']} {row['prenom']} · Dossier n° {row['idPatient']}" for row in rows}
    selected = st.selectbox('Ouvrir un dossier', list(options), index=None, placeholder='Sélectionnez un patient',
                             format_func=lambda patient_id: options[patient_id], key='patient_selected')

    clinical_table(pd.DataFrame(rows)[['idPatient', 'nom', 'prenom', 'dateNaissance']].rename(columns={
        'idPatient': 'N°', 'nom': 'Nom', 'prenom': 'Prénom', 'dateNaissance': 'Naissance',
        'telephone': 'Téléphone', 'adresse': 'Adresse',
    }), hide_index=True, alt='Répertoire des patients correspondant à la recherche')
    if listing['total'] > patient_repository.PAGE_SIZE:
        with st.container(horizontal=True):
            if st.button('Précédent', disabled=listing['page'] == 0, key='patients_previous'):
                st.session_state['patient_page'] -= 1
                st.rerun()
            if st.button('Suivant', disabled=(listing['page'] + 1) * patient_repository.PAGE_SIZE >= listing['total'], key='patients_next'):
                st.session_state['patient_page'] += 1
                st.rerun()

if selected is None:
    with record:
        empty_state('Un dossier à portée de main', 'Sélectionnez un patient dans le répertoire pour retrouver ses informations et son parcours de soins.')
    st.stop()
with record:
    try:
        detail = patient_repository.patient_detail(selected)
    except RepositoryError:
        st.error('Le dossier est indisponible ou a été supprimé. Actualisez le répertoire.')
        st.stop()
    
    patient = detail['patient']
    with st.container(border=True, key='panel_patient_identity'):
        st.subheader('Fiche patient')
        # Text commands keep database values out of HTML and Markdown interpretation.
        st.text(f"{patient['nom']} {patient['prenom']}")
        st.text(f"Naissance : {patient['dateNaissance']:%d/%m/%Y}")
        st.text(f"Téléphone : {patient['telephone']}")
        st.text(f"Adresse : {patient['adresse']}")
        editing = st.toggle('Modifier les informations', key=f'patient_edit_toggle_{selected}')
    
    if not editing:
        st.session_state.pop('patient_edit_snapshot', None)
    else:
        snapshot = st.session_state.get('patient_edit_snapshot')
        if snapshot is None or snapshot['idPatient'] != selected:
            snapshot = patient.copy()
            st.session_state['patient_edit_snapshot'] = snapshot
            st.session_state['patient_edit_revision'] = st.session_state.get('patient_edit_revision', 0) + 1
        revision = st.session_state['patient_edit_revision']
        with surface_form(f'patient_edit_form_{selected}_{revision}'):
            st.subheader('Modifier le dossier')
            values = patient_fields(f'edit_{selected}_{revision}', snapshot)
            submitted = st.form_submit_button('Enregistrer les modifications', type='primary', key='patient_edit_submit')
        if submitted:
            try:
                patient_service.update_patient(selected, values, snapshot)
            except patient_service.ValidationError as exc:
                st.warning(str(exc))
            except RepositoryError as exc:
                # Repository exceptions contain only controlled messages, never connector text.
                st.error(str(exc))
            else:
                st.session_state['patient_saved'] = 'Informations mises à jour avec succès.'
                st.session_state.pop('patient_edit_snapshot', None)
                st.session_state.pop('dashboard_snapshot', None)
                st.rerun()
    
    with st.container(border=True, key='panel_patient_consultations'):
        st.subheader('Historique des consultations')
        if detail['consultations']:
            clinical_table(pd.DataFrame(detail['consultations']).rename(columns={
                'idConsultation': 'N°', 'dateHeure': 'Date et heure', 'motif': 'Motif', 'diagnostic': 'Diagnostic',
                'medecin': 'Médecin', 'idRDV': 'Rendez-vous', 'codeSalle': 'Salle',
            }), hide_index=True, alt='Historique des consultations du patient sélectionné')
        else:
            st.info('Aucune consultation dans ce dossier.')
    with st.container(border=True, key='panel_patient_stays'):
        st.subheader('Historique des hospitalisations')
        if detail['hospitalizations']:
            clinical_table(pd.DataFrame(detail['hospitalizations']).rename(columns={
                'idHospitalisation': 'N°', 'dateAdmission': 'Admission', 'dateSortie': 'Sortie',
                'numeroChambre': 'Chambre', 'numeroLit': 'Lit',
            }), hide_index=True, alt='Historique des séjours hospitaliers du patient sélectionné')
            st.caption('Une sortie vide indique qu’aucune date de sortie n’a été enregistrée.')
        else:
            st.info('Aucune hospitalisation dans ce dossier.')
