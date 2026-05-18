from __future__ import annotations

import streamlit as st

from streamlit_shared.api_client import ping_backend
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.ui import render_diagnostics

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth
    default_base = ctx.default_base
    default_user = ctx.default_user
    default_password = ctx.default_password
    username = ctx.username
    password = ctx.password

    render_page_header(
        "Administration",
        "ZEUS Settings",
        "Configure the ZEUS backend endpoint and login used by the console.",
    )

    with st.container(key="zeus-settings-stack"):
        with page_panel("About ZEUS"):
            st.markdown(
                """
                <div class="zeus-product-identity">
                    <p class="zeus-product-identity__description">
                        ZEUS stands for ZDM Enqueue URL Services, a ZDM migration control plane for fleet migration operations.
                    </p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with page_panel("Backend status"):
            if st.button("Ping backend", type="primary"):
                ok, used, data, err = ping_backend(api_base, auth)
                if ok:
                    st.success(f"Backend reachable via `{used}`")
                    render_diagnostics(data or {}, label="Backend response")
                else:
                    st.error(
                        "Backend unreachable. Check the ZEUS Backend URL and TLS certificate trust."
                    )
                    if err:
                        with st.expander("Technical details", expanded=False):
                            st.code(err)

        with page_panel("Backend settings"):
            with st.form("backend_settings", border=False):
                new_api_base = st.text_input("ZEUS Backend URL", value=api_base or default_base).rstrip("/")
                new_username = st.text_input("Username", value=username or default_user)
                new_password = st.text_input("Password", value=password or default_password, type="password")
                save_settings = st.form_submit_button("Save", type="primary")
            if save_settings:
                st.session_state["api_base"] = new_api_base
                st.session_state["username"] = new_username
                st.session_state["password"] = new_password
                st.success("Backend settings updated.")



    # -----------------------------
