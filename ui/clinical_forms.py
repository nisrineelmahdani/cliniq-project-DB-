"""Native CLINIQ form controls shared by appointments and consultations."""

from datetime import date, datetime

import streamlit as st

from db.repositories import consultation_repository
from services.clinic_clock import clinic_now


def record_select(label, rows, id_field, key, *, initial=None, disabled=False):
    labels = {row[id_field]: f"{row['label']} · n° {row[id_field]}" for row in rows}
    keys = list(labels)
    return st.selectbox(label, keys, index=keys.index(initial) if initial in keys else None,
                        format_func=lambda item: labels[item], key=key, disabled=disabled,
                        placeholder='Sélectionnez une valeur')


def date_time_fields(prefix, initial=None):
    initial = initial or clinic_now().replace(second=0, microsecond=0)
    left, right = st.columns(2)
    with left:
        day = st.date_input('Date', value=initial.date(), min_value=date(1000, 1, 1),
                            max_value=date(9999, 12, 31), format='DD/MM/YYYY', key=f'{prefix}_date')
    with right:
        clock = st.time_input('Heure', value=initial.time(), step=60, key=f'{prefix}_time')
    return datetime.combine(day, clock) if day is not None and clock is not None else None


def appointment_fields(prefix, options, initial=None):
    initial = initial or {}
    st.markdown(':material/group: **Patient et équipe soignante**')
    left, right = st.columns(2)
    with left:
        patient = record_select('Patient', options['patients'], 'idPatient', f'{prefix}_patient',
                                 initial=initial.get('idPatient'), disabled=bool(initial))
    with right:
        doctor = record_select('Médecin', options['doctors'], 'idMedecin', f'{prefix}_doctor',
                                initial=initial.get('idMedecin'), disabled=bool(initial))
    st.markdown(':material/calendar_month: **Créneau de visite**')
    when = date_time_fields(prefix, initial.get('dateHeure'))
    left, right = st.columns(2)
    with left:
        duration = st.number_input('Durée prévue (minutes)', min_value=1, max_value=65535,
                                   value=initial.get('dureePrevue', 30), step=5, key=f'{prefix}_duration')
    with right:
        statuses = list(dict.fromkeys(options['statuses'] + ([initial['statut']] if initial else [])))
        status = st.selectbox('Statut', statuses,
                               index=statuses.index(initial['statut']) if initial else None,
                               accept_new_options=True, placeholder='Sélectionnez ou saisissez un statut', key=f'{prefix}_status')
    st.caption('Un rendez-vous annulé libère le créneau. Les autres statuts le réservent.')
    return dict(idPatient=patient, idMedecin=doctor, dateHeure=when, dureePrevue=duration, statut=status)


def consultation_owners(prefix, options, initial=None):
    initial = initial or {}
    left, right = st.columns(2)
    with left:
        patient = record_select('Patient', options['patients'], 'idPatient', f'{prefix}_patient', initial=initial.get('idPatient'))
    with right:
        doctor = record_select('Médecin', options['doctors'], 'idMedecin', f'{prefix}_doctor', initial=initial.get('idMedecin'))
    return patient, doctor


def consultation_fields(prefix, options, patient, doctor, initial=None):
    initial = initial or {}
    candidates = consultation_repository.appointment_options(patient, doctor, consultation_id=initial.get('idConsultation')) if patient and doctor else []
    labels = {row['idRDV']: f"{row['dateHeure']:%d/%m/%Y %H:%M} · {row['statut']} · n° {row['idRDV']}" for row in candidates}
    ids = [None, *labels]
    current = initial.get('idRDV')
    appointment = st.selectbox('Rendez-vous lié (facultatif)', ids,
        index=ids.index(current) if current in ids else 0,
        format_func=lambda item: 'Aucun rendez-vous' if item is None else labels[item], key=f'{prefix}_appointment')
    st.caption('Seuls les rendez-vous du patient et du médecin choisis, disponibles ou déjà liés à cette consultation, sont proposés.')
    room = record_select('Salle (facultative)', options['rooms'], 'idSalle', f'{prefix}_room', initial=initial.get('idSalle'))
    when = date_time_fields(prefix, initial.get('dateHeure'))
    st.markdown(':material/clinical_notes: **Compte rendu de consultation**')
    reason = st.text_area('Motif', value=initial.get('motif', ''), max_chars=65535, key=f'{prefix}_reason')
    diagnosis = st.text_area('Diagnostic', value=initial.get('diagnostic', ''), max_chars=65535, key=f'{prefix}_diagnosis')
    return dict(idPatient=patient, idMedecin=doctor, idRDV=appointment, idSalle=room,
                dateHeure=when, motif=reason, diagnostic=diagnosis)


def saved(prefix, message):
    st.session_state[f'{prefix}_saved'] = message
    st.session_state[f'{prefix}_revision'] = st.session_state.get(f'{prefix}_revision', 0) + 1
    st.session_state.pop(f'{prefix}_snapshot', None)
    st.session_state.pop('dashboard_snapshot', None)
    st.rerun()


def edit_snapshot(prefix, row, id_field):
    snapshot = st.session_state.get(f'{prefix}_snapshot')
    if snapshot is None or snapshot[id_field] != row[id_field]:
        snapshot = row.copy()
        st.session_state[f'{prefix}_snapshot'] = snapshot
        st.session_state[f'{prefix}_revision'] = st.session_state.get(f'{prefix}_revision', 0) + 1
    return snapshot, st.session_state[f'{prefix}_revision']


def pagination(prefix, result, page_size):
    st.session_state[f'{prefix}_page'] = result['page']
    st.caption(f"{result['total']} résultat(s) · Page {result['page'] + 1}")
    if result['total'] <= page_size:
        return
    with st.container(horizontal=True):
        if st.button('Précédent', disabled=result['page'] == 0, key=f'{prefix}_previous'):
            st.session_state[f'{prefix}_page'] -= 1
            st.rerun()
        if st.button('Suivant', disabled=(result['page'] + 1) * page_size >= result['total'], key=f'{prefix}_next'):
            st.session_state[f'{prefix}_page'] += 1
            st.rerun()
