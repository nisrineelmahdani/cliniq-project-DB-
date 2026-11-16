"""Shared CLINIQ presentation components; no database or business-rule logic."""

from contextlib import contextmanager
from html import escape
from pathlib import Path

import streamlit as st

from services.clinic_clock import clinic_now

COLORS = {
    'rose': '#E84C71', 'coral': '#FF7B89', 'blush': '#FCE7ED',
    'background': '#FFF8FA', 'surface': '#FFFFFF', 'text': '#442638',
    'muted': '#806775', 'red': '#C93F55', 'green': '#24745B',
    'amber': '#956215', 'blue': '#42659D', 'border': '#EEDFE5',
}


def apply_design() -> None:
    st.html(Path(__file__).with_name('styles.css'))


def choose_mode(key: str, value: str) -> None:
    st.session_state[key] = value


def page_header(title: str, subtitle: str, *, section: str = 'PARCOURS PATIENT',
                action: str | None = None, mode_key: str | None = None,
                mode_value: str | None = None) -> None:
    with st.container(key='cliniq_page_header'):
        left, right = st.columns([4, 2], vertical_alignment='center')
        with left:
            st.html(f'<p class="eyebrow">{escape(section)}</p>')
            st.title(title)
            st.caption(subtitle)
        with right:
            if action and mode_key and mode_value:
                st.button(action, icon=':material/add:', type='primary', width='stretch',
                          key=f'{mode_key}_primary', on_click=choose_mode,
                          args=(mode_key, mode_value))
            else:
                st.markdown(f':material/calendar_today: **{clinic_now():%d.%m.%Y}**')
                st.caption('Votre espace de soins · CLINIQ')
    st.space('small')


@contextmanager
def surface_form(key: str, **kwargs):
    """Native form on a named surface, with stable existing widget/form keys."""
    with st.container(border=True, key=f'panel_{key}'):
        with st.form(key, border=False, **kwargs):
            yield


def section_heading(title: str, caption: str = '', *, icon: str = 'folder_open') -> None:
    st.subheader(title, icon=f':material/{icon}:')
    if caption:
        st.caption(caption)


def status_badge(status: str) -> None:
    tone = {'Confirmé': 'success', 'Terminé': 'neutral', 'Terminée': 'neutral',
            'Planifié': 'info', 'Prévue': 'info', 'En cours': 'warning',
            'Annulé': 'danger', 'Disponible': 'success', 'Occupé': 'warning'}.get(status, 'neutral')
    st.html(f'<span class="status-badge status-{tone}">{escape(status)}</span>')


def empty_state(title: str, description: str) -> None:
    # Keep a native info element for assistive technology and AppTest assertions.
    with st.container(border=True, key='panel_empty'):
        st.markdown(':material/search_off: **'+title+'**')
        st.info(description)


def workflow_hint(title: str, steps: str) -> None:
    with st.container(key='cliniq_workflow_hint'):
        st.markdown(f':material/route: **{title}**')
        st.caption(steps)


def clinical_table(data, **kwargs):
    """Readable dates and consistent table sizing; values remain native data."""
    config = {name: st.column_config.DatetimeColumn(name, format='DD/MM/YYYY HH:mm')
              for name in ('Date et heure', 'Début', 'Fin', 'Admission', 'Sortie')}
    config['Naissance'] = st.column_config.DateColumn('Naissance', format='DD/MM/YYYY')
    kwargs.setdefault('column_config', config)
    kwargs.setdefault('width', 'stretch')
    kwargs.setdefault('row_height', 40)
    return st.dataframe(data, **kwargs)
