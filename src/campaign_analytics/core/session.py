"""Small, explicit Streamlit session-state initialisation."""

import streamlit as st


DEFAULT_SESSION_STATE: dict[str, object] = {
    "active_page": "Dashboard",
    "campaign_name": None,
    "campaign_round": None,
    "upload_records": [],
    "uploader_version": 0,
    "last_error_reference": None,
}


def initialise_session() -> None:
    """Set platform defaults without replacing a user's active session values."""
    for key, value in DEFAULT_SESSION_STATE.items():
        st.session_state.setdefault(key, value)

