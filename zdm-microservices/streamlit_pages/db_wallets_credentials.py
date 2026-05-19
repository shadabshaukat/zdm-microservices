from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, validate_payload_or_stop
from streamlit_shared.api_payload import validate_cli_command_response
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import native_table_height
from streamlit_shared.wallet_payload import (
    validate_credential_wallet_delete_response,
    validate_credential_wallet_rows,
)


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Prepare Databases",
        "DB Wallets & Credentials",
        "Create reusable DB credential wallets for ZDM jobs and database discovery tasks.",
    )
    render_workflow_back_button()

    wallets_resp = api_request("get", "/credential-wallets", api_base, auth, quiet=True)
    wallets_unavailable = wallets_resp is None
    wallet_rows = (
        validate_payload_or_stop(wallets_resp, validate_credential_wallet_rows)
        if wallets_resp is not None
        else []
    )
    wallet_names = [row["name"] for row in wallet_rows]
    wallet_credentials = {row["name"]: row.get("credential_username") for row in wallet_rows}
    wallet_options = ["-- Select wallet --"] + wallet_names

    flash_message = st.session_state.pop("credential_wallet_flash", None)
    if flash_message:
        st.success(str(flash_message))

    if st.session_state.pop("credential_wallet_create_reset", False):
        st.session_state["credential_wallet_name_input"] = ""
    if st.session_state.pop("credential_create_reset", False):
        st.session_state["credential_wallet_select"] = "-- Select wallet --"
        st.session_state["credential_user_input"] = ""
        st.session_state["credential_password_input"] = ""
    if st.session_state.get("credential_wallet_select") not in wallet_options:
        st.session_state["credential_wallet_select"] = "-- Select wallet --"

    skip_wallet_submit = st.session_state.pop("credential_wallet_skip_next_submit", False)
    skip_credential_submit = st.session_state.pop("credential_skip_next_submit", False)

    tabs = st.tabs(["Create wallet & credential", "Saved wallets"])

    with tabs[0]:
        with page_panel("Create wallet", width="form"):
            with st.form("create_wallet", border=False):
                wallet_name = st.text_input(
                    "Credential wallet name",
                    help="Creates MIGRATION_BASE/wallets/cred/<wallet_name>",
                    key="credential_wallet_name_input",
                )
                create_wallet_clicked = st.form_submit_button("Create wallet", type="primary")

            if create_wallet_clicked and not skip_wallet_submit:
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
                        st.session_state["credential_wallet_flash"] = (
                            f"Credential wallet '{wallet_name}' created."
                        )
                        st.session_state["credential_wallet_create_reset"] = True
                        st.session_state["credential_wallet_select"] = wallet_name
                        st.session_state["credential_wallet_skip_next_submit"] = True
                        st.rerun()

        with page_panel("Create credential", width="form"):
            selected_wallet = st.selectbox("Wallet", wallet_options, key="credential_wallet_select")
            selected_wallet_has_credential = (
                selected_wallet != "-- Select wallet --"
                and bool(wallet_credentials.get(selected_wallet))
            )
            if selected_wallet_has_credential:
                st.warning("This wallet already has a credential. Delete and recreate the wallet if it is wrong.")

            with st.form("create_credential", border=False):
                cred_user = st.text_input("User", key="credential_user_input")
                cred_password = st.text_input("Password", type="password", key="credential_password_input")
                create_cred_clicked = st.form_submit_button(
                    "Create credential",
                    type="primary",
                    disabled=selected_wallet_has_credential,
                )

            if create_cred_clicked and not skip_credential_submit:
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
                        st.session_state["credential_wallet_flash"] = (
                            f"Credential for wallet '{wallet_name_cred}' created."
                        )
                        st.session_state["credential_create_reset"] = True
                        st.session_state["credential_skip_next_submit"] = True
                        st.rerun()

    with tabs[1]:
        with page_panel("Saved wallets"):
            if wallets_unavailable:
                st.error("ZEUS backend is not reachable. Saved wallets cannot be loaded.")
            elif wallet_rows:
                editor_rows = [
                    {
                        "Wallet": row["name"],
                        "Credential user": row.get("credential_username") or "",
                        "Status": "Ready" if row.get("credential_username") else "Empty",
                        "Delete": False,
                    }
                    for row in wallet_rows
                ]
                edited_df = st.data_editor(
                    pd.DataFrame(editor_rows),
                    hide_index=True,
                    num_rows="fixed",
                    width="stretch",
                    height=native_table_height(len(editor_rows)),
                    disabled=["Wallet", "Credential user", "Status"],
                    column_config={
                        "Wallet": st.column_config.TextColumn("Wallet", pinned=True),
                        "Credential user": st.column_config.TextColumn("Credential user"),
                        "Status": st.column_config.TextColumn("Status"),
                        "Delete": st.column_config.CheckboxColumn("Delete"),
                    },
                    key="credential_wallet_editor",
                )
                to_delete = [
                    str(row.get("Wallet"))
                    for row in edited_df.to_dict("records")
                    if bool(row.get("Delete")) and row.get("Wallet")
                ]

                confirm_delete = False
                if to_delete:
                    selected_has_credentials = any(wallet_credentials.get(name) for name in to_delete)
                    if selected_has_credentials:
                        st.warning("Deleting credential wallets removes stored DB credentials.")
                        confirm_delete = st.checkbox("Confirm deletion", key="credential_wallet_confirm_delete")
                    else:
                        confirm_delete = True

                action_cols = st.columns([0.88, 0.12])
                with action_cols[-1]:
                    delete_clicked = st.button("Delete", type="secondary", width="stretch", disabled=bool(to_delete) and not confirm_delete)

                if delete_clicked:
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
                        st.session_state.pop("credential_wallet_confirm_delete", None)
                        st.rerun()
            else:
                st.caption("No credential wallets saved.")

    # -----------------------------
