"""Simple password gate for all dashboard pages."""

import os
import streamlit as st


def _get_password() -> str:
    """Resolve password: st.secrets > env var > default."""
    try:
        return st.secrets["DASHBOARD_PASSWORD"]
    except Exception:
        return os.environ.get("DASHBOARD_PASSWORD", "BabylonLabs%LTV")


def check_password():
    """Block the page until the correct password is entered.

    Call AFTER st.set_page_config() on each page.
    """
    if st.session_state.get("authenticated"):
        return

    st.title("🔒 Access Required")
    pwd = st.text_input("Enter password", type="password")
    if pwd:
        if pwd == _get_password():
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Wrong password")
    st.stop()
