"""Native CLINIQ read-only CIF context and association tables."""

import pandas as pd
import streamlit as st

from ui.design import clinical_table


def hospitalization_context(row):
    with st.container(border=True, key='panel_stay_context'):
        st.subheader('Contexte du séjour')
        st.text(row['patient'])
        st.text(f"Séjour n° {row['idHospitalisation']} · Chambre {row['numeroChambre']} · Lit {row['numeroLit']}")
        st.text(f"Admission : {row['dateAdmission']:%d/%m/%Y %H:%M}")
        st.text('Sortie : '+(row['dateSortie'].strftime('%d/%m/%Y %H:%M') if row['dateSortie'] else 'Non renseignée'))


def assignments_table(rows,*,alt):
    if not rows:
        st.info('Aucun acte médical n’a encore de médecin responsable pour cette sélection.')
        return
    clinical_table(pd.DataFrame(rows)[['idHospitalisation','patient','dateAdmission','idActe','libelleActe','medecin']].rename(columns={
        'idHospitalisation':'Séjour n°','patient':'Patient','dateAdmission':'Admission','idActe':'Acte n°',
        'libelleActe':'Type d’acte','medecin':'Médecin responsable',
    }),hide_index=True,alt=alt)
