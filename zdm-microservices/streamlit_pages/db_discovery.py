from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_dbconnections_response,
    validate_discovery_latest_response,
    validate_discovery_response,
)
from streamlit_shared.console_layout import render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.db_auth import (
    render_db_auth_inputs_for_method,
    render_db_auth_method,
    validate_db_auth_selection,
)
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.response_file_form import active_migration_method_options
from streamlit_shared.ui import render_diagnostics, st_df_safe
from streamlit_shared.wallet_payload import validate_credential_wallet_names_response

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Database Setup",
        "DB Discovery",
        "Run source discovery to retrieve database details needed for ZDM configuration.",
    )
    render_workflow_back_button()

    conns = validate_payload_or_stop(
        api_request_required("get", "/dbconnections", api_base, auth),
        validate_dbconnections_response,
    )
    conn_names = ["-- Select connection --"] + list(conns.keys())
    discovery_migration_types = active_migration_method_options()
    if st.session_state.get("disc_mt") not in discovery_migration_types:
        st.session_state["disc_mt"] = next(iter(discovery_migration_types), "")

    col_sel, col_mt = st.columns([0.6, 0.4], vertical_alignment="bottom")
    with col_sel:
        selected_conn = st.selectbox("Connection", conn_names, key="disc_conn")
    with col_mt:
        selected_migration_label = st.selectbox("Migration type", list(discovery_migration_types.keys()), key="disc_mt")
        migration_type = discovery_migration_types[selected_migration_label]
    auth_method = render_db_auth_method(key_prefix="disc")
    wallet_rows = []
    if auth_method == "credential_wallet":
        wallet_rows = validate_payload_or_stop(
            api_request_required("get", "/credential-wallets/names", api_base, auth),
            validate_credential_wallet_names_response,
        )
    auth_payload = render_db_auth_inputs_for_method(
        key_prefix="disc",
        method=auth_method,
        wallet_rows=wallet_rows,
        show_credential_user=False,
    )

    # -------- helpers (normalize once, then render) --------
    def _format_bytes(val: Optional[float]) -> str:
        try:
            num = float(val)
        except Exception:
            return ""
        mb = num / (1024 * 1024)
        return f"{int(num):,} bytes ({mb:,.0f} MB)"

    def _pick_number(val: Any) -> Optional[float]:
        if isinstance(val, dict):
            # prefer canonical keys, otherwise first numeric-ish value
            for key in ["STREAMS_POOL_SIZE_BYTES", "streams_pool_size_bytes"]:
                if key in val:
                    return _pick_number(val[key])
            for v in val.values():
                num = _pick_number(v)
                if num is not None:
                    return num
            return None
        if isinstance(val, (int, float)):
            return float(val)
        if isinstance(val, str):
            try:
                return float(val)
            except Exception:
                return None
        return None

    def normalize_snapshot(raw: Dict[str, Any]) -> Dict[str, Any]:
        """Extract/derive the fields the UI needs in one pass."""
        mig = str(raw.get("migration_type") or "").upper()
        extras = raw.get("extras") or {}
        logical_extra = extras.get("logical_offline_extra") or {}

        readiness: List[Dict[str, str]] = []

        streams_raw = logical_extra.get("streams_pool_size")
        streams_val = _pick_number(streams_raw)
        streams_display = "Not returned"
        streams_status = "UNKNOWN"
        streams_hint = "Not returned"
        if streams_val is not None:
            streams_display = _format_bytes(streams_val)
            if streams_val >= 350 * 1024 * 1024:
                streams_status = "PASS"
                streams_hint = ">= 350MB (recommended)"
            elif streams_val >= 256 * 1024 * 1024:
                streams_status = "WARN"
                streams_hint = "256–349MB; consider increasing to 350MB"
            else:
                streams_status = "FAIL"
                streams_hint = "<256MB; set streams_pool_size to >=350MB"
        elif streams_raw is not None:
            streams_display = str(streams_raw)
            streams_status = "WARN"
            streams_hint = "Could not parse value"

        if mig == "OFFLINE_LOGICAL":
            readiness.append(
                {
                    "Check": "STREAMS_POOL_SIZE ≥ 350MB (logical offline)",
                    "Value": streams_display,
                    "Status": streams_status,
                    "Hint": streams_hint,
                }
            )

        return {
            "migration_type": mig,
            "readiness_checks": readiness,
            "streams_pool_bytes": streams_val,
            "streams_pool_display": streams_display,
            "streams_pool_status": streams_status,
            "streams_pool_hint": streams_hint,
        }

    def discovery_profile_rows(raw: Dict[str, Any]) -> Tuple[List[Dict[str, str]], Optional[str]]:
        extras = raw.get("extras") or {}
        logical_common = extras.get("logical_common") or {}
        profiles = logical_common.get("db_profiles")
        if profiles is None:
            return [], None
        if isinstance(profiles, dict) and profiles.get("error"):
            return [], str(profiles.get("error"))
        if not isinstance(profiles, list):
            raise ValueError("Unexpected discovery profile payload shape: expected extras.logical_common.db_profiles list")

        rows: List[Dict[str, str]] = []
        for row in profiles:
            if (
                not isinstance(row, dict)
                or not isinstance(row.get("PROFILE"), str)
                or not isinstance(row.get("PROFILE_DDL"), str)
            ):
                raise ValueError("Unexpected discovery profile payload shape: expected PROFILE and PROFILE_DDL strings")
            rows.append({"PROFILE": row["PROFILE"], "PROFILE_DDL": row["PROFILE_DDL"]})
        return rows, None

    def cloud_identity_record(raw: Any) -> Dict[str, Any]:
        rows = raw if isinstance(raw, list) else [raw]

        for row in rows:
            if isinstance(row, dict) and "error" not in row and row.get("DATABASE_OCID"):
                return row

        return {}

    run_disc = st.button("Run discovery", type="primary")

    # -------- snapshot sourcing (cached from backend or freshly run) --------
    snapshot = None
    snapshot_source = ""
    cache_key = f"discovery_cached_{selected_conn}"
    cache_file_key = f"{cache_key}_file"
    cache_tsdisp_key = f"{cache_key}_ts_display"

    def parse_ts_from_filename(path: Optional[str]) -> Optional[str]:
        if not path:
            return None
        fname = os.path.basename(path)
        match = re.search(r"_(\d{8}T\d{6}Z)_snapshot\.json$", fname)
        if not match:
            return None
        raw = match.group(1)  # YYYYMMDDTHHMMSSZ
        return f"{raw[0:4]}-{raw[4:6]}-{raw[6:8]} {raw[9:11]}:{raw[11:13]}:{raw[13:15]} UTC"

    if selected_conn != "-- Select connection --":
        if cache_key not in st.session_state:
            latest_payload = api_request_required(
                "get",
                f"/dbconnections/{selected_conn}/discovery/latest",
                api_base,
                auth,
            )
            latest_snapshot = validate_payload_or_stop(
                latest_payload,
                validate_discovery_latest_response,
            )
            if latest_snapshot is not None:
                st.session_state[cache_key] = latest_snapshot
                st.session_state[cache_file_key] = latest_payload.get("file")
                tsd = parse_ts_from_filename(latest_payload.get("file"))
                if tsd:
                    st.session_state[cache_tsdisp_key] = tsd
        snapshot = st.session_state.get(cache_key)
        snapshot_source = "cached" if snapshot is not None else ""

    if run_disc:
        if selected_conn == "-- Select connection --":
            st.error("Select a connection.")
        else:
            auth_error = validate_db_auth_selection(auth_payload)
            if auth_error:
                st.error(auth_error)
                st.stop()
            payload = {"name": selected_conn, "auth": auth_payload, "migration_type": migration_type}
            data = api_request("post", "/dbconnections/discover", api_base, auth, payload=payload)
            if data:
                snapshot = validate_payload_or_stop(data, validate_discovery_response)
                st.session_state[cache_key] = snapshot
                st.session_state.pop(cache_file_key, None)
                st.session_state[cache_tsdisp_key] = "just captured"
                st.session_state["last_discovery"] = snapshot
                snapshot_source = "live"

    if snapshot is None:
        last = st.session_state.get("last_discovery")
        snapshot = last if not isinstance(last, dict) or "snapshot" not in last else last.get("snapshot")

    if snapshot:
        normalized = normalize_snapshot(snapshot)
    else:
        normalized = {}
    snap_ts_display = (
        st.session_state.get(cache_tsdisp_key)
        or parse_ts_from_filename(st.session_state.get(cache_file_key))
        or "time unknown"
    )

    if snapshot:
        # Header card
        header = st.container(border=True)
        with header:
            db_info = snapshot.get("db_info") or {}
            inst = snapshot.get("instance_info") or {}
            conn_meta = snapshot.get("connection") or {}
            con_name = snapshot.get("connection_name") or selected_conn
            mig_type = normalized.get("migration_type") or str(snapshot.get("migration_type") or "").upper()
            st.markdown(f"**{con_name}** — _{mig_type or 'N/A'}_ — {snap_ts_display}")
            if snapshot_source == "cached":
                st.caption(f"Cached snapshot: {snap_ts_display}")

            chips: List[str] = []
            platform_type = snapshot.get("platform_type")
            if platform_type:
                chips.append(f"Type: {platform_type}")
            role = snapshot.get("db_role_open_mode_base") or {}
            if role.get("DATABASE_ROLE") or role.get("database_role"):
                chips.append(f"Role: {role.get('DATABASE_ROLE') or role.get('database_role')}")
            if role.get("OPEN_MODE") or role.get("open_mode"):
                chips.append(f"Open: {role.get('OPEN_MODE') or role.get('open_mode')}")
            rac = snapshot.get("rac_info") or {}
            rac_val = rac.get("RAC") or rac.get("rac")
            inst_cnt = rac.get("INSTANCE_COUNT") or rac.get("instance_count")
            if rac_val:
                chips.append(f"RAC: {rac_val}{' ('+str(inst_cnt)+')' if inst_cnt else ''}")
            cont = snapshot.get("container_label")
            if cont:
                chips.append(f"Container: {cont}")
            if chips:
                st.markdown(" ".join([f"`{c}`" for c in chips]))

        cloud_identity = cloud_identity_record(snapshot.get("cloud_identity"))

        tab_names = ["Readiness", "Summary", "Schemas", "Tablespaces", "Directories", "NLS & TZ"]
        cloud_tab_idx = None
        profiles_tab_idx = None
        if cloud_identity:
            cloud_tab_idx = len(tab_names)
            tab_names.append("Cloud Identity")
        if str(normalized.get("migration_type") or "").startswith("LOGICAL_"):
            profiles_tab_idx = len(tab_names)
            tab_names.append("Profiles")
        tab_names.append("Diagnostics")
        tabs = st.tabs(tab_names)

        with tabs[0]:
            checks = normalized.get("readiness_checks") or []
            if checks:
                st_df_safe(pd.DataFrame(checks), hide_index=True, width='stretch')
            else:
                st.info("No readiness checks defined for this migration type yet.")

        # ---------- Summary (grid)
        with tabs[1]:
            st.markdown("### Summary")
            charmap = {row.get("PARAMETER") or row.get("parameter"): row.get("VALUE") or row.get("value") for row in (snapshot.get("nls") or [])}
            charset = charmap.get("NLS_CHARACTERSET")
            ncharset = charmap.get("NLS_NCHAR_CHARACTERSET")
            grid_rows = [
                {"Field": "DB Unique Name", "Value": db_info.get("DB_UNIQUE_NAME") or db_info.get("db_unique_name")},
                {"Field": "DB Name", "Value": db_info.get("NAME") or db_info.get("name")},
                {"Field": "DBID", "Value": db_info.get("DBID") or db_info.get("dbid")},
                {"Field": "Host", "Value": inst.get("HOST_NAME") or inst.get("host_name") or conn_meta.get("host")},
                {"Field": "Version", "Value": inst.get("VERSION_FULL") or inst.get("version_full")},
                {"Field": "Platform", "Value": db_info.get("PLATFORM_NAME") or db_info.get("platform_name")},
                {"Field": "Charset", "Value": charset},
                {"Field": "NCharset", "Value": ncharset},
                {"Field": "Timezone file", "Value": (snapshot.get('timezone') or {}).get('VERSION') if isinstance(snapshot.get('timezone'), dict) else snapshot.get('timezone')},
                {"Field": "Service", "Value": conn_meta.get("service_name")},
            ]
            grid = pd.DataFrame(grid_rows)
            grid = grid.dropna(how="all")
            st_df_safe(grid, hide_index=True, width='stretch')

        # ---------- Schemas / tablespaces / dirs
        with tabs[2]:
            schemas = snapshot.get("schemas_all") or []
            if isinstance(schemas, list) and schemas:
                if all(isinstance(s, str) for s in schemas):
                    df = pd.DataFrame({"Schema": schemas})
                else:
                    df = pd.DataFrame(schemas)
                    df.columns = [c.title().replace("_", " ") for c in df.columns]
                st_df_safe(df, hide_index=True, width='stretch')
            else:
                st.info("No schemas returned.")

        with tabs[3]:
            tbs = snapshot.get("tablespaces") or []
            if isinstance(tbs, list) and tbs:
                if all(isinstance(t, str) for t in tbs):
                    df = pd.DataFrame({"Tablespace": tbs})
                else:
                    df = pd.DataFrame(tbs)
                st_df_safe(df, hide_index=True, width='stretch')
            else:
                st.info("No tablespaces returned.")

        with tabs[4]:
            dirs = snapshot.get("directories") or []
            if isinstance(dirs, list) and dirs:
                df = pd.DataFrame(dirs)
                df.columns = [c.title().replace("_", " ") for c in df.columns]
                st_df_safe(df, hide_index=True, width='stretch')
            else:
                st.info("No directories returned.")

        with tabs[5]:
            nls = snapshot.get("nls") or []
            tz = snapshot.get("timezone")
            if nls:
                st.markdown("**NLS Parameters**")
                st_df_safe(pd.DataFrame(nls), hide_index=True, width='stretch')
            if tz:
                tz_val = tz.get("VERSION") if isinstance(tz, dict) else tz
                st.markdown("**Timezone file version**")
                st.write(tz_val)
            if not nls and not tz:
                st.info("No NLS/TZ data.")

        if cloud_tab_idx is not None:
            with tabs[cloud_tab_idx]:
                st.markdown("### Cloud Identity")
                cloud_grid_rows = [
                    {"Field": "Database Name", "Value": cloud_identity.get("DATABASE_NAME")},
                    {"Field": "Region", "Value": cloud_identity.get("REGION")},
                    {"Field": "Tenant OCID", "Value": cloud_identity.get("TENANT_OCID")},
                    {"Field": "Database OCID", "Value": cloud_identity.get("DATABASE_OCID")},
                    {"Field": "Compartment OCID", "Value": cloud_identity.get("COMPARTMENT_OCID")},
                    {"Field": "Outbound IP Address", "Value": cloud_identity.get("OUTBOUND_IP_ADDRESS")},
                    {"Field": "Public Domain Name", "Value": cloud_identity.get("PUBLIC_DOMAIN_NAME")},
                    {"Field": "Autoscalable Storage", "Value": cloud_identity.get("AUTOSCALABLE_STORAGE")},
                    {"Field": "Base Size", "Value": cloud_identity.get("BASE_SIZE")},
                    {"Field": "Infrastructure", "Value": cloud_identity.get("INFRASTRUCTURE")},
                    {"Field": "Service", "Value": cloud_identity.get("SERVICE")},
                    {"Field": "Applications", "Value": cloud_identity.get("APPLICATIONS")},
                    {"Field": "Compute Model", "Value": cloud_identity.get("COMPUTE_MODEL")},
                    {"Field": "Compute Count", "Value": cloud_identity.get("COMPUTE_COUNT")},
                    {"Field": "Compute Autoscaling", "Value": cloud_identity.get("COMPUTE_AUTOSCALING")},
                ]
                cloud_grid = pd.DataFrame(cloud_grid_rows)
                st_df_safe(cloud_grid, hide_index=True, width='stretch')

        if profiles_tab_idx is not None:
            with tabs[profiles_tab_idx]:
                try:
                    profile_rows, profile_error = discovery_profile_rows(snapshot)
                except ValueError as exc:
                    st.error("ZEUS could not read the custom profile details in this discovery snapshot.")
                    with st.expander("Technical details", expanded=False):
                        st.code(str(exc))
                else:
                    if profile_error:
                        st.error("Profile discovery did not complete.")
                        with st.expander("Technical details", expanded=False):
                            st.code(profile_error)
                    elif profile_rows:
                        script = "\n\n".join(
                            row["PROFILE_DDL"].rstrip().rstrip(";") + ";"
                            for row in profile_rows
                        )
                        count_col, download_col = st.columns([0.7, 0.3], vertical_alignment="center")
                        with count_col:
                            st.caption(
                                f"{len(profile_rows)} custom profile"
                                f"{'s' if len(profile_rows) != 1 else ''} returned"
                            )
                        with download_col:
                            st.download_button(
                                "Download all profile DDL",
                                script,
                                file_name=f"{con_name}_profiles.sql",
                                mime="text/sql",
                                width='stretch',
                            )
                        for row in profile_rows:
                            with st.expander(row["PROFILE"]):
                                profile_script = row["PROFILE_DDL"].rstrip().rstrip(";") + ";"
                                st.download_button(
                                    "Download profile SQL",
                                    profile_script,
                                    file_name=f"{row['PROFILE']}.sql",
                                    mime="text/sql",
                                    key=f"download-profile-{row['PROFILE']}",
                                )
                                st.code(row["PROFILE_DDL"], language="sql")
                    else:
                        st.info("No custom profile DDL returned for this logical discovery snapshot.")

        with tabs[-1]:
            render_diagnostics(snapshot)
