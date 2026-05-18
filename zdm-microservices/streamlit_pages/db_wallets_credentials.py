from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import validate_cli_command_response
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.wallet_payload import (
    validate_credential_wallet_delete_response,
    validate_credential_wallet_rows,
)

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Database Setup",
        "DB Wallets & Credentials",
        "Create reusable DB credential wallets for ZDM jobs and database discovery tasks.",
    )
    render_workflow_back_button()

    wallets_resp = api_request_required("get", "/credential-wallets", api_base, auth)
    wallet_rows = validate_payload_or_stop(wallets_resp, validate_credential_wallet_rows)
    wallet_names = [row["name"] for row in wallet_rows]
    wallet_credentials = {row["name"]: row.get("credential_username") for row in wallet_rows}

    left, right = st.columns([1, 1])

    with left:
        with page_panel("Create wallet"):
            with st.form("create_wallet", border=False):
                wallet_name = st.text_input("Credential wallet name", help="Creates MIGRATION_BASE/wallets/cred/<wallet_name>")
                create_wallet_clicked = st.form_submit_button("Create wallet", type="primary")

            if create_wallet_clicked:
                if not wallet_name:
                    st.error("Wallet name is required.")
                elif wallet_name in wallet_names:
                    st.error("Wallet already exists.")
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
                        st.rerun()

    with right:
        with page_panel("Create credential"):
            wallet_options = ["-- Select wallet --"] + wallet_names

            selected_wallet = st.selectbox("Wallet", wallet_options)
            selected_wallet_has_credential = (
                selected_wallet != "-- Select wallet --"
                and bool(wallet_credentials.get(selected_wallet))
            )
            if selected_wallet_has_credential:
                st.warning("This wallet already has a credential. Delete and recreate the wallet if it is wrong.")

            with st.form("create_credential", border=False):
                cred_user = st.text_input("User")
                cred_password = st.text_input("Password", type="password")
                create_cred_clicked = st.form_submit_button(
                    "Create credential",
                    type="primary",
                    disabled=selected_wallet_has_credential,
                )

            if create_cred_clicked:
                wallet_name_cred = selected_wallet if selected_wallet != "-- Select wallet --" else ""
                if not wallet_name_cred or not cred_user or not cred_password:
                    st.error("Wallet name, user, and password are required.")
                elif wallet_credentials.get(wallet_name_cred):
                    st.error("Credential already exists in this wallet. Delete and recreate the wallet if it is wrong.")
                else:
                    payload = {"wallet_name": wallet_name_cred, "user": cred_user.strip(), "password": cred_password}
                    data = api_request("post", "/wallets/mkstore-credential", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(
                            data,
                            validate_cli_command_response,
                            endpoint="POST /wallets/mkstore-credential",
                        )
                        st.success(validated["status"])
                        st.rerun()

    with page_panel("Saved wallets"):
        if wallet_rows:
            wallet_table_rows = [
                {
                    "Wallet": row["name"],
                    "Credential User": row.get("credential_username") or "",
                    "Status": "Ready" if row.get("credential_username") else "Empty",
                    "Delete?": False,
                }
                for row in wallet_rows
            ]
            edited = st.data_editor(
                pd.DataFrame(wallet_table_rows),
                width="stretch",
                hide_index=True,
                column_config={
                    "Wallet": st.column_config.TextColumn(disabled=True),
                    "Credential User": st.column_config.TextColumn(disabled=True),
                    "Status": st.column_config.TextColumn(disabled=True),
                    "Delete?": st.column_config.CheckboxColumn(),
                },
                key="credential_wallet_editor",
            )

            to_delete = [row["Wallet"] for _, row in edited.iterrows() if row.get("Delete?", False)]
            confirm_delete = False
            if to_delete:
                selected_has_credentials = any(wallet_credentials.get(name) for name in to_delete)
                if selected_has_credentials:
                    st.warning("Deleting credential wallets removes stored DB credentials.")
                    confirm_delete = st.checkbox("Confirm deletion", key="credential_wallet_delete_confirm")
                else:
                    confirm_delete = True

            if st.button("Delete checked wallets", type="secondary", disabled=bool(to_delete) and not confirm_delete):
                if not to_delete:
                    st.info("No wallets selected for deletion.")
                else:
                    deleted = 0
                    for name in to_delete:
                        data = api_request("delete", f"/credential-wallets/{name}", api_base, auth)
                        if data:
                            validate_payload_or_stop(data, validate_credential_wallet_delete_response)
                            deleted += 1
                    st.success(f"Deleted {deleted} wallet{'s' if deleted != 1 else ''}.")
                    st.session_state.pop("credential_wallet_delete_confirm", None)
                    st.rerun()
        else:
            st.caption("No credential wallets saved.")

    # -----------------------------
