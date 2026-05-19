from __future__ import annotations

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
from streamlit_shared.db_auth import (
    render_db_auth_inputs_for_method,
    render_db_auth_method,
    validate_db_auth_selection,
)
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
from streamlit_shared.wallet_payload import validate_credential_wallet_names_response

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Prepare Databases",
        "DB Connections",
        "Create and maintain source and target DB connection records for ZDM configuration.",
    )
    render_workflow_back_button()

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
            raw_conns = api_request("get", "/dbconnections", api_base, auth, quiet=True)
            conns = {}
            if raw_conns is not None:
                conns = validate_payload_or_stop(raw_conns, validate_dbconnections_response)

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
                            "Delete?": False,
                        }
                    )

                df_orig = pd.DataFrame(rows)
                edited = st.data_editor(
                    df_orig,
                    hide_index=True,
                    width='stretch',
                    column_config={
                        "Name": st.column_config.TextColumn(disabled=True),
                        "Role": st.column_config.TextColumn(disabled=True),
                        "DB Platform": st.column_config.TextColumn(disabled=True),
                        "TLS Wallet dir": st.column_config.TextColumn(disabled=True),
                        "Protocol": st.column_config.SelectboxColumn(options=["TCP", "TCPS"]),
                        "TLS w/o wallet": st.column_config.CheckboxColumn(),
                        "Delete?": st.column_config.CheckboxColumn(),
                    },
                    key="conn_editor",
                )

                col_save, col_delete = st.columns([0.55, 0.45])
                with col_save:
                    if st.button("Save edits", type="primary", width='stretch'):
                        updated = 0
                        for idx, row in edited.iterrows():
                            orig = df_orig.iloc[idx]
                            if row.equals(orig):
                                continue
                            name = row["Name"]
                            payload = {
                                "name": name,
                                "db_type": conns[name].get("db_type", ""),
                                "connection_role": conns[name].get("connection_role", ""),
                                "host": row["Host"],
                                "port": int(row["Port"]),
                                "service_name": row["Service"],
                                "protocol": row["Protocol"],
                                "allow_tls_without_wallet": bool(row["TLS w/o wallet"]),
                            }
                            resp = api_request("post", "/dbconnections", api_base, auth, payload=payload)
                            if resp:
                                validate_payload_or_stop(
                                    resp,
                                    validate_dbconnection_save_response,
                                    expected_name=name,
                                )
                                updated += 1
                        if updated == 0:
                            st.info("No changes to save.")
                        else:
                            st.success(f"Saved {updated} changed connection{'s' if updated != 1 else ''}.")
                with col_delete:
                    if st.button("Delete checked", type="secondary", width='stretch'):
                        to_delete = [row["Name"] for _, row in edited.iterrows() if row.get("Delete?", False)]
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

        with page_panel("Test Connection"):
            last_saved = st.session_state.get("last_saved_conn", "-- Select --")
            options = ["-- Select --"] + list(conns.keys())
            default_idx = options.index(last_saved) if last_saved in options else 0
            test_name = st.selectbox("Connection", options, index=default_idx)
            test_clicked = st.button("Test", type="primary")

            st.divider()
            auth_method = render_db_auth_method(key_prefix="conn_test")
            wallet_rows = []
            if auth_method == "credential_wallet":
                wallet_resp = api_request("get", "/credential-wallets/names", api_base, auth, quiet=True)
                if wallet_resp is not None:
                    wallet_rows = validate_payload_or_stop(wallet_resp, validate_credential_wallet_names_response)
            auth_payload = render_db_auth_inputs_for_method(
                key_prefix="conn_test",
                method=auth_method,
                wallet_rows=wallet_rows,
                show_credential_user=False,
            )

            if test_clicked:
                if test_name == "-- Select --":
                    st.error("Please select a connection.")
                else:
                    cinfo = conns.get(test_name, {})
                    wallet_required = (str(cinfo.get("protocol", "")).upper() == "TCPS") and not cinfo.get(
                        "allow_tls_without_wallet"
                    )
                    if wallet_required and not cinfo.get("tls_wallet_uploaded_dir"):
                        st.error("Upload a TLS wallet for this connection before testing.")
                        st.stop()
                    auth_error = validate_db_auth_selection(auth_payload)
                    if auth_error:
                        st.error(auth_error)
                        st.stop()
                    payload = {
                        "name": test_name,
                        "auth": auth_payload,
                    }
                    data = api_request("post", "/dbconnections/test", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(data, validate_dbconnection_test_response)
                        st.success(validated["message"])
                        render_diagnostics(validated)


    # -----------------------------
