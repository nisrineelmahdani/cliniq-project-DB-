"""Medical act types and the exact hospitalization–act -> doctor CIF."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table, page_header, surface_form



from db.repositories import medical_act_repository as repository
from db.repositories.common import RepositoryError
from services import medical_act_service as service
from services.patient_service import ValidationError
from ui.clinical_forms import pagination,record_select,saved
from ui.medical_act_views import assignments_table,hospitalization_context


page_header('Actes médicaux', 'La bonne responsabilité, pour chaque acte et chaque séjour.', section='SÉJOURS & SOINS', action='Nouvelle affectation', mode_key='ma_mode', mode_value='Nouvelle affectation')
if st.session_state.get('ma_saved'):
    st.success(st.session_state.pop('ma_saved'))
mode=st.segmented_control('Espace actes médicaux',['Affectations','Nouvelle affectation','Types d’actes','Vue par séjour'],default=None if 'ma_mode' in st.session_state else 'Affectations',key='ma_mode')
if st.button('Actualiser les listes et le contexte',icon=':material/refresh:',key='ma_refresh'):
    st.session_state.pop('ma_context',None)
    st.session_state.pop('ma_snapshot',None)
try:
    options=repository.filter_options()
    if mode=='Types d’actes':
        with surface_form('ma_catalog_search_form'):
            search=st.text_input('Rechercher un type d’acte',max_chars=200,key='ma_catalog_search')
            applied=st.form_submit_button('Rechercher',key='ma_catalog_search_submit')
        if applied or 'ma_catalog_applied' not in st.session_state:
            st.session_state['ma_catalog_applied']=search
            st.session_state['ma_catalog_page']=0
        result=repository.list_acts(st.session_state['ma_catalog_applied'],page=st.session_state.get('ma_catalog_page',0))
        pagination('ma_catalog',result,repository.PAGE_SIZE)
        st.caption('Catalogue en lecture seule. Le coût affiché est celui du type d’acte, sans compter des réalisations individuelles.')
        if result['rows']:
            clinical_table(pd.DataFrame(result['rows']).rename(columns={'idActe':'N°','libelleActe':'Type d’acte','cout':'Coût'}),hide_index=True,alt='Types d’actes médicaux du catalogue approuvé')
        else:
            st.info('Aucun type d’acte ne correspond à cette recherche.')
        st.stop()

    if mode=='Vue par séjour':
        patient=record_select('Filtrer les séjours par patient',options['patients'],'idPatient','ma_read_patient')
        stays=repository.hospitalizations(patient)
        selected=record_select('Séjour à consulter',stays,'idHospitalisation','ma_read_stay')
        st.caption('Vue en lecture seule des responsabilités affectées au séjour ; aucune réalisation individuelle n’est enregistrée.')
        if selected is None:
            st.info('Sélectionnez un séjour pour afficher ses actes et leurs responsables.')
        else:
            detail=repository.hospitalization_detail(selected)
            hospitalization_context(detail['hospitalization'])
            assignments_table(detail['assignments'],alt='Responsabilités médicales affectées au séjour sélectionné')
        st.stop()

    stays=repository.hospitalizations()
    if mode=='Nouvelle affectation':
        st.session_state.pop('ma_snapshot',None)
        if not stays or not options['acts'] or not options['doctors']:
            st.info('Un séjour, un type d’acte et un médecin doivent exister avant une affectation.')
            st.stop()
        selected=record_select('Séjour',stays,'idHospitalisation','ma_add_stay')
        if selected is None:
            st.info('Choisissez un séjour pour afficher son contexte et désigner un responsable.')
            st.stop()
        detail=repository.hospitalization_detail(selected)
    else:
        with surface_form('ma_filters_form'):
            search=st.text_input('Rechercher une affectation',placeholder='Patient, médecin, acte ou numéro de séjour',max_chars=200,key='ma_search')
            with st.expander('Affiner la recherche', icon=':material/tune:'):
                left,right=st.columns(2)
                with left:
                    patient=record_select('Patient',options['patients'],'idPatient','ma_filter_patient')
                    act=record_select('Acte médical',options['acts'],'idActe','ma_filter_act')
                with right:
                    hospitalization=record_select('Hospitalisation',stays,'idHospitalisation','ma_filter_stay')
                    doctor=record_select('Médecin responsable',options['doctors'],'idMedecin','ma_filter_doctor')
            applied=st.form_submit_button('Appliquer les filtres',icon=':material/filter_list:',key='ma_filter_submit')
        if applied or 'ma_filters' not in st.session_state:
            st.session_state['ma_filters']=dict(search=search,patient=patient,hospitalization=hospitalization,act=act,doctor=doctor)
            st.session_state['ma_assignments_page']=0
        result=repository.list_assignments(**st.session_state['ma_filters'],page=st.session_state.get('ma_assignments_page',0))
        pagination('ma_assignments',result,repository.PAGE_SIZE)
        assignments_table(result['rows'],alt='Responsabilités médicales correspondant aux filtres')
        if not result['rows']:
            st.stop()
        pairs={(row['idHospitalisation'],row['idActe']):row for row in result['rows']}
        pair=st.selectbox('Ouvrir une affectation',list(pairs),index=None,
            format_func=lambda item:f"Séjour n° {item[0]} · {pairs[item]['libelleActe']} · acte n° {item[1]}",key='ma_selected_pair')
        if pair is None:
            st.stop()
        selected,act_id=pair
        detail=repository.hospitalization_detail(selected)

    current_context=detail['hospitalization']
    context=st.session_state.get('ma_context')
    if context is None or context['idHospitalisation']!=selected:
        context=current_context.copy()
        st.session_state['ma_context']=context
        st.session_state.pop('ma_snapshot',None)
        st.session_state['ma_revision']=st.session_state.get('ma_revision',0)+1
    if any(context[key]!=current_context[key] for key in repository.CONTEXT_FIELDS):
        st.warning('Le séjour a changé depuis son ouverture. Actualisez le contexte avant de continuer.')
        st.stop()
    hospitalization_context(current_context)
    if mode=='Nouvelle affectation':
        with st.container(border=True):
            st.subheader('Responsabilités déjà affectées à ce séjour')
            assignments_table(detail['assignments'],alt='Affectations existantes avant une nouvelle désignation')
        revision=st.session_state['ma_revision']
        with surface_form('ma_add_form'):
            st.subheader('Désigner un médecin responsable')
            act=record_select('Type d’acte',options['acts'],'idActe',f'ma_add_{revision}_act')
            doctor=record_select('Médecin responsable',options['doctors'],'idMedecin',f'ma_add_{revision}_doctor')
            submitted=st.form_submit_button('Affecter la responsabilité',type='primary',key='ma_add_submit')
        if submitted:
            try:
                service.add_assignment(selected,act,doctor,context=context)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('ma','Responsabilité médicale affectée avec succès.')
        st.stop()

    current=next((row for row in detail['assignments'] if row['idActe']==act_id),None)
    if current is None:
        st.warning('Cette affectation n’existe plus. Actualisez la liste.')
        st.stop()
    snapshot=st.session_state.get('ma_snapshot')
    if snapshot is None or (snapshot['idHospitalisation'],snapshot['idActe'])!=pair:
        snapshot=current.copy()
        st.session_state['ma_snapshot']=snapshot
        st.session_state['ma_revision']=st.session_state.get('ma_revision',0)+1
    st.subheader(current['libelleActe'])
    st.caption('Médecin actuellement responsable')
    st.text(current['medecin'])
    if st.button('Recharger cette affectation',key='ma_reload_pair'):
        st.session_state.pop('ma_snapshot',None)
        st.rerun()
    revision=st.session_state['ma_revision']
    action=st.segmented_control('Action',['Réaffecter','Retirer'],default='Réaffecter',key=f'ma_action_{selected}_{act_id}')
    if action=='Retirer':
        with surface_form(f'ma_remove_form_{selected}_{act_id}_{revision}'):
            st.warning('Le retrait supprime uniquement cette responsabilité. Le séjour, le type d’acte et le médecin sont conservés.')
            confirmed=st.checkbox('Je confirme le retrait de cette affectation.',key=f'ma_remove_{selected}_{act_id}_{revision}_confirm')
            submitted=st.form_submit_button('Retirer l’affectation',type='primary',key='ma_remove_submit')
        if submitted:
            try:
                service.remove_assignment(selected,act_id,original=snapshot,context=context,confirmed=confirmed)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('ma','Affectation retirée. Les autres données sont conservées.')
    else:
        with surface_form(f'ma_reassign_form_{selected}_{act_id}_{revision}'):
            doctor=record_select('Nouveau médecin responsable',options['doctors'],'idMedecin',f'ma_reassign_{selected}_{act_id}_{revision}_doctor',initial=snapshot['idMedecin'])
            st.caption('La réaffectation modifie la ligne existante. Le couple séjour–acte reste inchangé.')
            submitted=st.form_submit_button('Réaffecter la responsabilité',type='primary',key='ma_reassign_submit')
        if submitted:
            try:
                service.reassign(selected,act_id,doctor,original=snapshot,context=context)
            except (ValidationError,RepositoryError) as exc:
                st.error(str(exc))
            else:
                saved('ma','Médecin responsable mis à jour sur l’affectation existante.')
except RepositoryError as exc:
    st.error(str(exc))
