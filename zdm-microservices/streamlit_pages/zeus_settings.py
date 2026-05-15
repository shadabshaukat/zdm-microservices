from __future__ import annotations

import streamlit as st

from streamlit_shared.api_client import ping_backend
from streamlit_shared.context import AppContext

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth
    default_base = ctx.default_base
    default_user = ctx.default_user
    default_password = ctx.default_password
    username = ctx.username
    password = ctx.password

    st.subheader("ZEUS Settings")
    st.caption("Configure the FastAPI endpoint and Basic Auth used by ZEUS UI.")

    left, right = st.columns([1.2, 1])

    with left:
        with st.form("backend_settings"):
            new_api_base = st.text_input("API Base URL", value=api_base or default_base).rstrip("/")
            new_username = st.text_input("Username", value=username or default_user)
            new_password = st.text_input("Password", value=password or default_password, type="password")
            save_settings = st.form_submit_button("Save", type="primary")
        if save_settings:
            st.session_state["api_base"] = new_api_base
            st.session_state["username"] = new_username
            st.session_state["password"] = new_password
            st.success("Backend settings updated.")

    with right:
        st.markdown("### Backend Status")
        if st.button("Ping backend", type="primary"):
            ok, used, data, err = ping_backend(api_base, auth)
            if ok:
                st.success(f"Backend reachable via `{used}`")
                st.json(data)
            else:
                st.error(
                    "Backend unreachable. Check API_BASE_URL and TLS trust. "
                    "If using self-signed cert, set REQUESTS_CA_BUNDLE to zeus.crt."
                )
                if err:
                    st.caption(f"Ping detail: {err}")



    # -----------------------------
