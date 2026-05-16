from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence

import streamlit as st


AUTH_METHOD_LABELS = {
    "Credential wallet": "credential_wallet",
    "Password": "password",
}
DEFAULT_AUTH_METHOD_LABEL = "Credential wallet"


def render_db_auth_method(*, key_prefix: str) -> str:
    method_label = st.radio(
        "Authentication",
        list(AUTH_METHOD_LABELS.keys()),
        index=list(AUTH_METHOD_LABELS.keys()).index(DEFAULT_AUTH_METHOD_LABEL),
        horizontal=True,
        key=f"{key_prefix}_auth_method",
    )
    return AUTH_METHOD_LABELS[method_label]


def render_db_auth_inputs_for_method(
    *,
    key_prefix: str,
    method: str,
    wallet_rows: Sequence[Mapping[str, Any]] = (),
) -> Dict[str, Any]:
    if method == "password":
        username = st.text_input("DB username", key=f"{key_prefix}_auth_username")
        password = st.text_input("DB password", type="password", key=f"{key_prefix}_auth_password")
        return {"method": "password", "username": username.strip(), "password": password}

    wallet_names = [str(row["name"]) for row in wallet_rows]
    selected = st.selectbox(
        "Credential wallet",
        ["-- Select wallet --"] + wallet_names,
        key=f"{key_prefix}_auth_wallet",
    )
    wallet_row = next((row for row in wallet_rows if row.get("name") == selected), {})
    credential_username = wallet_row.get("credential_username")
    if selected != "-- Select wallet --":
        if credential_username:
            st.caption(f"Credential user: {credential_username}")
        else:
            st.warning("Selected wallet has no credential. Add a credential first.")
    wallet_name = "" if selected == "-- Select wallet --" else selected
    return {"method": "credential_wallet", "wallet_name": wallet_name}


def validate_db_auth_selection(auth: Mapping[str, Any]) -> str | None:
    method = auth.get("method")
    if method == "password":
        if not auth.get("username") or not auth.get("password"):
            return "DB username and password are required."
        return None
    if method == "credential_wallet":
        if not auth.get("wallet_name"):
            return "Credential wallet is required."
        return None
    return "Authentication method is required."
