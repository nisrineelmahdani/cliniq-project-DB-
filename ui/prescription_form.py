"""Native fields for the three attributes owned by PRESCRIRE."""

import streamlit as st


def prescription_fields(prefix, initial=None):
    initial = initial or {}
    left, right = st.columns(2)
    with left:
        quantity = st.number_input('Quantité (unités)', min_value=1, max_value=4294967295,
                                    value=initial.get('quantite', 1), step=1, key=f'{prefix}_quantity')
    with right:
        duration = st.number_input('Durée du traitement (jours)', min_value=1, max_value=65535,
                                    value=initial.get('duree', 1), step=1, key=f'{prefix}_duration')
    instructions = st.text_area('Posologie', value=initial.get('posologie', ''), max_chars=255,
                                placeholder='Saisissez les instructions prescrites', key=f'{prefix}_instructions')
    st.caption('Quantité et durée strictement positives. Posologie obligatoire, 255 caractères maximum.')
    return dict(quantite=quantity, posologie=instructions, duree=duration)
