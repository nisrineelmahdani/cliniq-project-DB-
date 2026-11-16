"""One short-lived dashboard snapshot per browser session, never a shared patient cache."""

import streamlit as st

from db.repositories.dashboard_repository import load_dashboard
from services.clinic_clock import clinic_now


def dashboard_snapshot(*, refresh: bool = False) -> dict:
    now = clinic_now()
    snapshot = st.session_state.get('dashboard_snapshot')
    if (refresh or snapshot is None or snapshot['as_of'].date() != now.date()
            or not 0 <= (now - snapshot['as_of']).total_seconds() < 30):
        snapshot = load_dashboard(now)
        st.session_state['dashboard_snapshot'] = snapshot
    return snapshot
