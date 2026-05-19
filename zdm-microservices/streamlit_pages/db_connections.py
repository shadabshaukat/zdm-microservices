from __future__ import annotations

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
from streamlit_shared.ui import render_diagnostics, render_static_table
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

    col_form, col_table = st.columns([1.15, 1.1])

    with col_form:
        with page_panel("Define Connection"):
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


    with col_table:
        with page_panel("Saved Connections"):
            if raw_conns is None:
                st.error(
                    "ZEUS backend is not reachable. Check ZEUS Settings and make sure the backend service is running."
                )
            elif not conns:
                st.info("No connections saved yet.")
            else:
                rows = []
                for name, info in conns.items():
                    rows.append(
                        {
                            "Name": name,
                            "Role": db_connection_role_label(info.get("connection_role", "")),
                            "DB Platform": db_connection_type_label(info.get("db_type", "")),
                            "Host": info.get("host", ""),
                            "Port": info.get("port", ""),
                            "Service": info.get("service_name", ""),
                            "Protocol": info.get("protocol", ""),
                            "TLS w/o wallet": bool(info.get("allow_tls_without_wallet")),
                            "TLS Wallet dir": info.get("tls_wallet_uploaded_dir", ""),
                            "Credential Wallet": info.get("credential_wallet_name") or "",
                            "Credential User": wallet_user_by_name.get(info.get("credential_wallet_name") or "") or "",
                            "Status": "Ready" if info.get("credential_wallet_name") else "Needs credential wallet",
                        }
                    )

                render_static_table(
                    rows,
                    [
                        "Name",
                        "Role",
                        "DB Platform",
                        "Host",
                        "Port",
                        "Service",
                        "Protocol",
                        "Credential Wallet",
                        "Credential User",
                        "Status",
                    ],
                )

                st.divider()
                edit_options = ["-- Select connection --"] + list(conns.keys())
                edit_name = st.selectbox(
                    "Connection to edit",
                    edit_options,
                    key="conn_edit_select",
                )
                if edit_name != "-- Select connection --":
                    edit_info = conns[edit_name]
                    edit_wallet_options = ["-- Select credential wallet --"] + wallet_names
                    saved_wallet = edit_info.get("credential_wallet_name") or "-- Select credential wallet --"
                    edit_wallet_index = (
                        edit_wallet_options.index(saved_wallet)
                        if saved_wallet in edit_wallet_options
                        else 0
                    )
                    edit_host = st.text_input(
                        "Edit host",
                        value=str(edit_info.get("host") or ""),
                        key=f"conn_edit_host_{edit_name}",
                    )
                    edit_port = st.number_input(
                        "Edit port",
                        min_value=1,
                        max_value=65535,
                        value=int(edit_info.get("port") or 1521),
                        step=1,
                        key=f"conn_edit_port_{edit_name}",
                    )
                    edit_service = st.text_input(
                        "Edit service name",
                        value=str(edit_info.get("service_name") or ""),
                        key=f"conn_edit_service_{edit_name}",
                    )
                    edit_protocol = st.selectbox(
                        "Edit protocol",
                        ["TCP", "TCPS"],
                        index=1 if str(edit_info.get("protocol") or "").upper() == "TCPS" else 0,
                        key=f"conn_edit_protocol_{edit_name}",
                    )
                    edit_tls_without_wallet = st.checkbox(
                        "TLS without wallet",
                        value=bool(edit_info.get("allow_tls_without_wallet")),
                        key=f"conn_edit_tls_without_wallet_{edit_name}",
                    )
                    edit_credential_wallet = st.selectbox(
                        "Edit credential wallet",
                        edit_wallet_options,
                        format_func=wallet_display,
                        index=edit_wallet_index,
                        key=f"conn_edit_credential_wallet_{edit_name}",
                    )
                    if st.button("Save edits", type="primary", width='stretch'):
                        if edit_credential_wallet == "-- Select credential wallet --":
                            st.error("Credential wallet is required.")
                        elif not edit_host or not edit_service:
                            st.error("Host and service name are required.")
                        else:
                            payload = {
                                "name": edit_name,
                                "db_type": edit_info.get("db_type", ""),
                                "connection_role": edit_info.get("connection_role", ""),
                                "host": edit_host,
                                "port": int(edit_port),
                                "service_name": edit_service,
                                "protocol": edit_protocol,
                                "allow_tls_without_wallet": bool(edit_tls_without_wallet),
                                "credential_wallet_name": edit_credential_wallet,
                            }
                            resp = api_request("post", "/dbconnections", api_base, auth, payload=payload)
                            if resp:
                                validate_payload_or_stop(
                                    resp,
                                    validate_dbconnection_save_response,
                                    expected_name=edit_name,
                                )
                                st.success("Saved connection edits.")
                                st.rerun()

                to_delete = st.multiselect(
                    "Connections to delete",
                    list(conns.keys()),
                    key="connections_to_delete",
                )
                if st.button("Delete checked", type="secondary", width='stretch'):
                    if not to_delete:
                        st.info("No connections selected for deletion.")
                    else:
                        deleted = 0
                        for name in to_delete:
                            resp = api_request("delete", f"/dbconnections/{name}", api_base, auth)
                            if resp:
                                validate_payload_or_stop(resp, validate_dbconnection_delete_response)
                                deleted += 1
                        st.success(
                            f"Deleted {deleted} connection{'s' if deleted != 1 else ''}. Refresh to update list."
                        )
                        st.rerun()

        with page_panel("Test Connection"):
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
