"""Date-driven availability controls; actual assignment is rechecked on commit."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from ui.design import clinical_table

from services import hospitalization_service as service
from services.clinic_clock import clinic_now
from services.patient_service import ValidationError
from ui.clinical_forms import record_select
from ui.design import surface_form, status_badge


def timestamp_fields(prefix, label, initial=None):
    initial = initial or clinic_now().replace(second=0, microsecond=0)
    left, right = st.columns(2)
    with left:
        day = st.date_input(f'Date {label}', value=initial.date(), min_value=date(1000,1,1), max_value=date(9999,12,31), format='DD/MM/YYYY', key=f'{prefix}_date')
    with right:
        clock = st.time_input(f'Heure {label}', value=initial.time(), step=60, key=f'{prefix}_time')
    return datetime.combine(day,clock) if day is not None and clock is not None else None


def hospitalization_form(prefix, options, *, initial=None, submit_key):
    initial = initial or {}
    st.markdown(':material/person: **Le patient et son séjour**')
    patient = record_select('Patient', options['patients'], 'idPatient', f'{prefix}_patient', initial=initial.get('idPatient'), disabled=bool(initial))
    admission = timestamp_fields(f'{prefix}_admission', 'd’admission', initial.get('dateAdmission'))
    has_discharge = st.toggle('Renseigner une date de sortie', value=initial.get('dateSortie') is not None, key=f'{prefix}_has_discharge')
    discharge = None
    if has_discharge:
        discharge = timestamp_fields(f'{prefix}_discharge', 'de sortie', initial.get('dateSortie') or admission)
        if discharge is None:
            st.warning('Renseignez la date et l’heure de sortie, ou désactivez cette option.')
            return None, False
    st.markdown(':material/bed: **Choisir une place disponible**')
    room = record_select('Chambre', options['rooms'], 'idChambre', f'{prefix}_room', initial=initial.get('idChambre'))
    try:
        beds = service.available_beds(admission, discharge, room=room, exclude_id=initial.get('idHospitalisation'))
    except ValidationError as exc:
        st.warning(str(exc))
        return None, False
    st.caption('Les lits proposés sont libres sur toute la période choisie. Sans sortie, la réservation reste ouverte. La disponibilité sera revérifiée à la confirmation.')
    if not beds:
        st.info('Aucun lit disponible pour cette période et cette chambre. Modifiez les dates ou la chambre.')
        return None, False
    clinical_table(pd.DataFrame(beds)[['numeroChambre','numeroLit','typeChambre']].rename(columns={
        'numeroChambre':'Chambre','numeroLit':'Lit','typeChambre':'Type',
    }), hide_index=True, alt='Lits disponibles sur l’ensemble de la période demandée')
    st.success(f'{len(beds)} lit(s) disponible(s) pour cette période.')
    with surface_form(f'{prefix}_form'):
        bed = record_select('Lit disponible', beds, 'idLit', f'{prefix}_bed', initial=initial.get('idLit'))
        submitted = st.form_submit_button('Enregistrer le séjour', type='primary', key=submit_key)
    return dict(idPatient=patient,idLit=bed,dateAdmission=admission,dateSortie=discharge), submitted


def stays_table(rows, *, alt):
    if not rows:
        st.info('Aucune hospitalisation à afficher pour ces critères.')
        return
    clinical_table(pd.DataFrame(rows)[['idHospitalisation','patient','numeroChambre','numeroLit','dateAdmission','dateSortie','statut']].rename(columns={
        'idHospitalisation':'N°','patient':'Patient','numeroChambre':'Chambre','numeroLit':'Lit',
        'dateAdmission':'Admission','dateSortie':'Sortie','statut':'Statut',
    }), hide_index=True, alt=alt)
