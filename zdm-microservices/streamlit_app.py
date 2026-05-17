import os

import streamlit as st
from requests.auth import HTTPBasicAuth

try:
    from .backend_auth import first_user_defaults  # package-style
except ImportError:
    from backend_auth import first_user_defaults  # script-style

from streamlit_pages import (
    db_connections,
    db_discovery,
    db_wallets_credentials,
    migration_dashboard,
    projects,
    zdm_job_definitions,
    zdm_job_monitoring,
    zdm_job_submission,
    zdm_response_files,
    zeus_settings,
)
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_navigation, select_section


APP_LONG_NAME = "ZEUS – ZDM Enqueue URL Services"
st.set_page_config(page_title=APP_LONG_NAME, layout="wide")
st.title(APP_LONG_NAME)
st.caption("A lightweight UI on top of ZDM CLI via your FastAPI microservice.")


def _load_zeus_auth_defaults():
    """Read first user/pass from auth helper."""
    return first_user_defaults()


# Use hostname matching the certificate CN (localhost) to avoid TLS hostname errors.
default_base = os.getenv("API_BASE_URL", f"https://localhost:{os.getenv('ZEUS_PORT', '8001')}").rstrip("/")
auth_user_file, auth_pass_file = _load_zeus_auth_defaults()
default_user = os.getenv("ZDM_API_USER", auth_user_file or "zdmuser")
default_password = os.getenv("ZDM_API_PASSWORD", auth_pass_file or "YourPassword123#_")

if "api_base" not in st.session_state:
    st.session_state["api_base"] = default_base
if "username" not in st.session_state:
    st.session_state["username"] = default_user
if "password" not in st.session_state:
    st.session_state["password"] = default_password

api_base = st.session_state.get("api_base", "").rstrip("/")
username = st.session_state.get("username", "")
password = st.session_state.get("password", "")
auth = HTTPBasicAuth(username, password)

section = select_section()
render_navigation(section)
with st.sidebar:
    st.caption(f"API: {st.session_state.get('api_base','') or 'not set'}")
    st.caption(f"User: {st.session_state.get('username','') or 'not set'}")

previous_section = st.session_state.get("_active_section")
st.session_state["_active_section"] = section

if section != "settings" and not api_base:
    st.warning("Please configure ZEUS Settings first.")
    st.stop()

ctx = AppContext(
    api_base=api_base,
    auth=auth,
    default_base=default_base,
    default_user=default_user,
    default_password=default_password,
    username=username,
    password=password,
    section=section,
    previous_section=previous_section,
)

PAGE_RENDERERS = {
    "settings": zeus_settings.render,
    "connections": db_connections.render,
    "wallet": db_wallets_credentials.render,
    "discovery": db_discovery.render,
    "projects": projects.render,
    "response": zdm_response_files.render,
    "createjob": zdm_job_definitions.render,
    "runjob": zdm_job_submission.render,
    "jobs": zdm_job_monitoring.render,
    "fleet_dashboard": migration_dashboard.render,
}

PAGE_RENDERERS.get(section, zeus_settings.render)(ctx)
