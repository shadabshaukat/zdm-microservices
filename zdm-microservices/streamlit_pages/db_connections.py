from __future__ import annotations

from typing import Any, Mapping

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import (
    api_request,
    api_upload_file,
    validate_payload_or_stop,
)
from streamlit_shared.api_payload import (
    validate_dbconnection_delete_response,
    validate_dbconnection_save_response,
    validate_dbconnection_test_response,
    validate_dbconnections_response,
    validate_tls_wallet_upload_response,
)
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.db_types import (
    DB_CONNECTION_ROLE_OPTIONS,
    db_connection_role_label,
    db_connection_type_label,
    db_connection_type_notes,
    db_connection_type_options_for_role,
    is_adb_database_type,
)
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import render_diagnostics
from streamlit_shared.wallet_payload import validate_credential_wallet_rows


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Prepare Databases",
        "DB Connections",
        "Create and maintain source and target DB connection records for ZDM configuration.",
    )
    render_workflow_back_button()

    wallets_resp = api_request("get", "/credential-wallets", api_base, auth, quiet=True)
    wallet_rows = (
        validate_payload_or_stop(wallets_resp, validate_credential_wallet_rows)
        if wallets_resp is not None
        else []
    )
    wallet_user_by_name = {
        str(row.get("name")): row.get("credential_username")
        for row in wallet_rows
    }
    wallet_names = [str(row.get("name")) for row in wallet_rows if row.get("name")]
    wallet_options = ["-- Select credential wallet --"] + wallet_names

    raw_conns = api_request("get", "/dbconnections", api_base, auth, quiet=True)
    conns = (
        validate_payload_or_stop(raw_conns, validate_dbconnections_response)
        if raw_conns is not None
        else {}
    )

    def wallet_display(name: str) -> str:
        if name == "-- Select credential wallet --":
            return name
        user = wallet_user_by_name.get(name)
        return f"{name} ({user})" if user else name

    tabs = st.tabs(["Create connection", "Saved connections", "Test connection"])

    with tabs[0]:
        with page_panel("Define Connection", width="form"):
            # NOTE: We intentionally do NOT wrap these inputs in st.form().
            # Widgets inside a form do not trigger re-runs until submit, which breaks conditional UI
            # such as hiding/showing the wallet uploader.
            name = st.text_input(
                "Connection name",
                help="Identifier used in later test/migration calls",
                key="conn_name",
            )
            connection_role = st.selectbox(
                "Connection role",
                DB_CONNECTION_ROLE_OPTIONS,
                format_func=db_connection_role_label,
                index=0,
                key="conn_role",
            )
            db_type_options = db_connection_type_options_for_role(connection_role)
            db_type = st.selectbox(
                "DB Platform",
                db_type_options,
                format_func=db_connection_type_label,
                index=0,
                key=f"conn_db_type_{connection_role}",
            )
            for note in db_connection_type_notes(db_type):
                st.caption(note)

            host = st.text_input("Host", key="conn_host")
            port = st.number_input("Port", min_value=1, max_value=65535, value=1521, step=1, key="conn_port")
            service_name = st.text_input("Service Name", key="conn_service_name")
            credential_wallet_name = st.selectbox(
                "Credential wallet",
                wallet_options,
                format_func=wallet_display,
                key="conn_credential_wallet",
            )
            if wallets_resp is None:
                st.error("Credential wallets cannot be loaded. Check ZEUS Settings and backend availability.")
            elif not wallet_names:
                st.info("Create a DB Wallet & Credential before saving a DB connection.")

            is_adb = is_adb_database_type(db_type)
            if is_adb:
                use_tcps = st.toggle("Use TCPS", value=True, help="Recommended for ADB", key="conn_use_tcps")
                tls_no_wallet = False
                if use_tcps:
                    tls_no_wallet = st.toggle("TLS without wallet (server cert only)", value=False, key="conn_use_tls_no_wallet")
                else:
                    st.session_state.pop("conn_use_tls_no_wallet", None)
                wallet_needed = use_tcps and not tls_no_wallet
                use_tls_no_wallet = tls_no_wallet
            else:
                use_tcps = st.toggle(
                    "Use encrypted TCPS",
                    value=False,
                    help="For non-ADB connections; default is TCP",
                    key="conn_use_tcps",
                )
                wallet_needed = use_tcps
                use_tls_no_wallet = False
                st.session_state.pop("conn_use_tls_no_wallet", None)

            upload_file = None
            if wallet_needed:
                st.caption(
                    "TLS wallet is required. Upload will be stored under MIGRATION_BASE/connections/<name>/tls_wallet/"
                )
                upload_file = st.file_uploader(
                    "Upload TLS wallet (.zip/.p12)",
                    type=None,
                    key="tls_wallet_uploader",
                )
            else:
                # if it's not needed, hide it and clear any previously selected upload
                st.caption("Wallet not required for current selection.")
                st.session_state.pop("tls_wallet_uploader", None)

            save_clicked = st.button("Save connection", type="primary", key="conn_save_btn")

            if save_clicked:
                if not all([name, host, service_name]):
                    st.error("Name, host, and service_name are required.")
                elif credential_wallet_name == "-- Select credential wallet --":
                    st.error("Credential wallet is required.")
                elif wallet_needed and not upload_file:
                    st.error("Wallet is required for this connection type/protocol. Please upload the wallet.")
                else:
                    payload = {
                        "name": name,
                        "host": host,
                        "port": int(port),
                        "service_name": service_name,
                        "db_type": db_type,
                        "connection_role": connection_role,
                        "protocol": "TCPS" if use_tcps else "TCP",
                        "allow_tls_without_wallet": use_tls_no_wallet,
                        "credential_wallet_name": credential_wallet_name,
                    }
                    data = api_request("post", "/dbconnections", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(
                            data,
                            validate_dbconnection_save_response,
                            expected_name=name,
                        )
                        st.success(validated["message"])
                        if upload_file:
                            upload_resp = api_upload_file(
                                f"/dbconnections/{name}/tls-wallet",
                                api_base,
                                auth,
                                "wallet",
                                upload_file,
                            )
                            if upload_resp:
                                validate_payload_or_stop(upload_resp, validate_tls_wallet_upload_response)
                                st.success("TLS wallet uploaded.")
                        render_diagnostics(validated)
                        st.session_state["last_saved_conn"] = name

    with tabs[1]:
        with page_panel("Saved Connections"):
            if raw_conns is None:
                st.error(
                    "ZEUS backend is not reachable. Check ZEUS Settings and make sure the backend service is running."
                )
            elif not conns:
                st.info("No connections saved yet.")
            else:
                editor_rows = _connection_editor_rows(conns, wallet_user_by_name)
                wallet_editor_options = _wallet_options_for_saved_connections(wallet_names, conns)
                edited_df = st.data_editor(
                    pd.DataFrame(editor_rows),
                    hide_index=True,
                    num_rows="fixed",
                    width="stretch",
                    disabled=["Name", "Role", "DB Platform", "Credential User", "Status"],
                    column_config={
                        "Name": st.column_config.TextColumn("Name", pinned=True),
                        "Role": st.column_config.TextColumn("Role"),
                        "DB Platform": st.column_config.TextColumn("DB Platform"),
                        "Host": st.column_config.TextColumn("Host", required=True),
                        "Port": st.column_config.NumberColumn("Port", min_value=1, max_value=65535, step=1, required=True),
                        "Service": st.column_config.TextColumn("Service", required=True),
                        "Protocol": st.column_config.SelectboxColumn("Protocol", options=["TCP", "TCPS"], required=True),
                        "Credential Wallet": st.column_config.SelectboxColumn("Credential Wallet", options=wallet_editor_options, required=True),
                        "Credential User": st.column_config.TextColumn("Credential User"),
                        "TLS without wallet": st.column_config.CheckboxColumn("TLS without wallet"),
                        "Status": st.column_config.TextColumn("Status"),
                        "Delete": st.column_config.CheckboxColumn("Delete"),
                    },
                    key="conn_saved_editor",
                )
                edited_records = edited_df.to_dict("records")
                to_delete = [
                    str(row.get("Name"))
                    for row in edited_records
                    if bool(row.get("Delete")) and str(row.get("Name"))
                ]

                st.divider()
                action_cols = st.columns([0.68, 0.16, 0.16])
                with action_cols[1]:
                    save_clicked = st.button("Save", type="primary", width="stretch")
                with action_cols[2]:
                    delete_clicked = st.button("Delete", type="secondary", width="stretch")

                if save_clicked:
                    edited_rows = [
                        {
                            "name": str(row.get("Name")),
                            "original": conns.get(str(row.get("Name")), {}),
                            "payload": _connection_payload_from_editor_row(row, conns.get(str(row.get("Name")), {})),
                        }
                        for row in edited_records
                        if str(row.get("Name")) in conns
                    ]
                    invalid_rows = [
                        row["name"]
                        for row in edited_rows
                        if not _connection_payload_is_valid(row["payload"])
                    ]
                    if invalid_rows:
                        st.error("Host, service name, and credential wallet are required for: " + ", ".join(invalid_rows))
                    else:
                        changed_rows = [
                            row
                            for row in edited_rows
                            if _connection_payload_changed(row["payload"], row["original"])
                        ]
                        if not changed_rows:
                            st.info("No connection changes to save.")
                        else:
                            saved = 0
                            for row in changed_rows:
                                payload = row["payload"]
                                resp = api_request("post", "/dbconnections", api_base, auth, payload=payload)
                                if resp:
                                    validate_payload_or_stop(
                                        resp,
                                        validate_dbconnection_save_response,
                                        expected_name=row["name"],
                                    )
                                    saved += 1
                            st.success(f"Saved {saved} connection{'s' if saved != 1 else ''}.")
                            st.rerun()

                if delete_clicked:
                    if not to_delete:
                        st.info("No connections selected for deletion.")
                    else:
                        deleted = 0
                        for name in to_delete:
                            resp = api_request("delete", f"/dbconnections/{name}", api_base, auth)
                            if resp:
                                validate_payload_or_stop(resp, validate_dbconnection_delete_response)
                                deleted += 1
                        st.success(f"Deleted {deleted} connection{'s' if deleted != 1 else ''}.")
                        st.rerun()

    with tabs[2]:
        with page_panel("Test Connection", width="form"):
            last_saved = st.session_state.get("last_saved_conn", "-- Select --")
            options = ["-- Select --"] + list(conns.keys())
            default_idx = options.index(last_saved) if last_saved in options else 0
            test_name = st.selectbox("Connection", options, index=default_idx)
            test_clicked = st.button("Test", type="primary")

            if test_clicked:
                if test_name == "-- Select --":
                    st.error("Please select a connection.")
                else:
                    cinfo = conns.get(test_name, {})
                    if not cinfo.get("credential_wallet_name"):
                        st.error("This connection is missing a credential wallet. Edit the connection before testing.")
                        st.stop()
                    wallet_required = (str(cinfo.get("protocol", "")).upper() == "TCPS") and not cinfo.get(
                        "allow_tls_without_wallet"
                    )
                    if wallet_required and not cinfo.get("tls_wallet_uploaded_dir"):
                        st.error("Upload a TLS wallet for this connection before testing.")
                        st.stop()
                    payload = {"name": test_name}
                    data = api_request("post", "/dbconnections/test", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(data, validate_dbconnection_test_response)
                        st.success(validated["message"])
                        render_diagnostics(validated)


    # -----------------------------


def _wallet_options_for_saved_connections(wallet_names: list[str], conns: Mapping[str, Mapping[str, Any]]) -> list[str]:
    options = ["-- Select credential wallet --"] + list(wallet_names)
    for info in conns.values():
        saved_wallet = str(info.get("credential_wallet_name") or "")
        if saved_wallet and saved_wallet not in options:
            options.append(saved_wallet)
    return options


def _connection_editor_rows(
    conns: Mapping[str, Mapping[str, Any]],
    wallet_user_by_name: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for name, info in conns.items():
        credential_wallet = str(info.get("credential_wallet_name") or "-- Select credential wallet --")
        rows.append(
            {
                "Name": name,
                "Role": db_connection_role_label(info.get("connection_role", "")),
                "DB Platform": db_connection_type_label(info.get("db_type", "")),
                "Host": str(info.get("host") or ""),
                "Port": int(info.get("port") or 1521),
                "Service": str(info.get("service_name") or ""),
                "Protocol": str(info.get("protocol") or "TCP").upper(),
                "Credential Wallet": credential_wallet,
                "Credential User": str(wallet_user_by_name.get(credential_wallet) or ""),
                "TLS without wallet": bool(info.get("allow_tls_without_wallet")),
                "Status": "Ready" if credential_wallet != "-- Select credential wallet --" else "Needs wallet",
                "Delete": False,
            }
        )
    return rows


def _connection_payload_from_editor_row(
    row: Mapping[str, Any],
    original: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "name": _editor_text(row.get("Name")),
        "db_type": original.get("db_type", ""),
        "connection_role": original.get("connection_role", ""),
        "host": _editor_text(row.get("Host")),
        "port": int(row.get("Port") or 1521),
        "service_name": _editor_text(row.get("Service")),
        "protocol": _editor_text(row.get("Protocol")).upper() or "TCP",
        "allow_tls_without_wallet": bool(row.get("TLS without wallet")),
        "credential_wallet_name": _editor_text(row.get("Credential Wallet")) or "-- Select credential wallet --",
    }


def _editor_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _connection_payload_is_valid(payload: Mapping[str, Any]) -> bool:
    return (
        bool(str(payload.get("host") or "").strip())
        and bool(str(payload.get("service_name") or "").strip())
        and payload.get("credential_wallet_name") != "-- Select credential wallet --"
    )


def _connection_payload_changed(payload: Mapping[str, Any], original: Mapping[str, Any]) -> bool:
    comparable_original = {
        "host": str(original.get("host") or ""),
        "port": int(original.get("port") or 1521),
        "service_name": str(original.get("service_name") or ""),
        "protocol": str(original.get("protocol") or "TCP").upper(),
        "allow_tls_without_wallet": bool(original.get("allow_tls_without_wallet")),
        "credential_wallet_name": str(original.get("credential_wallet_name") or "-- Select credential wallet --"),
    }
    comparable_payload = {
        "host": str(payload.get("host") or ""),
        "port": int(payload.get("port") or 1521),
        "service_name": str(payload.get("service_name") or ""),
        "protocol": str(payload.get("protocol") or "TCP").upper(),
        "allow_tls_without_wallet": bool(payload.get("allow_tls_without_wallet")),
        "credential_wallet_name": str(payload.get("credential_wallet_name") or "-- Select credential wallet --"),
    }
    return comparable_payload != comparable_original
