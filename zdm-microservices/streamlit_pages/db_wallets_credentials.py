from __future__ import annotations

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import validate_cli_command_response
from streamlit_shared.context import AppContext
from streamlit_shared.wallet_payload import (
    validate_credential_wallet_delete_response,
    validate_credential_wallet_rows,
)

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    st.subheader("DB Wallets & Credentials")
    st.caption("Create wallets and store credentials used by ZDM response files.")

    wallets_resp = api_request_required("get", "/credential-wallets", api_base, auth)
    wallet_rows = validate_payload_or_stop(wallets_resp, validate_credential_wallet_rows)
    wallet_names = [row["name"] for row in wallet_rows]
    wallet_credentials = {row["name"]: row.get("credential_username") for row in wallet_rows}

    left, right = st.columns([1, 1])

    with left:
        st.markdown("### Create wallet")
        with st.form("create_wallet"):
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
                    st.json(validated)
                    st.rerun()

    with right:
        st.markdown("### Create credential")
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
                    st.json(validated)
                    st.rerun()

    st.markdown("### Saved wallets")
    if wallet_rows:
        pending_delete = st.session_state.get("credential_wallet_pending_delete")

        def delete_wallet(wallet_name: str) -> None:
            data = api_request("delete", f"/credential-wallets/{wallet_name}", api_base, auth)
            if data:
                validate_payload_or_stop(data, validate_credential_wallet_delete_response)
                st.success(f"Deleted wallet '{wallet_name}'.")
                st.session_state.pop("credential_wallet_pending_delete", None)
                st.rerun()

        header_cols = st.columns([1.7, 1.3, 0.7, 0.45])
        header_cols[0].markdown("**Wallet**")
        header_cols[1].markdown("**Credential User**")
        header_cols[2].markdown("**Status**")
        header_cols[3].markdown("**Delete**")

        for row in wallet_rows:
            wallet_name = row["name"]
            credential_username = row.get("credential_username") or ""
            status = "Ready" if credential_username else "Empty"

            row_cols = st.columns([1.7, 1.3, 0.7, 0.45])
            row_cols[0].write(wallet_name)
            row_cols[1].write(credential_username or "-")
            row_cols[2].write(status)
            if row_cols[3].button(
                "Delete",
                key=f"delete_credential_wallet_{wallet_name}",
                help=f"Delete credential wallet {wallet_name}",
                icon=":material/delete:",
                width="stretch",
            ):
                if credential_username:
                    st.session_state["credential_wallet_pending_delete"] = wallet_name
                    st.rerun()
                else:
                    delete_wallet(wallet_name)

            if pending_delete == wallet_name:
                st.warning(f"Deleting '{wallet_name}' removes its stored DB credential.")
                confirm_col, cancel_col = st.columns([0.5, 0.5])
                if confirm_col.button(
                    "Confirm delete",
                    key=f"confirm_delete_credential_wallet_{wallet_name}",
                    type="secondary",
                    width="stretch",
                ):
                    delete_wallet(wallet_name)
                if cancel_col.button(
                    "Cancel",
                    key=f"cancel_delete_credential_wallet_{wallet_name}",
                    width="stretch",
                ):
                    st.session_state.pop("credential_wallet_pending_delete", None)
                    st.rerun()
    else:
        st.caption("No credential wallets saved.")

    # -----------------------------
