"""Hospital admissions, discharge/corrections, occupancy and patient history."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, status_badge, surface_form, workflow_hint



from db.repositories import hospitalization_repository as repository
from db.repositories.common import RepositoryError
from services import hospitalization_service as service
from services.clinic_clock import clinic_now
from services.patient_service import ValidationError
from ui.clinical_forms import edit_snapshot, pagination, record_select, saved
from ui.hospitalization_form import hospitalization_form, stays_table, timestamp_fields


page_header('Hospitalisations', 'Accueillir, attribuer un lit et accompagner chaque séjour.', section='SÉJOURS & SOINS', action='Nouvelle admission', mode_key='hosp_mode', mode_value='Nouvelle admission')
if st.session_state.get('hosp_saved'):
    st.success(st.session_state.pop('hosp_saved'))
mode = st.segmented_control('Espace hospitalisations', ['Séjours','Nouvelle admission','Occupation','Historique patient'], default=None if 'hosp_mode' in st.session_state else 'Séjours', key='hosp_mode')
as_of = clinic_now()
try:
    options = repository.filter_options()
    if mode == 'Occupation':
        when = timestamp_fields('hosp_occupancy', 'd’observation', as_of)
        room = record_select('Filtrer par chambre', options['rooms'], 'idChambre', 'hosp_occupancy_room')
        if when is None:
            st.info('Choisissez une date et une heure d’observation.')
            st.stop()
        data = repository.occupancy(when, room=room)
        st.caption(f'Occupation au {when:%d/%m/%Y %H:%M} · Admission incluse, sortie exclue.')
        total = sum(row['total'] for row in data['rooms'])
        occupied = sum(row['occupied'] for row in data['rooms'])
        for col,label,value in zip(st.columns(3), ['Lits','Lits occupés','Lits disponibles'], [total,occupied,total-occupied]):
            with col:
                st.metric(label,int(value),border=True)
        if not data['rooms']:
            st.info('Aucune chambre à afficher.')
            st.stop()
        st.subheader('Vos chambres, en un regard')
        for room_row in data['rooms']:
            with st.container(border=True, key=f"panel_room_{room_row['idChambre']}"):
                st.markdown(f"**Chambre {room_row['numeroChambre']}** · {room_row['typeChambre']}")
                st.caption(f"{room_row['available']} disponible(s) sur {room_row['total']}")
                with st.container(horizontal=True):
                    for bed_row in data['beds']:
                        if bed_row['idChambre'] == room_row['idChambre']:
                            with st.container(width=170):
                                st.caption(f"Lit {bed_row['numeroLit']}")
                                status_badge('Occupé' if bed_row['occupied'] else 'Disponible')
        with st.container(border=True, key='panel_hospitalizations_1'):
            st.subheader('Occupation par chambre')
            clinical_table(pd.DataFrame(data['rooms']).drop(columns=['idChambre']).rename(columns={
                'numeroChambre':'Chambre','typeChambre':'Type','total':'Lits','occupied':'Occupés','available':'Disponibles',
            }), hide_index=True, alt='Occupation réelle des lits par chambre')
        with st.container(border=True, key='panel_hospitalizations_2'):
            st.subheader('État des lits')
            if data['beds']:
                beds = pd.DataFrame(data['beds'])
                beds['occupied'] = beds['occupied'].map({0:'Disponible',1:'Occupé'})
                clinical_table(beds.drop(columns=['idLit','idChambre']).rename(columns={
                    'numeroChambre':'Chambre','numeroLit':'Lit','typeChambre':'Type','occupied':'État',
                }), hide_index=True, alt='Disponibilité des lits à la date et heure choisies')
            else:
                st.info('Aucun lit dans cette sélection.')
        st.stop()
    if mode == 'Historique patient':
        patient = record_select('Patient',options['patients'],'idPatient','hosp_history_patient')
        if patient is None:
            st.info('Sélectionnez un patient pour consulter tous ses séjours.')
        else:
            stays_table(repository.patient_history(patient,as_of), alt='Historique des hospitalisations du patient sélectionné')
        st.stop()
    if mode == 'Nouvelle admission':
        if not options['patients'] or not options['rooms']:
            st.info('Un patient, une chambre et un lit doivent exister avant une admission.')
            st.stop()
        revision = st.session_state.get('hosp_revision',0)
        workflow_hint('Un accueil bien préparé', '1 · Patient et période   →   2 · Chambre   →   3 · Lit disponible')
        st.subheader('Enregistrer une admission')
        values,submitted = hospitalization_form(f'hosp_add_{revision}',options,submit_key='hosp_add_submit')
        if submitted:
            try:
                service.save_hospitalization(values)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('hosp','Hospitalisation enregistrée avec succès.')
        st.stop()

    with surface_form('hosp_filters_form'):
        search = st.text_input('Rechercher un séjour',placeholder='Patient, chambre, lit ou numéro',max_chars=200,key='hosp_search')
        with st.expander('Affiner la recherche', icon=':material/tune:'):
            left,right = st.columns(2)
            with left:
                patient = record_select('Patient',options['patients'],'idPatient','hosp_filter_patient')
                from_day = st.date_input('Admissions à partir du',value=None,format='DD/MM/YYYY',key='hosp_filter_from')
            with right:
                room = record_select('Chambre',options['rooms'],'idChambre','hosp_filter_room')
                to_day = st.date_input('Admissions jusqu’au',value=None,format='DD/MM/YYYY',key='hosp_filter_to')
            status = st.selectbox('Statut du séjour',[None,'En cours','Terminée','Prévue'],format_func=lambda item:'Tous les séjours' if item is None else item,key='hosp_filter_status')
        applied = st.form_submit_button('Appliquer les filtres',icon=':material/filter_list:',key='hosp_filter_submit')
    if applied or 'hosp_filters' not in st.session_state:
        try:
            service.validate_period(from_day,to_day)
        except ValidationError as exc:
            st.warning(str(exc))
            st.stop()
        st.session_state['hosp_filters'] = dict(search=search,patient=patient,room=room,from_day=from_day,to_day=to_day,status=status)
        st.session_state['hosp_page'] = 0
    if st.button('Actualiser les séjours',icon=':material/refresh:',key='hosp_refresh'):
        st.session_state.pop('hosp_snapshot',None)
    result = repository.list_hospitalizations(as_of,**st.session_state['hosp_filters'],page=st.session_state.get('hosp_page',0))
    pagination('hosp',result,repository.PAGE_SIZE)
    if not result['rows']:
        stays_table(result['rows'],alt='Séjours hospitaliers correspondant aux filtres')
        st.stop()
    labels = {row['idHospitalisation']:f"{row['dateAdmission']:%d/%m/%Y %H:%M} · {row['patient']} · n° {row['idHospitalisation']}" for row in result['rows']}
    selected = st.selectbox('Ouvrir un séjour',list(labels),index=None,format_func=lambda item:labels[item],key='hosp_selected')
    with st.expander('Répertoire des séjours', expanded=selected is None):
        stays_table(result['rows'],alt='Séjours hospitaliers correspondant aux filtres')
    if selected is None:
        st.stop()
    row = repository.get_hospitalization(selected,as_of)
    with st.container(border=True, key='panel_hospitalizations_3'):
        st.subheader('Détail du séjour')
        st.text(row['patient'])
        st.text(f"Chambre {row['numeroChambre']} · Lit {row['numeroLit']}")
        status_badge(row['statut'])
        st.text(f"Admission : {row['dateAdmission']:%d/%m/%Y %H:%M}")
        st.text('Sortie : ' + (row['dateSortie'].strftime('%d/%m/%Y %H:%M') if row['dateSortie'] else 'Non renseignée'))
    action = st.segmented_control('Action',['Détails','Modifier','Sortie'],default='Détails',key=f'hosp_action_{selected}')
    if action == 'Détails':
        st.session_state.pop('hosp_snapshot',None)
        st.subheader('Historique du patient')
        stays_table(repository.patient_history(row['idPatient'],as_of),alt='Tous les séjours du patient de cette hospitalisation')
        st.stop()
    snapshot,revision = edit_snapshot('hosp',row,'idHospitalisation')
    if st.button('Recharger ce séjour',key='hosp_reload'):
        st.session_state.pop('hosp_snapshot',None)
        st.rerun()
    if action == 'Sortie':
        st.subheader('Enregistrer ou corriger la sortie')
        discharge = timestamp_fields(f'hosp_exit_{selected}_{revision}','de sortie',snapshot.get('dateSortie') or as_of)
        if st.button('Enregistrer la sortie',type='primary',key='hosp_discharge_submit'):
            try:
                service.record_discharge(selected,discharge,original=snapshot)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('hosp','Sortie enregistrée avec succès.')
    else:
        st.subheader('Corriger les informations du séjour')
        st.caption('Une correction du lit s’applique à l’ensemble de ce séjour. Le suivi de transferts successifs n’est pas représenté par le modèle actuel.')
        values,submitted = hospitalization_form(f'hosp_edit_{selected}_{revision}',options,initial=snapshot,submit_key='hosp_edit_submit')
        if submitted:
            try:
                service.save_hospitalization(values,hospitalization_id=selected,original=snapshot)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('hosp','Séjour mis à jour avec succès.')
except RepositoryError as exc:
    st.error(str(exc))
