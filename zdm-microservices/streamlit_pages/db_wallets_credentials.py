from __future__ import annotations

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import validate_cli_command_response
from streamlit_shared.context import AppContext
from streamlit_shared.wallet_payload import validate_credential_wallets_response

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    st.subheader("DB Wallets & Credentials")
    st.caption("Create wallets and store credentials used by ZDM response files.")

    left, right = st.columns([1, 1])

    with left:
        st.markdown("### Create wallet")
        with st.form("create_wallet"):
            wallet_name = st.text_input("Credential wallet name", help="Creates MIGRATION_BASE/wallets/cred/<wallet_name>")
            create_wallet_clicked = st.form_submit_button("Create wallet", type="primary")

        if create_wallet_clicked:
            if not wallet_name:
                st.error("Wallet name is required.")
            else:
                payload = {"wallet_name": wallet_name}
                data = api_request("post", "/wallets/ora-pki", api_base, auth, payload=payload)
                if data:
                    validated = validate_payload_or_stop(
                        data,
                        validate_cli_command_response,
                        endpoint="POST /wallets/ora-pki",
                    )
                    st.success(validated["status"])
                    st.json(validated)

    with right:
        st.markdown("### Create credential")
        wallets_resp = api_request_required("get", "/credential-wallets", api_base, auth)
        wallet_map = validate_payload_or_stop(wallets_resp, validate_credential_wallets_response)
        wallet_names = list(wallet_map.keys())
        wallet_options = ["-- Select wallet --"] + wallet_names

        selected_wallet = st.selectbox("Wallet", wallet_options)

        with st.form("create_credential"):
            cred_user = st.text_input("User")
            cred_password = st.text_input("Password", type="password")
            create_cred_clicked = st.form_submit_button("Create credential", type="primary")

        if create_cred_clicked:
            wallet_name_cred = selected_wallet if selected_wallet != "-- Select wallet --" else ""
            if not wallet_name_cred or not cred_user or not cred_password:
                st.error("Wallet name, user, and password are required.")
            else:
                payload = {"wallet_name": wallet_name_cred, "user": cred_user, "password": cred_password}
                data = api_request("post", "/wallets/mkstore-credential", api_base, auth, payload=payload)
                if data:
                    validated = validate_payload_or_stop(
                        data,
                        validate_cli_command_response,
                        endpoint="POST /wallets/mkstore-credential",
                    )
                    st.success(validated["status"])
                    st.json(validated)


    st.info(
        "Run: from repo root `streamlit run zdm-microservices/streamlit_app.py` · "
        "Ensure FastAPI is running and accessible from this machine."
    )

    # -----------------------------
