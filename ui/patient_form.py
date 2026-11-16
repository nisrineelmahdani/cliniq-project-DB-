"""Shared registration/edit fields. Submission is handled by the page."""

from datetime import date

import streamlit as st

from services.clinic_clock import clinic_now


def patient_fields(prefix: str, initial: dict | None = None) -> dict:
    initial = initial or {}
    st.markdown(':material/person: **Identité du patient**')
    left, right = st.columns(2)
    with left:
        nom = st.text_input('Nom', value=initial.get('nom', ''), max_chars=100, key=f'{prefix}_nom')
    with right:
        prenom = st.text_input('Prénom', value=initial.get('prenom', ''), max_chars=100, key=f'{prefix}_prenom')
    birth = st.date_input('Date de naissance', value=initial.get('dateNaissance'),
                          min_value=date(1000, 1, 1), max_value=clinic_now().date(),
                          format='DD/MM/YYYY', key=f'{prefix}_birth')
    st.markdown(':material/contact_phone: **Coordonnées**')
    phone = st.text_input('Téléphone', value=initial.get('telephone', ''), max_chars=30, key=f'{prefix}_telephone')
    address = st.text_input('Adresse', value=initial.get('adresse', ''), max_chars=255, key=f'{prefix}_adresse')
    st.caption('Tous les champs sont obligatoires.')
    return dict(nom=nom, prenom=prenom, dateNaissance=birth, telephone=phone, adresse=address)
