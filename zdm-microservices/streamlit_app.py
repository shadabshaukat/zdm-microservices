import os
import json
import re
import pandas as pd
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, List

import requests
import streamlit as st
from requests.auth import HTTPBasicAuth
try:
    from .backend_auth import first_user_defaults  # package-style
except ImportError:
    from backend_auth import first_user_defaults  # script-style


# Wrapper to avoid Arrow type errors from mixed object columns.
def st_df_safe(df: pd.DataFrame, **kwargs):
    # Coerce to DataFrame if caller passed list/dict/etc.
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    try:
        return st.dataframe(df, **kwargs)
    except Exception:
        df2 = df.copy()
        for col in df2.columns:
            if df2[col].dtype == object:
                df2[col] = df2[col].apply(
                    lambda v: v.decode() if isinstance(v, (bytes, bytearray)) else v
                ).astype(str)
        return st.dataframe(df2, **kwargs)


# -----------------------------
# Helpers
# -----------------------------
def api_request(
    method: str,
    path: str,
    base_url: str,
    auth: HTTPBasicAuth,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    quiet: bool = False,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            params=params,
            auth=auth,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = None
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text if exc.response is not None else "HTTP error"
        if not quiet:
            st.error(f"API error ({exc.response.status_code if exc.response else 'HTTP'}): {detail}")
        return None
    except requests.RequestException as exc:
        if not quiet:
            st.error(f"Request failed: {exc}")
        return None

    try:
        return response.json()
    except ValueError:
        return {"raw": response.text}


def generate_rsp_lines(preview_payload: Dict[str, Any]) -> List[str]:
    """Convert the UI preview payload into final response-file lines (KEY=VALUE).

    This is intentionally frontend-owned logic so the backend can stay write-only.
    """
    def normalize_value(value: Any) -> str:
        if isinstance(value, bool):
            return "TRUE" if value else "FALSE"
        if isinstance(value, str):
            if value.lower() == "true":
                return "TRUE"
            if value.lower() == "false":
                return "FALSE"
            return value
        return str(value)

    out: List[str] = []

    for k, v in preview_payload.items():
        # not part of the rsp content
        if k in ("project", "filename"):
            continue

        if v is None:
            continue

        # Expand special list/dict structures into numbered lines
        if k == "include_schemas" and isinstance(v, list):
            for i, sch in enumerate(v, start=1):
                sch_s = str(sch).strip()
                if not sch_s:
                    continue
                out.append(f"INCLUDEOBJECTS-{i}=owner:{sch_s}")
            continue

        if k == "DATAPUMPSETTINGS_METADATAREMAPS" and isinstance(v, list):
            for i, remap in enumerate(v, start=1):
                remap_type = old_value = new_value = None
                if isinstance(remap, dict):
                    remap_type = remap.get("type")
                    old_value = remap.get("oldValue")
                    new_value = remap.get("newValue")
                elif isinstance(remap, (list, tuple)) and len(remap) == 3:
                    remap_type, old_value, new_value = remap
                if remap_type is None or old_value is None or new_value is None:
                    continue
                out.append(
                    f"DATAPUMPSETTINGS_METADATAREMAPS-{i}=type:{remap_type}, oldValue:{old_value}, newValue:{new_value}"
                )
            continue

        if k == "additional" and isinstance(v, dict):
            for ak, av in v.items():
                if av is None:
                    continue
                av_s = normalize_value(av).strip()
                if av_s == "":
                    continue
                out.append(f"{ak}={av_s}")
            continue

        # Default: write key=value
        v_s = normalize_value(v).strip()
        if v_s == "":
            continue
        out.append(f"{k}={v_s}")

    return out


def get_projects_list(api_base: str, auth: HTTPBasicAuth) -> Dict[str, Any]:
    proj = api_request("get", "/projects", api_base, auth, quiet=True) or {}
    return proj if isinstance(proj, dict) else {}


def ping_backend(api_base: str, auth: HTTPBasicAuth) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[str]]:
    """Try health/version endpoints and return success plus last error detail."""
    last_error: Optional[str] = None
    for ep in ["/health", "/version"]:
        url = f"{api_base}{ep}"
        try:
            resp = requests.get(url, auth=auth, timeout=8)
            resp.raise_for_status()
            try:
                return True, ep, resp.json(), None
            except ValueError:
                return True, ep, {"raw": resp.text}, None
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
    return False, "", None, last_error


def is_blank(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def caption_key(key: str, extra: str = "") -> str:
    """Return the ZDM parameter key (kept for templating/refactors)."""
    return key


def param_help(key: str, extra: str = "") -> str:
    """Tooltip helper for Streamlit `help=`."""
    if extra:
        return f"Param: {key} · {extra}"
    return f"Param: {key}"


def field_label(label: str, required: bool) -> str:
    return f"{label}{' *' if required else ''}"


def compute_completion(required_items: List[Tuple[str, Any]]) -> Tuple[float, List[str]]:
    missing = [name for name, val in required_items if is_blank(val)]
    total = max(1, len(required_items))
    done = total - len(missing)
    return done / total, missing


def extract_job_id(text: str) -> Optional[str]:
    """Best-effort job id extractor from CLI output."""
    if not text:
        return None
    match = re.search(r"job\s*id\s*[:=]\s*([A-Za-z0-9_.\-]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"jobid\s*[:=]\s*([A-Za-z0-9_.\-]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"job\s*-?id\s+([A-Za-z0-9_.\-]+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return None


# -----------------------------
# Branding
# -----------------------------
APP_LONG_NAME = "ZEUS – ZDM Enqueue URL Services"
st.set_page_config(page_title=APP_LONG_NAME, layout="wide")
st.title(APP_LONG_NAME)
st.caption("A lightweight UI on top of ZDM CLI via your FastAPI microservice.")


# -----------------------------
# Defaults / session state
# -----------------------------
# Use hostname matching the certificate CN (localhost) to avoid TLS hostname errors.
default_base = os.getenv("API_BASE_URL", f"https://localhost:{os.getenv('ZEUS_PORT', '8001')}").rstrip("/")
def _load_zeus_auth_defaults() -> Tuple[str, str]:
    """Read first user/pass from auth helper."""
    return first_user_defaults()

auth_user_file, auth_pass_file = _load_zeus_auth_defaults()

default_user = os.getenv("ZDM_API_USER", auth_user_file or "zdmuser")
default_password = os.getenv("ZDM_API_PASSWORD", auth_pass_file or "YourPassword123#_")

if "api_base" not in st.session_state:
    st.session_state["api_base"] = default_base
if "username" not in st.session_state:
    st.session_state["username"] = default_user
if "password" not in st.session_state:
    st.session_state["password"] = default_password

api_base = st.session_state.get("api_base", "").rstrip("/")
username = st.session_state.get("username", "")
password = st.session_state.get("password", "")
auth = HTTPBasicAuth(username, password)


# -----------------------------
# Sidebar nav
# -----------------------------
with st.sidebar:
    st.subheader("Navigation")
    nav_options = {
        "Backend Connection": "settings",
        "DB Connections": "connections",
        "DB Discovery": "discovery",
        "Projects": "projects",
        "Response Files": "response",
        "Create Job": "createjob",
        "Run Job": "runjob",
        "Monitor Jobs": "jobs",
        "Wallets & Credentials": "wallet",
    }
    nav_choice = st.radio("Go to", list(nav_options.keys()))
    st.divider()
    st.caption(f"API: {st.session_state.get('api_base','') or 'not set'}")
    st.caption(f"User: {st.session_state.get('username','') or 'not set'}")

section = nav_options.get(nav_choice, "settings")

if section != "settings" and not api_base:
    st.warning("Please configure Backend Connection first.")
    st.stop()


# -----------------------------
# Settings
# -----------------------------
if section == "settings":
    st.subheader("Backend Connection")
    st.caption("Configure the FastAPI endpoint and Basic Auth used by ZEUS UI.")

    left, right = st.columns([1.2, 1])

    with left:
        with st.form("backend_settings"):
            new_api_base = st.text_input("API Base URL", value=api_base or default_base).rstrip("/")
            new_username = st.text_input("Username", value=username or default_user)
            new_password = st.text_input("Password", value=password or default_password, type="password")
            save_settings = st.form_submit_button("Save", type="primary")
        if save_settings:
            st.session_state["api_base"] = new_api_base
            st.session_state["username"] = new_username
            st.session_state["password"] = new_password
            st.success("Backend settings updated.")

    with right:
        st.markdown("### Backend Status")
        if st.button("Ping backend", type="primary"):
            ok, used, data, err = ping_backend(api_base, auth)
            if ok:
                st.success(f"Backend reachable via `{used}`")
                st.json(data)
            else:
                st.error(
                    "Backend unreachable. Check API_BASE_URL and TLS trust. "
                    "If using self-signed cert, set REQUESTS_CA_BUNDLE to zeus.crt."
                )
                if err:
                    st.caption(f"Ping detail: {err}")



# -----------------------------
# DB Connections
# -----------------------------
elif section == "connections":
    st.subheader("DB Connections")

    adb_types = ["ADBD", "ADBS", "ADBCC"]
    dbtype_options = adb_types + ["EXADATA", "ORACLE"]

    col_form, col_table = st.columns([1.15, 1.1])

    with col_form:
        st.markdown("### Define connection")

        # NOTE: We intentionally do NOT wrap these inputs in st.form().
        # Widgets inside a form do not trigger re-runs until submit, which breaks conditional UI
        # such as hiding/showing the wallet uploader.
        name = st.text_input(
            "Connection name",
            help="Identifier used in later test/migration calls",
            key="conn_name",
        )
        db_type = st.selectbox("DB Type", dbtype_options, index=0, key="conn_db_type")

        host = st.text_input("Host", key="conn_host")
        port = st.number_input("Port", min_value=1, max_value=65535, value=1521, step=1, key="conn_port")
        service_name = st.text_input("Service Name", key="conn_service_name")
        db_user = st.text_input("DB username", key="conn_db_user")

        is_adb = db_type in adb_types
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
                help="For EXA*/ORACLE; default is TCP",
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
            if not all([name, host, service_name, db_user]):
                st.error("Name, host, service_name, and username are required.")
            elif wallet_needed and not upload_file:
                st.error("Wallet is required for this DB type/protocol. Please upload the wallet.")
            else:
                payload = {
                    "name": name,
                    "host": host,
                    "port": int(port),
                    "service_name": service_name,
                    "username": db_user,
                    "db_type": db_type,
                    "protocol": "TCPS" if use_tcps else "TCP",
                    "allow_tls_without_wallet": use_tls_no_wallet,
                }
                data = api_request("post", "/dbconnection", api_base, auth, payload=payload)
                if data:
                    st.success(data.get("message", "Connection saved"))
                    if upload_file:
                        try:
                            files = {"wallet": (upload_file.name, upload_file.getvalue())}
                            resp = requests.post(
                                f"{api_base}/dbconnection/{name}/uploadTlsWallet",
                                files=files,
                                auth=auth,
                                timeout=30,
                            )
                            resp.raise_for_status()
                            st.success("TLS wallet uploaded.")
                        except Exception as exc:
                            st.error(f"Wallet upload failed: {exc}")
                    st.json(data)
                    st.session_state["last_saved_conn"] = name


    with col_table:
        st.markdown("### Saved connections")
        conns = api_request("get", "/dbconnections", api_base, auth, quiet=True) or {}
        if not conns:
            st.info("No connections saved yet.")
        else:
            rows = []
            for name, info in conns.items():
                rows.append(
                    {
                        "Name": name,
                        "DB Type": info.get("db_type", ""),
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
                            "db_type": row["DB Type"],
                            "host": row["Host"],
                            "port": int(row["Port"]),
                            "service_name": row["Service"],
                            "username": conns[name].get("username", ""),
                            "protocol": row["Protocol"],
                            "allow_tls_without_wallet": bool(row["TLS w/o wallet"]),
                        }
                        resp = api_request("post", "/dbconnection", api_base, auth, payload=payload)
                        if resp:
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
                            resp = api_request("delete", f"/dbconnection/{name}", api_base, auth)
                            if resp:
                                deleted += 1
                        st.success(f"Deleted {deleted} connection{'s' if deleted != 1 else ''}. Refresh to update list.")

        st.markdown("### Test connection")
        last_saved = st.session_state.get("last_saved_conn", "-- Select --")
        options = ["-- Select --"] + list(conns.keys())
        default_idx = options.index(last_saved) if last_saved in options else 0
        with st.form("test_connection"):
            test_name = st.selectbox("Connection", options, index=default_idx)
            temp_password = st.text_input("DB password (not stored)", type="password")
            test_clicked = st.form_submit_button("Test", type="primary")

        if test_clicked:
            if test_name == "-- Select --":
                st.error("Please select a connection.")
            else:
                cinfo = conns.get(test_name, {})
                wallet_required = (str(cinfo.get("protocol", "")).upper() == "TCPS") and not cinfo.get("allow_tls_without_wallet")
                if wallet_required and not cinfo.get("tls_wallet_uploaded_dir"):
                    st.error("Upload a TLS wallet for this connection before testing.")
                    st.stop()
                if not temp_password:
                    st.error("Enter the DB password to test this connection.")
                    st.stop()
                payload = {
                    "name": test_name,
                    "password": temp_password,
                }
                data = api_request("post", "/dbconnection/test", api_base, auth, payload=payload)
                if data:
                    st.success(data.get("message", "Test succeeded"))
                    st.json(data)


# -----------------------------
# Projects
# -----------------------------
elif section == "projects":
    st.subheader("Projects")
    st.caption("A Project groups source & target connections; its name is also used as the response filename.")

    connections_cache = api_request("get", "/dbconnections", api_base, auth, quiet=True) or {}
    conn_names = ["-- Select connection --"] + list(connections_cache.keys())

    with st.form("save_project"):
        project_name = st.text_input(
            "Project name",
            help="Lowercase letters + numbers + dash/underscore only. Used as response file name.",
        )
        source_conn = st.selectbox("Source connection", conn_names)
        target_conn = st.selectbox("Target connection", conn_names, key="target_conn_select")
        project_clicked = st.form_submit_button("Save project", type="primary")

    def valid_project(name: str) -> bool:
        return bool(name) and name.islower() and all(c.isalnum() or c in "-_" for c in name)

    if project_clicked:
        if not valid_project(project_name):
            st.error("Project name must be lowercase and contain only a-z, 0-9, dash or underscore.")
        elif source_conn == "-- Select connection --" or target_conn == "-- Select connection --":
            st.error("Source and target connection are required.")
        else:
            payload = {"name": project_name, "source_connection": source_conn, "target_connection": target_conn}
            data = api_request("post", "/project", api_base, auth, payload=payload)
            if data:
                st.success(data.get("message", "Project saved"))
                st.json(data)


# -----------------------------
# Response Files (Productized, REAL-TIME, CONDITIONAL UI)
# -----------------------------
elif section == "response":
    header_l, header_r = st.columns([4.5, 1.5], vertical_alignment="center")
    with header_l:
        st.markdown("## Response Files")
    with header_r:
        projects_resp = get_projects_list(api_base, auth)
        project_names = list(projects_resp.keys()) if isinstance(projects_resp, dict) else []
        project = st.selectbox(
            "Project",
            ["-- Select project --"] + project_names,
            key="rf_project",
            label_visibility="collapsed",
        )


    if project == "-- Select project --":
        st.info("Select a project to start.")
        st.stop()

    # options
    dbtype_options = {
        "Logical": ["ORACLE", "ADBD", "ADBS", "ADBCC", "EXADATA"],
        "Hybrid": ["ORACLE", "EXADATA", "ODA"],
    }
    platform_type_options = ["VMDB", "EXACS", "EXACC", "NON_CLOUD"]
    jobmode_options = ["SCHEMA", "TABLE", "FULL", "TRANSPORTABLE"]
    remap_type_options = ["REMAP_TABLESPACE", "REMAP_SCHEMA", "REMAP_DATAFILE"]
    migration_type_options = ["Logical", "Physical", "Hybrid"]
    method_options_map = {
        "Logical": ["OFFLINE_LOGICAL", "ONLINE_LOGICAL"],
        "Physical": ["ONLINE_PHYSICAL", "OFFLINE_PHYSICAL"],
        "Hybrid": ["OFFLINE_XTTS"],
    }
    medium_options_map = {
        "Logical": ["OSS", "NFS", "DBLINK", "COPY", "AMAZON3"],
        "Physical": ["OSS", "EXTBACKUP", "ZDLRA", "NFS", "DIRECT"],
        "Hybrid": ["NFS"],
    }
    disallowed_methods = {"ONLINE_LOGICAL", "OFFLINE_XTTS"}

    # wallets cache
    wallets_resp = api_request("get", "/credentialWallets", api_base, auth, quiet=True) or {}
    wallet_map = {}
    if isinstance(wallets_resp, dict):
        wallet_map = {
            w.get("name"): w.get("path")
            for w in wallets_resp.get("wallets", [])
            if w.get("name") and w.get("path")
        }
    wallet_names = ["-- Select wallet --"] + list(wallet_map.keys())

    # manual override state (init ONCE, don't overwrite later)
    if "rf_use_manual" not in st.session_state:
        st.session_state["rf_use_manual"] = False
    if "rf_manual_text" not in st.session_state:
        st.session_state["rf_manual_text"] = ""  # filled by "Reset" button or first-time below
    if "rf_form_loaded_project" not in st.session_state:
        st.session_state["rf_form_loaded_project"] = ""

    col_form, col_gap, col_preview = st.columns([1.22, 0.08, 1])

    with col_gap:
        st.write("")

    # ---------------- form side ----------------
    def parse_rsp_content(text: str) -> Dict[str, Any]:
        parsed: Dict[str, Any] = {"kv": {}, "include_schemas": [], "remaps": []}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip()
            if key.startswith("INCLUDEOBJECTS-") and val.lower().startswith("owner:"):
                parsed["include_schemas"].append(val.split(":", 1)[1].strip())
                continue
            if key.startswith("DATAPUMPSETTINGS_METADATAREMAPS-"):
                parts = {}
                for seg in val.split(","):
                    if ":" in seg:
                        k2, v2 = seg.split(":", 1)
                        parts[k2.strip()] = v2.strip()
                if parts.get("type") and parts.get("oldValue") and parts.get("newValue"):
                    parsed["remaps"].append(
                        {"type": parts["type"], "oldValue": parts["oldValue"], "newValue": parts["newValue"]}
                    )
                continue
            parsed["kv"][key] = val
        return parsed

    def apply_rsp_to_state(project_name: str):
        rsp_resp = api_request("get", f"/responsefile/{project_name}", api_base, auth, quiet=True)
        if not (isinstance(rsp_resp, dict) and rsp_resp.get("status") == "success"):
            return
        content = rsp_resp.get("content", "")
        parsed = parse_rsp_content(content)
        kv = parsed.get("kv", {})
        mapping = {
            "MIGRATION_METHOD": "rf_migration_method",
            "DATA_TRANSFER_MEDIUM": "rf_medium",
            "TARGETDATABASE_DBTYPE": "rf_target_dbtype",
            "TARGETDATABASE_OCID": "rf_target_ocid",
            "TARGETDATABASE_ADMINUSERNAME": "rf_target_admin",
            "TARGETDATABASE_CONNECTIONDETAILS_SERVICENAME": "rf_target_service",
            "SOURCEDATABASE_ADMINUSERNAME": "rf_src_admin",
            "SOURCEDATABASE_CONNECTIONDETAILS_HOST": "rf_src_host",
            "SOURCEDATABASE_CONNECTIONDETAILS_PORT": "rf_src_port",
            "SOURCEDATABASE_CONNECTIONDETAILS_SERVICENAME": "rf_src_service",
            "DATAPUMPSETTINGS_JOBMODE": "rf_jobmode",
            "DATAPUMPSETTINGS_METADATAFIRST": "rf_metadatafirst",
            "DATAPUMPSETTINGS_DELETEDUMPSINOSS": "rf_deletedumps",
            "DATAPUMPSETTINGS_FIXINVALIDOBJECTS": "rf_fixinvalid",
            "DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_NAME": "rf_export_dir_name",
            "DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_PATH": "rf_export_dir_path",
            "TABLESPACEDETAILS_AUTOREMAP": "rf_autoremap",
            "TABLESPACEDETAILS_REMAPTARGET": "rf_remap_target",
            "TABLESPACEDETAILS_REMAPTEMPTARGET": "rf_remap_temp_target",
            "DATAPUMPSETTINGS_DATABUCKET_NAMESPACENAME": "rf_bucket_ns",
            "DATAPUMPSETTINGS_DATABUCKET_BUCKETNAME": "rf_bucket_name",
            "OCIAUTHENTICATIONDETAILS_REGIONID": "rf_oci_region",
            "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_TENANTID": "rf_oci_tenant",
            "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_USERID": "rf_oci_user",
            "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_FINGERPRINT": "rf_oci_fp",
            "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_PRIVATEKEYFILE": "rf_oci_pk",
            "PLATFORM_TYPE": "rf_platform_type",
            "HOST": "rf_phys_oss_host",
            "OPC_CONTAINER": "rf_phys_opc_container",
            "WALLET_TARGETADMIN": "rf_wallet_target_path",
            "WALLET_SOURCECONTAINER": "rf_wallet_source_path",
        }
        for k, state_key in mapping.items():
            if k in kv:
                val = kv[k]
                if state_key == "rf_src_port":
                    try:
                        val = int(val)
                    except Exception:
                        pass
                st.session_state[state_key] = val

        # include schemas
        inc = parsed.get("include_schemas") or []
        st.session_state["rf_include_schemas"] = "\n".join(inc)

        # remaps/additional prefills (use separate keys to avoid widget assignment errors)
        remaps = parsed.get("remaps") or []
        if remaps:
            st.session_state["rf_remap_prefill"] = pd.DataFrame(remaps)

        additional_rows = []
        for k, v in kv.items():
            if k in mapping:
                continue
            additional_rows.append({"key": k, "value": v})
        if additional_rows:
            st.session_state["rf_additional_prefill"] = pd.DataFrame(additional_rows)

        # wallet select boxes: map path back to wallet name if known
        path_to_wallet = {v: k for k, v in wallet_map.items()}
        tgt_path = kv.get("WALLET_TARGETADMIN")
        src_path = kv.get("WALLET_SOURCECONTAINER")
        if tgt_path and tgt_path in path_to_wallet:
            st.session_state["rf_wallet_target"] = path_to_wallet[tgt_path]
        if src_path and src_path in path_to_wallet:
            st.session_state["rf_wallet_source"] = path_to_wallet[src_path]

        st.session_state["rf_form_loaded_project"] = project_name

    if st.session_state.get("rf_form_loaded_project") != project:
        apply_rsp_to_state(project)

    with col_form:
        # Wider button columns to avoid label wrapping
        row_p, row_b1, row_b2 = st.columns([6, 1.4, 1.4], vertical_alignment="center")
        with row_p:
            st.markdown(f"### Project: `{project}`")
        # Section controls
        if "rf_expand_all" not in st.session_state:
            st.session_state["rf_expand_all"] = False
        with row_b1:
            if st.button("Expand", key="rf_expand_all_btn", width='stretch'):
                st.session_state["rf_expand_all"] = True
        with row_b2:
            if st.button("Collapse", key="rf_collapse_all_btn", width='stretch'):
                st.session_state["rf_expand_all"] = False

        expand_all = st.session_state.get("rf_expand_all", False)

        # ---- Migration basics
        st.markdown("#### Basics")
        migration_type = st.selectbox("Migration type", migration_type_options, key="rf_migration_type", help=param_help("MIGRATION_TYPE"))

        method_opts = method_options_map.get(migration_type, [])
        default_method = method_opts[0] if method_opts else ""
        migration_method = st.selectbox("Migration method", method_opts, key="rf_migration_method", help=param_help("MIGRATION_METHOD"))

        if migration_method in disallowed_methods:
            st.warning(f"{migration_method} is not selectable yet; using {default_method}.")
            migration_method = default_method

        medium_options = medium_options_map.get(migration_type, ["OSS"])
        if st.session_state.get("rf_medium") not in medium_options:
            st.session_state["rf_medium"] = medium_options[0]

        medium = st.selectbox("Data transfer medium", medium_options, key="rf_medium", help=param_help("DATA_TRANSFER_MEDIUM"))

        medium_upper = (medium or "").upper()
        is_oss = medium_upper == "OSS"

        st.divider()

        # ---- Target / Source (collapsible; keep variables initialized for preview builder)
        expand_all = st.session_state.get("rf_expand_all", False)

        target_platform = None
        target_ocid = ""
        target_dbtype = None
        target_admin = ""
        target_service = ""
        wallet_target_path = ""
        src_admin = ""
        src_host = ""
        src_port = 1521
        src_service = ""
        wallet_source_path = ""

        with st.expander("Source & Target ", expanded=expand_all):
            if migration_type == "Logical":
                tab_src, tab_tgt = st.tabs(["Source database", "Target database"])

                with tab_src:
                    src_host = st.text_input(field_label("Source host", True), key="rf_src_host", help=param_help("SOURCEDATABASE_CONNECTIONDETAILS_HOST"))

                    if "rf_src_port" in st.session_state:
                        src_port = st.number_input(
                            field_label("Source port", True),
                            min_value=1,
                            max_value=65535,
                            step=1,
                            key="rf_src_port",
                            help=param_help("SOURCEDATABASE_CONNECTIONDETAILS_PORT"),
                        )
                    else:
                        src_port = st.number_input(
                            field_label("Source port", True),
                            min_value=1,
                            max_value=65535,
                            value=1521,
                            step=1,
                            key="rf_src_port",
                            help=param_help("SOURCEDATABASE_CONNECTIONDETAILS_PORT"),
                        )

                    src_service = st.text_input(field_label("Source service name", True), key="rf_src_service", help=param_help("SOURCEDATABASE_CONNECTIONDETAILS_SERVICENAME"))

                    src_admin = st.text_input(
                        field_label("Source admin username", True),
                        value="system",
                        key="rf_src_admin",
                    help=param_help("SOURCEDATABASE_ADMINUSERNAME"),
                    )

                    wallet_source_name = st.selectbox(
                        field_label("Source wallet", True),
                        wallet_names,
                        key="rf_wallet_source",
                    help=param_help("WALLET_SOURCECONTAINER"),
                    )
                    wallet_source_path = wallet_map.get(wallet_source_name, "") if wallet_source_name != "-- Select wallet --" else ""

                with tab_tgt:
                    target_dbtype = st.selectbox(
                        field_label("Target DB type", True),
                        dbtype_options["Logical"],
                        key="rf_target_dbtype",
                    help=param_help("TARGETDATABASE_DBTYPE"),
                    )

                    target_ocid = st.text_input(field_label("Target ADB OCID", True), key="rf_target_ocid", help=param_help("TARGETDATABASE_OCID"))

                    target_service = st.text_input(
                        field_label("Target service name", True),
                        key="rf_target_service",
                    help=param_help("TARGETDATABASE_CONNECTIONDETAILS_SERVICENAME"),
                    )

                    target_admin = st.text_input(
                        field_label("Target admin username", True),
                        value="admin",
                        key="rf_target_admin",
                    help=param_help("TARGETDATABASE_ADMINUSERNAME"),
                    )

                    wallet_target_name = st.selectbox(
                        field_label("Target admin wallet", True),
                        wallet_names,
                        key="rf_wallet_target",
                    help=param_help("WALLET_TARGETCONTAINER"),
                    )
                    wallet_target_path = wallet_map.get(wallet_target_name, "") if wallet_target_name != "-- Select wallet --" else ""

            elif migration_type == "Physical":
                st.caption("Physical migrations use platform settings rather than ADB target/source connection fields here.")
                target_platform = st.selectbox(field_label("Platform type", True), platform_type_options, key="rf_platform_type", help=param_help("PLATFORM_TYPE"))

            else:  # Hybrid
                target_dbtype = st.selectbox(field_label("Target DB type", True), dbtype_options["Hybrid"], key="rf_hybrid_dbtype", help=param_help("TARGETDATABASE_DBTYPE"))

        st.divider()

        # ---- Transfer settings (conditional)
        bucket_ns = bucket_name = ""
        region = tenant = user_ocid = fingerprint = pk_file = ""
        oss_host = opc_container = ""

        with st.expander("Transfer settings", expanded=expand_all):
            if is_oss and migration_type == "Logical":
                st.markdown("**Object Storage (Logical)**")
                bucket_ns = st.text_input(field_label("Namespace", True), key="rf_bucket_ns", help=param_help("DATAPUMPSETTINGS_DATABUCKET_NAMESPACENAME"))

                bucket_name = st.text_input(field_label("Bucket name", True), key="rf_bucket_name", help=param_help("DATAPUMPSETTINGS_DATABUCKET_BUCKETNAME"))

            elif is_oss and migration_type == "Physical":
                st.markdown("**Object Storage (Physical)**")
                oss_host = st.text_input(field_label("Object Storage endpoint", True), key="rf_phys_oss_host", help=param_help("HOST"))

                opc_container = st.text_input(field_label("Bucket / container", True), key="rf_phys_opc_container", help=param_help("OPC_CONTAINER"))
            else:
                st.caption("No Object Storage fields for current selection.")

        # ---- OCI authentication (separate section for logical OSS)
        if is_oss and migration_type == "Logical":
            with st.expander("OCI authentication", expanded=expand_all):
                region = st.text_input(field_label("Region", True), key="rf_oci_region", help=param_help("OCIAUTHENTICATIONDETAILS_REGIONID"))

                tenant = st.text_input(field_label("Tenant OCID", True), key="rf_oci_tenant", help=param_help("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_TENANTID"))

                user_ocid = st.text_input(field_label("User OCID", True), key="rf_oci_user", help=param_help("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_USERID"))

                fingerprint = st.text_input(field_label("API key fingerprint", True), key="rf_oci_fp", help=param_help("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_FINGERPRINT"))

                pk_file = st.text_input(field_label("Private key file path", True), key="rf_oci_pk", help=param_help("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_PRIVATEKEYFILE"))

        # ---- Data Pump (logical/hybrid)
        include_schemas_raw = ""
        remap_rows = pd.DataFrame()
        additional_rows = pd.DataFrame([{"key": "", "value": ""}])

        jobmode = metadatafirst = deletedumps = fixinvalid = ""
        export_dir_name = export_dir_path = ""
        autoremap = remap_target = remap_temp_target = ""

        if migration_type in ["Logical", "Hybrid"]:
            st.divider()
            with st.expander("Data Pump", expanded=expand_all):
                jobmode = st.selectbox(field_label("Job mode", True), jobmode_options, key="rf_jobmode", help=param_help("DATAPUMPSETTINGS_JOBMODE"))

                metadatafirst = st.selectbox(field_label("Metadata first", True), ["TRUE", "FALSE"], index=1, key="rf_metadatafirst", help=param_help("DATAPUMPSETTINGS_METADATAFIRST"))

                deletedumps = st.selectbox(field_label("Delete dumps after success", True), ["TRUE", "FALSE"], index=1, key="rf_deletedumps", help=param_help("DATAPUMPSETTINGS_DELETEDUMPSINOSS"))

                fixinvalid = st.selectbox(field_label("Fix invalid objects", True), ["TRUE", "FALSE"], index=0, key="rf_fixinvalid", help=param_help("DATAPUMPSETTINGS_FIXINVALIDOBJECTS"))

                export_dir_name = st.text_input(field_label("Export directory object", True), value="DATA_PUMP_DIR", key="rf_export_dir_name", help=param_help("DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_NAME"))

                export_dir_path = st.text_input(field_label("Export directory path", True), key="rf_export_dir_path", help=param_help("DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_PATH"))

                with st.expander("Tablespace remap", expanded=expand_all):
                    autoremap = st.selectbox(field_label("Auto remap", True), ["TRUE", "FALSE"], index=0, key="rf_autoremap", help=param_help("TABLESPACEDETAILS_AUTOREMAP"))

                    remap_target = st.text_input(field_label("Default remap target", True), value="DATA", key="rf_remap_target", help=param_help("TABLESPACEDETAILS_REMAPTARGET"))

                    remap_temp_target = st.selectbox(field_label("Remap temp tablespaces", True), ["TRUE", "FALSE"], index=0, key="rf_remap_temp_target", help=param_help("TABLESPACEDETAILS_REMAPTEMPTARGET"))

                    st.caption("Metadata remaps (`DATAPUMPSETTINGS_METADATAREMAPS`)")
                    remap_prefill = st.session_state.pop("rf_remap_prefill", None)
                    remap_rows = st.data_editor(
                        remap_prefill if remap_prefill is not None else pd.DataFrame([{"type": "REMAP_TABLESPACE", "oldValue": "", "newValue": ""}]),
                        num_rows="dynamic",
                        column_config={
                            "type": st.column_config.SelectboxColumn("Type", options=remap_type_options, required=True),
                            "oldValue": st.column_config.TextColumn("Old value", required=True),
                            "newValue": st.column_config.TextColumn("New value", required=True),
                        },
                        key="rf_remap_table",
                    )

                with st.expander("Schemas", expanded=expand_all):
                    include_schemas_raw = st.text_area(field_label("Schemas to include (one per line)", True), height=140, key="rf_include_schemas", help=param_help("include_schemas"))
                    st.caption(f"Count: {len([s for s in include_schemas_raw.splitlines() if s.strip()])}")

            st.divider()
            with st.expander("Additional parameters (key/value)", expanded=expand_all):
                additional_prefill = st.session_state.pop("rf_additional_prefill", None)
                additional_rows = st.data_editor(
                    additional_prefill if additional_prefill is not None else pd.DataFrame([{"key": "RUNCPATREMOTELY", "value": "TRUE"}]),
                    num_rows="dynamic",
                    column_config={
                        "key": st.column_config.TextColumn("Key", required=False),
                        "value": st.column_config.TextColumn("Value", required=False),
                    },
                    key="rf_additional_table",
                )

        st.divider()

# ---- Build preview payload (REAL-TIME)
        include_schemas = [s.strip() for s in include_schemas_raw.splitlines() if s.strip()] if migration_type == "Logical" else []

        remaps_preview = []
        if migration_type == "Logical" and not remap_rows.empty:
            for _, row in remap_rows.iterrows():
                t, o, n = row.get("type", ""), row.get("oldValue", ""), row.get("newValue", "")
                if t and o and n:
                    remaps_preview.append([t, o, n])

        additional_preview: Dict[str, str] = {}
        if not additional_rows.empty:
            for _, row in additional_rows.iterrows():
                k = str(row.get("key", "")).strip()
                v = str(row.get("value", "")).strip()
                if k:
                    additional_preview[k] = v

        preview_payload: Dict[str, Any] = {
            "project": project,
            "filename": project,
            "MIGRATION_METHOD": migration_method,
            "DATA_TRANSFER_MEDIUM": medium,
        }

        # required fields list for progress + summary
        required_items: List[Tuple[str, Any]] = []

        if migration_type == "Logical":
            preview_payload.update(
                {
                    "TARGETDATABASE_OCID": target_ocid,
                    "TARGETDATABASE_DBTYPE": target_dbtype,
                    "TARGETDATABASE_ADMINUSERNAME": target_admin,
                    "TARGETDATABASE_CONNECTIONDETAILS_SERVICENAME": target_service,
                    "WALLET_TARGETADMIN": wallet_target_path,
                    "SOURCEDATABASE_ADMINUSERNAME": src_admin,
                    "SOURCEDATABASE_CONNECTIONDETAILS_HOST": src_host,
                    "SOURCEDATABASE_CONNECTIONDETAILS_PORT": int(src_port),
                    "SOURCEDATABASE_CONNECTIONDETAILS_SERVICENAME": src_service,
                    "WALLET_SOURCECONTAINER": wallet_source_path,
                    "DATAPUMPSETTINGS_JOBMODE": jobmode,
                    "DATAPUMPSETTINGS_METADATAFIRST": metadatafirst,
                    "DATAPUMPSETTINGS_DELETEDUMPSINOSS": deletedumps,
                    "DATAPUMPSETTINGS_FIXINVALIDOBJECTS": fixinvalid,
                    "DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_NAME": export_dir_name,
                    "DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_PATH": export_dir_path,
                    "TABLESPACEDETAILS_AUTOREMAP": autoremap,
                    "TABLESPACEDETAILS_REMAPTARGET": remap_target,
                    "TABLESPACEDETAILS_REMAPTEMPTARGET": remap_temp_target,
                    "include_schemas": include_schemas,
                }
            )

            required_items.extend(
                [
                    ("TARGETDATABASE_OCID", target_ocid),
                    ("TARGETDATABASE_DBTYPE", target_dbtype),
                    ("TARGETDATABASE_ADMINUSERNAME", target_admin),
                    ("TARGETDATABASE_CONNECTIONDETAILS_SERVICENAME", target_service),
                    ("WALLET_TARGETADMIN", wallet_target_path),
                    ("SOURCEDATABASE_ADMINUSERNAME", src_admin),
                    ("SOURCEDATABASE_CONNECTIONDETAILS_HOST", src_host),
                    ("SOURCEDATABASE_CONNECTIONDETAILS_SERVICENAME", src_service),
                    ("WALLET_SOURCECONTAINER", wallet_source_path),
                    ("DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_NAME", export_dir_name),
                    ("DATAPUMPSETTINGS_EXPORTDIRECTORYOBJECT_PATH", export_dir_path),
                    ("include_schemas", "OK" if include_schemas else ""),
                ]
            )

            if is_oss:
                preview_payload.update(
                    {
                        "DATAPUMPSETTINGS_DATABUCKET_NAMESPACENAME": bucket_ns,
                        "DATAPUMPSETTINGS_DATABUCKET_BUCKETNAME": bucket_name,
                        "OCIAUTHENTICATIONDETAILS_REGIONID": region,
                        "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_TENANTID": tenant,
                        "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_USERID": user_ocid,
                        "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_FINGERPRINT": fingerprint,
                        "OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_PRIVATEKEYFILE": pk_file,
                    }
                )
                required_items.extend(
                    [
                        ("DATAPUMPSETTINGS_DATABUCKET_NAMESPACENAME", bucket_ns),
                        ("DATAPUMPSETTINGS_DATABUCKET_BUCKETNAME", bucket_name),
                        ("OCIAUTHENTICATIONDETAILS_REGIONID", region),
                        ("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_TENANTID", tenant),
                        ("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_USERID", user_ocid),
                        ("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_FINGERPRINT", fingerprint),
                        ("OCIAUTHENTICATIONDETAILS_USERPRINCIPAL_PRIVATEKEYFILE", pk_file),
                    ]
                )

        elif migration_type == "Physical":
            preview_payload.update({"PLATFORM_TYPE": target_platform})
            required_items.append(("PLATFORM_TYPE", target_platform))
            if is_oss:
                preview_payload.update({"HOST": oss_host, "OPC_CONTAINER": opc_container})
                required_items.extend([("HOST", oss_host), ("OPC_CONTAINER", opc_container)])

        elif migration_type == "Hybrid":
            preview_payload.update({"TARGETDATABASE_DBTYPE": target_dbtype})
            required_items.append(("TARGETDATABASE_DBTYPE", target_dbtype))

        if remaps_preview:
            preview_payload["DATAPUMPSETTINGS_METADATAREMAPS"] = remaps_preview
        if additional_preview:
            preview_payload["additional"] = additional_preview
        st.divider()

        existing_rsp = api_request("get", f"/responsefile/{project}", api_base, auth, quiet=True)
        submit_label = "Update response file" if existing_rsp and isinstance(existing_rsp, dict) and existing_rsp.get("status") == "success" else "Create response file"
        submit_clicked = st.button(submit_label, type="primary", key="rf_submit_btn")

    
    # ---------------- preview side ----------------
    with col_preview:
        st.markdown("### Payload")
        existing_rsp = api_request("get", f"/responsefile/{project}", api_base, auth, quiet=True)
        tab_auto, tab_manual, tab_rsp = st.tabs(["Preview", "Manual override", "RSP view"])

        use_manual = st.session_state.get("rf_use_manual", False)

        with tab_auto:
            if use_manual and st.session_state.get("rf_manual_text", "").strip():
                st.info("Manual override is enabled. Preview below is your manual JSON.")
                st.code(st.session_state["rf_manual_text"], language="json")
            else:
                st.code(json.dumps(preview_payload, indent=2), language="json")

        with tab_manual:
            # Keep the original JSON override UX:
            # - Reset from current preview
            # - Checkbox to use manual JSON for submit
            top_a, top_b = st.columns([1, 1])

            with top_a:
                reset_clicked = st.button("Reset manual from current preview", key="rf_reset_manual")

            with top_b:
                st.checkbox(
                    "Use manual payload for submit",
                    key="rf_use_manual",
                    help="When enabled, ZEUS will render response-file lines from the JSON below and submit them to /WriteResponseFile.",
                )

            # Safely seed manual text BEFORE the text_area widget is created
            if reset_clicked or not st.session_state.get("rf_manual_text", "").strip():
                st.session_state["rf_manual_text"] = json.dumps(preview_payload, indent=2)

            manual_text = st.text_area(
                "Editable JSON payload",
                height=480,
                key="rf_manual_text",
                help="Edit any key/value. When 'Use manual' is enabled, this JSON is used (UI validation is skipped).",
            )

            if manual_text.strip():
                try:
                    obj = json.loads(manual_text)
                    if not isinstance(obj, dict):
                        st.error("JSON must be an object (dictionary).")
                    else:
                        st.success("JSON is valid.")
                except Exception as exc:
                    st.error(f"Invalid JSON: {exc}")

        with tab_rsp:
            if existing_rsp and isinstance(existing_rsp, dict) and existing_rsp.get("status") == "success":
                st.caption("Existing response file")
                st.code(existing_rsp.get("content", ""), language="ini")
                if st.button("Load existing into manual editor", key="rf_load_existing_btn", type="secondary"):
                    st.session_state["rf_manual_text"] = existing_rsp.get("content", "")
                    st.session_state["rf_use_manual"] = True
                    st.rerun()
            else:
                rsp_lines_preview = generate_rsp_lines(preview_payload)
                st.caption("Would be written as:")
                st.code("\n".join(rsp_lines_preview), language="ini")


# ---- Handle submit (after UI built)
    if submit_clicked:
        use_manual = st.session_state.get("rf_use_manual", False)

        # Default: submit what UI generated
        lines_to_submit: List[str] = generate_rsp_lines(preview_payload)

        
        if use_manual:
            try:
                payload_obj = json.loads(st.session_state.get("rf_manual_text", ""))
            except Exception as exc:
                st.error(f"Manual payload invalid JSON: {exc}")
                st.stop()

            if not isinstance(payload_obj, dict):
                st.error("Manual payload must be a JSON object (dictionary).")
                st.stop()

            lines_to_submit = generate_rsp_lines(payload_obj)



        data = api_request("post", "/WriteResponseFile", api_base, auth, payload=payload_to_submit)
        if data:
            st.success(data.get("message", "Response file created"))
            st.json(data)



# -----------------------------
def render_job_result(payload: Dict[str, Any]):
    if not payload:
        return
    cmd_lines = payload.get("command")
    rows = []
    for k, v in payload.items():
        if k == "command":
            continue
        rows.append({"Field": k, "Value": v})
    if rows:
        st.markdown("#### Run result")
        st_df_safe(pd.DataFrame(rows), hide_index=True, width='stretch')
    if cmd_lines:
        st.markdown("##### ZDM CLI command")
        st.code("\n".join(cmd_lines) if isinstance(cmd_lines, list) else str(cmd_lines), language="bash")


# Create Job page (build & optionally run)
# -----------------------------
if section == "createjob":
    st.subheader("Create Job")
    st.caption("Define a job (and optionally run it). Job name is fixed per project + run type; saved jobs list is on the Run Job page.")

    projects_resp = get_projects_list(api_base, auth)
    connections_resp = api_request("get", "/dbconnections", api_base, auth, quiet=True) or {}
    project_names = list(projects_resp.keys()) if isinstance(projects_resp, dict) else []
    # saved jobs (for auto-load matching project+run_type)
    saved_jobs_resp = api_request("get", "/jobsaved", api_base, auth, quiet=True) or {}
    # wallets for -sourcesyswallet dropdown
    cred_wallets_resp = api_request("get", "/credentialWallets", api_base, auth, quiet=True) or {}
    wallet_map_runjob: Dict[str, str] = {}
    if isinstance(cred_wallets_resp, dict):
        wallet_map_runjob = {
            w.get("name"): w.get("path")
            for w in cred_wallets_resp.get("wallets", [])
            if w.get("name") and w.get("path")
        }
    wallet_options_runjob = ["-- Select wallet --"] + list(wallet_map_runjob.keys())

    sel_l, sel_r = st.columns([1, 1], vertical_alignment="top")

    with sel_l:
        project = st.selectbox(
            "Project",
            ["-- Select project --"] + project_names,
            key="runjob_project",
        )
    with sel_r:
        run_type = st.selectbox(
            "Run type",
            ["EVAL", "MIGRATE"],
            index=0,
            key="runjob_run_type",
        )

    # Pending load from Run Job page (explicit load button)
    pending_load = st.session_state.pop("runjob_load_pending", "")

    # Auto-load job definition if exists for project+run_type
    auto_job_key = f"{project}:{run_type}".lower()
    if project != "-- Select project --" and isinstance(saved_jobs_resp, dict):
        for name, job in saved_jobs_resp.items():
            if not isinstance(job, dict):
                continue
            if (pending_load == name) or (str(job.get("project")) == project and (job.get("run_type") or "").upper() == run_type):
                # Populate fields once per selection
                st.session_state["runjob_rsp"] = job.get("rsp") or f"{project}.rsp"
                st.session_state["runjob_sourcedb"] = job.get("sourcedb") or ""
                st.session_state["runjob_sourcenode"] = job.get("sourcenode") or ""
                st.session_state["runjob_srcauth"] = job.get("srcauth") or ""
                st.session_state["runjob_srcarg1"] = job.get("srcarg1") or ""
                st.session_state["runjob_srcarg2"] = job.get("srcarg2") or ""
                st.session_state["runjob_srcarg3"] = job.get("srcarg3") or ""
                # sourcesyswallet: store path and select matching name if possible
                wallet_path = job.get("sourcesyswallet") or ""
                st.session_state["runjob_sourcesyswallet"] = wallet_path
                wallet_name_match = ""
                if wallet_path:
                    for wname, wpath in wallet_map_runjob.items():
                        if wpath == wallet_path:
                            wallet_name_match = wname
                            break
                st.session_state["runjob_sourcesyswallet_name"] = wallet_name_match or wallet_options_runjob[0]
                st.session_state["runjob_targetnode"] = job.get("targetnode") or ""
                st.session_state["runjob_tgtauth"] = job.get("tgtauth") or ""
                st.session_state["runjob_tgtarg1"] = job.get("tgtarg1") or ""
                st.session_state["runjob_tgtarg2"] = job.get("tgtarg2") or ""
                st.session_state["runjob_tgtarg3"] = job.get("tgtarg3") or ""
                st.session_state["runjob_advisor_mode"] = job.get("advisor_mode") or "NONE"
                st.session_state["runjob_flow_control"] = job.get("flow_control") or "NONE"
                st.session_state["runjob_flow_phase"] = job.get("flow_phase") or ""
                st.session_state["runjob_genfixup"] = job.get("genfixup") or ""
                st.session_state["runjob_ignore"] = job.get("ignore") or []
                st.session_state["runjob_schedule_now"] = True if (job.get("schedule") or "").upper() == "NOW" else False
                st.session_state["runjob_schedule_text"] = "" if st.session_state.get("runjob_schedule_now") else (job.get("schedule") or "")
                st.session_state["runjob_listphases"] = bool(job.get("listphases"))
                st.session_state["runjob_custom_args"] = "\n".join(job.get("custom_args") or [])
                break

    if project == "-- Select project --":
        st.info("Select a project to start.")
        st.stop()

    migration_type = ""
    if isinstance(projects_resp, dict):
        migration_type = str(projects_resp.get(project, {}).get("migration_type", "") or "").upper()
    if not migration_type:
        migration_type = "LOGICAL_OFFLINE"

    def _blank(v: Any) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    proj_obj = projects_resp.get(project, {}) if isinstance(projects_resp, dict) else {}
    target_conn_name = proj_obj.get("target_connection") or proj_obj.get("target") or ""
    target_db_type = ""
    if isinstance(connections_resp, dict) and target_conn_name:
        target_db_type = (connections_resp.get(target_conn_name, {}) or {}).get("db_type", "") or ""

    def _show_target_ssh(db_type: str) -> bool:
        return (db_type or "").upper() not in ("ADBD", "ADBS", "ADBCC")
    existing_payload = None
    for k in [
        "existing_payload",
        "existing_response_payload",
        "rsp_payload",
        "response_payload",
        "payload",
        "responsefile_payload",
        "response_file_payload",
    ]:
        v = proj_obj.get(k) if isinstance(proj_obj, dict) else None
        if isinstance(v, dict) and v:
            existing_payload = v
            break

    existing_rsp_name = ""
    for k in ["rsp", "response_file", "response_file_name", "rsp_name", "rspFile"]:
        v = proj_obj.get(k) if isinstance(proj_obj, dict) else None
        if isinstance(v, str) and v.strip():
            existing_rsp_name = v.strip()
            break

    default_rsp_name = existing_rsp_name or f"{project}.rsp"
    if _blank(st.session_state.get("runjob_rsp")):
        st.session_state["runjob_rsp"] = default_rsp_name

    auto_base = f"{project}_{run_type.lower()}"
    job_key = "runjob_job_name"
    st.session_state[job_key] = auto_base

    seeded_key = "runjob_seeded_project"
    if st.session_state.get(seeded_key) != project and isinstance(existing_payload, dict):
        RF_TO_STATE = {
            "sourcedb": "runjob_sourcedb",
            "sourcenode": "runjob_sourcenode",
            "srcauth": "runjob_srcauth",
            "srcarg1": "runjob_srcarg1",
            "srcarg2": "runjob_srcarg2",
            "srcarg3": "runjob_srcarg3",
            "targetnode": "runjob_targetnode",
            "tgtauth": "runjob_tgtauth",
            "tgtarg1": "runjob_tgtarg1",
            "tgtarg2": "runjob_tgtarg2",
            "tgtarg3": "runjob_tgtarg3",
        }

        ALT_KEYS = {
            "SOURCEDATABASE_CONNECTIONDETAILS_HOST": "runjob_sourcenode",
            "SOURCEDATABASE_ADMINUSERNAME": "runjob_srcauth",
            "TARGETDATABASE_ADMINUSERNAME": "runjob_tgtauth",
        }

        def _apply_map(src: Dict[str, Any], mapping: Dict[str, str]) -> None:
            for rf_key, state_key in mapping.items():
                if rf_key not in src:
                    continue
                val = src.get(rf_key)
                if _blank(val):
                    continue
                if _blank(st.session_state.get(state_key)):
                    st.session_state[state_key] = str(val)

        _apply_map(existing_payload, RF_TO_STATE)
        _apply_map(existing_payload, ALT_KEYS)

        st.session_state[seeded_key] = project

    # Always keep RSP/job name in sync, no user edits
    st.session_state["runjob_rsp"] = default_rsp_name
    st.session_state[job_key] = auto_base

    col_top_a, col_top_b = st.columns(2)
    with col_top_a:
        st.text_input(
            "Response file name",
            key="runjob_rsp",
            help="Auto-derived from project",
            disabled=True,
        )
    with col_top_b:
        st.text_input(
            "Job name",
            key=job_key,
            help="Fixed: <project>_<eval|migrate>",
            disabled=True,
        )

    # Layout single column for create/run
    left_col = st.container()

    with left_col:
        st.markdown(f"Migration type (derived from project/response): `{migration_type}`")

        if migration_type == "LOGICAL_OFFLINE":
            with st.expander("ZDM CLI args (Logical Offline)", expanded=True):
                col_opt_a, col_opt_b = st.columns(2)
                with col_opt_a:
                    st.text_input("-sourcenode", key="runjob_sourcenode")
                    st.text_input("-srcauth", key="runjob_srcauth")
                    st.text_input("-srcarg1", key="runjob_srcarg1", help="e.g. user:oracle")
                    st.text_input("-srcarg2", key="runjob_srcarg2", help="e.g. identity_file:/home/zdmuser/.ssh/id_rsa")
                    wallet_selected = st.selectbox(
                        "-sourcesyswallet",
                        wallet_options_runjob,
                        key="runjob_sourcesyswallet_name",
                    )
                    st.session_state["runjob_sourcesyswallet"] = wallet_map_runjob.get(wallet_selected, "")
                with col_opt_b:
                    show_target_fields = _show_target_ssh(target_db_type)
                    if show_target_fields:
                        st.text_input("-targetnode", key="runjob_targetnode")
                        st.text_input("-tgtauth", key="runjob_tgtauth")
                        st.text_input("-tgtarg1", key="runjob_tgtarg1")
                        st.text_input("-tgtarg2", key="runjob_tgtarg2")
                        st.text_input("-tgtarg3", key="runjob_tgtarg3")

                st.divider()
                advisor_mode = st.selectbox("Advisor mode", ["NONE", "ADVISOR", "IGNORE_ADVISOR", "SKIP_ADVISOR"], key="runjob_advisor_mode")
                flow_control = st.selectbox("Flow control", ["NONE", "PAUSE_AFTER", "STOP_AFTER"], key="runjob_flow_control")
                flow_phase = st.text_input("Phase (for pause/stop)", key="runjob_flow_phase", help="Required when flow control is pause/stop")
                genfixup = st.selectbox("Genfixup", ["", "YES", "NO"], key="runjob_genfixup")
                ignore_opts = ["ALL","WARNING","PATCH_CHECK","NLS_CHECK","NLS_NCHAR_CHECK","ENDIAN_CHECK","VAULT_CHECK","DB_NK_CACHE_SIZE_CHECK"]
                ignore_sel = st.multiselect("Ignore checks", ignore_opts, key="runjob_ignore")
                schedule_now = st.checkbox("Schedule NOW", value=st.session_state.get("runjob_schedule_now", False), key="runjob_schedule_now")
                schedule_val = ""
                if schedule_now:
                    schedule_val = "NOW"
                else:
                    schedule_val = st.text_input("Schedule (ISO-8601)", key="runjob_schedule_text", help="YYYY-MM-DDTHH:MM:SS±HH")
                listphases = st.checkbox("List phases (-listphases)", value=False, key="runjob_listphases")
                custom_args_text = st.text_area("Custom args (one per line, full token e.g. '-myflag value')", key="runjob_custom_args")

        else:
            st.info(f"Migration type {migration_type} not yet wired; UI placeholder only.")
            advisor_mode = st.session_state.get("runjob_advisor_mode", "NONE")
            flow_control = st.session_state.get("runjob_flow_control", "NONE")
            flow_phase = st.session_state.get("runjob_flow_phase", "")
            genfixup = st.session_state.get("runjob_genfixup", "")
            ignore_sel = st.session_state.get("runjob_ignore", [])
            schedule_now = False
            schedule_val = st.session_state.get("runjob_schedule_text", "")
            listphases = st.session_state.get("runjob_listphases", False)
            custom_args_text = st.session_state.get("runjob_custom_args", "")

        action_col1, action_col2 = st.columns([0.4, 0.6])
        with action_col1:
            save_and_run = st.button("Save & Run", type="primary")
        with action_col2:
            save_only = st.button("Save only", type="secondary", width='stretch')
        run_clicked = save_and_run

    if save_only or save_and_run:
        payload_save = {
            "name": st.session_state.get(job_key),
            "project": project,
            "rsp": (st.session_state.get("runjob_rsp") or "").strip() or None,
            "run_type": st.session_state.get("runjob_run_type"),
            "sourcedb": st.session_state.get("runjob_sourcedb") or None,
            "sourcenode": st.session_state.get("runjob_sourcenode") or None,
            "srcauth": st.session_state.get("runjob_srcauth") or None,
            "srcarg1": st.session_state.get("runjob_srcarg1") or None,
            "srcarg2": st.session_state.get("runjob_srcarg2") or None,
            "srcarg3": st.session_state.get("runjob_srcarg3") or None,
            "sourcesyswallet": st.session_state.get("runjob_sourcesyswallet") or None,
            "targetnode": st.session_state.get("runjob_targetnode") or None,
            "tgtauth": st.session_state.get("runjob_tgtauth") or None,
            "tgtarg1": st.session_state.get("runjob_tgtarg1") or None,
            "tgtarg2": st.session_state.get("runjob_tgtarg2") or None,
            "tgtarg3": st.session_state.get("runjob_tgtarg3") or None,
            "advisor_mode": advisor_mode,
            "flow_control": flow_control,
            "flow_phase": flow_phase,
            "genfixup": genfixup or None,
            "ignore": ignore_sel or None,
            "schedule": schedule_val or None,
            "listphases": listphases,
            "custom_args": [ln.strip() for ln in (custom_args_text or "").splitlines() if ln.strip()],
        }
        resp_save = api_request("post", "/jobsaved", api_base, auth, payload=payload_save)
        if resp_save:
            st.success(f"Saved job '{payload_save['name']}'.")
            if save_only and not save_and_run:
                st.rerun()
            else:
                run_clicked = True

    if run_clicked:
        rsp_name = (st.session_state.get("runjob_rsp") or "").strip()
        if not rsp_name:
            st.error("Response file name is required.")
        else:
            payload = {
                "project": project,
                "run_type": run_type,
                "rsp": rsp_name,
                "sourcenode": (st.session_state.get("runjob_sourcenode") or "").strip() or None,
                "srcauth": (st.session_state.get("runjob_srcauth") or "").strip() or None,
                "srcarg1": (st.session_state.get("runjob_srcarg1") or "").strip() or None,
                "srcarg2": (st.session_state.get("runjob_srcarg2") or "").strip() or None,
                "srcarg3": (st.session_state.get("runjob_srcarg3") or "").strip() or None,
                "sourcesyswallet": (st.session_state.get("runjob_sourcesyswallet") or "").strip() or None,
                "targetnode": (st.session_state.get("runjob_targetnode") or "").strip() or None,
                "tgtauth": (st.session_state.get("runjob_tgtauth") or "").strip() or None,
                "tgtarg1": (st.session_state.get("runjob_tgtarg1") or "").strip() or None,
                "tgtarg2": (st.session_state.get("runjob_tgtarg2") or "").strip() or None,
                "tgtarg3": (st.session_state.get("runjob_tgtarg3") or "").strip() or None,
                "advisor_mode": advisor_mode,
                "flow_control": flow_control,
                "flow_phase": flow_phase or None,
                "genfixup": genfixup or None,
                "ignore": ignore_sel or None,
                "schedule": schedule_val or None,
                "listphases": listphases,
                "custom_args": [ln.strip() for ln in (custom_args_text or "").splitlines() if ln.strip()],
            }

            data = api_request("post", "/runjob", api_base, auth, payload=payload)
            if data:
                st.success("Job submitted.")
                st.session_state["last_job_status"] = data

    # -----------------------------
    # Run Job page (saved definitions only)
    # -----------------------------
elif section == "runjob":
    st.subheader("Run Job")
    st.caption("Pick a saved job definition, view it, preview the command, and run it.")

    saved_jobs_resp = api_request("get", "/jobsaved", api_base, auth, quiet=True) or {}
    saved_job_names = ["-- Select saved job --"] + list(saved_jobs_resp.keys())

    saved_sel = st.selectbox("Saved job definitions", saved_job_names, key="runjob_saved_select")
    c2, c3, c4 = st.columns([0.34, 0.33, 0.33])
    with c2:
        if st.button("View", key="runjob_view_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                st.session_state["runjob_view_job"] = saved_sel
                st.rerun()
    with c3:
        if st.button("Run", key="runjob_run_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                job = saved_jobs_resp.get(saved_sel, {})
                if job:
                    payload = {
                        "project": job.get("project"),
                        "run_type": job.get("run_type") or "EVAL",
                        "rsp": job.get("rsp"),
                        "sourcenode": job.get("sourcenode"),
                        "srcauth": job.get("srcauth"),
                        "srcarg1": job.get("srcarg1"),
                        "srcarg2": job.get("srcarg2"),
                        "srcarg3": job.get("srcarg3"),
                        "sourcesyswallet": job.get("sourcesyswallet"),
                        "targetnode": job.get("targetnode"),
                        "tgtauth": job.get("tgtauth"),
                        "tgtarg1": job.get("tgtarg1"),
                        "tgtarg2": job.get("tgtarg2"),
                        "tgtarg3": job.get("tgtarg3"),
                        "advisor_mode": job.get("advisor_mode"),
                        "flow_control": job.get("flow_control"),
                        "flow_phase": job.get("flow_phase"),
                        "genfixup": job.get("genfixup"),
                        "ignore": job.get("ignore"),
                        "schedule": job.get("schedule"),
                        "listphases": job.get("listphases"),
                        "custom_args": job.get("custom_args"),
                    }
                    data = api_request("post", "/runjob", api_base, auth, payload=payload)
                    if data:
                        st.success(f"Ran saved job '{saved_sel}'")
                        st.session_state["last_job_status"] = data
    with c4:
        if st.button("Delete", key="runjob_delete_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                resp = api_request("delete", f"/jobsaved/{saved_sel}", api_base, auth)
                if resp:
                    st.success(f"Deleted saved job '{saved_sel}'")
                    st.rerun()

    view_job_name = st.session_state.pop("runjob_view_job", "")
    if view_job_name and view_job_name in saved_jobs_resp:
        vjob = saved_jobs_resp.get(view_job_name, {})
        df_view = pd.DataFrame(
            [
                {"Field": k, "Value": "" if v is None else v}
                for k, v in vjob.items()
            ]
        )
        st_df_safe(df_view, hide_index=True, width='stretch')
        # Get live command preview via dry_run
        payload_preview = {
            "project": vjob.get("project"),
            "run_type": vjob.get("run_type") or "EVAL",
            "rsp": vjob.get("rsp"),
            "sourcenode": vjob.get("sourcenode"),
            "srcauth": vjob.get("srcauth"),
            "srcarg1": vjob.get("srcarg1"),
            "srcarg2": vjob.get("srcarg2"),
            "srcarg3": vjob.get("srcarg3"),
            "sourcesyswallet": vjob.get("sourcesyswallet"),
            "targetnode": vjob.get("targetnode"),
            "tgtauth": vjob.get("tgtauth"),
            "tgtarg1": vjob.get("tgtarg1"),
            "tgtarg2": vjob.get("tgtarg2"),
            "tgtarg3": vjob.get("tgtarg3"),
            "advisor_mode": vjob.get("advisor_mode"),
            "flow_control": vjob.get("flow_control"),
            "flow_phase": vjob.get("flow_phase"),
            "genfixup": vjob.get("genfixup"),
            "ignore": vjob.get("ignore"),
            "schedule": vjob.get("schedule"),
            "listphases": vjob.get("listphases"),
            "custom_args": vjob.get("custom_args"),
            "dry_run": True,
        }
        cmd_resp = api_request("post", "/runjob", api_base, auth, payload=payload_preview, quiet=False)
        if cmd_resp and isinstance(cmd_resp, dict) and cmd_resp.get("status") in ("planned", "success"):
            cmd_lines = cmd_resp.get("command")
            if cmd_lines:
                st.caption("ZDM CLI command (preview):")
                st.code("\n".join(cmd_lines) if isinstance(cmd_lines, list) else str(cmd_lines), language="bash")
            else:
                st.info("No command returned for this saved job.")
        elif cmd_resp:
            st.warning(f"Could not generate command: {cmd_resp}")

    # -----------------------------
    # Last submission (full width)
    # -----------------------------
    st.markdown("### Last submission")
    last_status = st.session_state.get("last_job_status")
    if last_status:
        render_job_result(last_status)
    else:
        st.info("No job submitted yet.")


elif section == "jobs":
    st.subheader("Monitor Jobs")
    st.caption("Look up job status and tail generated logs for ZDM runs.")

    def _parse_zdm_output(out: str) -> Dict[str, Any]:
        """Best-effort parsing of ZDM output text returned by /query."""
        if not out:
            return {}
        parsed: Dict[str, Any] = {}

        m = re.search(r"\bJob ID\s*:\s*(\S+)", out)
        if m:
            parsed["job_id"] = m.group(1)

        m = re.search(r"\bJob Type\s*:\s*\"?([A-Za-z0-9_\-]+)\"?", out)
        if m:
            parsed["job_type"] = m.group(1)

        m = re.search(r"\bCurrent status\s*:\s*([A-Za-z0-9_\-]+)", out)
        if m:
            parsed["zdm_status"] = m.group(1).upper()

        m = re.search(r"\bResult file path\s*:\s*\"?([^\"\n]+)\"?", out)
        if m:
            parsed["result_file"] = m.group(1).strip()

        phases: List[Tuple[str, str]] = []
        for line in out.splitlines():
            mm = re.match(r"^(ZDM_[A-Z0-9_]+)\s+\.+\s+([A-Z]+)\s*$", line.strip())
            if mm:
                phases.append((mm.group(1), mm.group(2)))
        if phases:
            parsed["phases"] = phases

        return parsed

    def _status_badge(status: str) -> Tuple[str, str]:
        """Return (label, kind) where kind in {'success','warning','error','info'} for Streamlit callouts."""
        s = (status or "").upper()
        if s in ("SUCCEEDED", "SUCCESS", "DONE", "COMPLETED"):
            return s, "success"
        if s in ("FAILED", "ERROR"):
            return s, "error"
        if s in ("RUNNING", "EXECUTING", "IN_PROGRESS"):
            return s, "warning"
        if s in ("PENDING", "PLANNED", "QUEUED"):
            return s, "info"
        return (s or "-"), "info"

    # -----------------------------
    # Query + Results/Logs (stacked)
    # -----------------------------
    with st.container(border=True):
        st.markdown("#### Query job")
        st.caption("Enter a Job ID, or pick one you ran recently.")

        def _apply_saved_jobid():
            val = (st.session_state.get("jobs_saved_pick") or "").strip()
            if val:
                st.session_state["jobs_manual_id"] = val
            st.session_state["jobs_saved_pick"] = ""

        job_ids_resp = api_request("get", "/jobids", api_base, auth, quiet=True) or {}
        job_ids_list: List[str] = job_ids_resp.get("job_ids", []) if isinstance(job_ids_resp, dict) else []

        row = st.columns([0.55, 0.25, 0.20], vertical_alignment="bottom")
        with row[0]:
            job_id = st.text_input("Job ID", key="jobs_manual_id", placeholder="e.g. 26")
        with row[1]:
            if job_ids_list:
                with st.popover("Pick saved"):
                    st.selectbox(
                        "Saved job IDs",
                        [""] + job_ids_list,
                        key="jobs_saved_pick",
                        on_change=_apply_saved_jobid,
                    )
            else:
                st.caption("No recent Job IDs")
        with row[2]:
            query_clicked = st.button("Query", type="primary", width='stretch')

        if query_clicked:
            job_id_clean = (job_id or "").strip()
            if not job_id_clean:
                st.error("Please enter a Job ID.")
            else:
                data = api_request("get", f"/query/{job_id_clean}", api_base, auth)
                if data:
                    st.session_state["last_job_id"] = job_id_clean
                    st.session_state["last_job_status"] = data
                    st.session_state["jobs_view"] = "Latest result"

    # -----------------------------
    # Latest result / Logs (tabs below query)
    # -----------------------------
    tab_status, tab_logs = st.tabs(["Latest result", "Logs"])

    last_job_id = (st.session_state.get("last_job_id") or "").strip()

    def _poll_latest(job_id: str) -> None:
        if not job_id:
            return
        data = api_request("get", f"/query/{job_id}", api_base, auth, quiet=True)
        if data:
            st.session_state["last_job_status"] = data

    with tab_status:
            st.markdown("#### Latest result")
            auto_refresh = st.toggle("Auto-refresh (every 5 seconds)", value=False, key="jobs_autorefresh_latest")

            def _render_latest():
                if not last_job_id:
                    st.info("No job queried yet.")
                    return

                if auto_refresh:
                    _poll_latest(last_job_id)

                last_status = st.session_state.get("last_job_status") or {}
                api_ok = last_status.get("status") if isinstance(last_status, dict) else None
                out_text = ""
                if isinstance(last_status, dict):
                    out_text = last_status.get("output") or last_status.get("message") or ""
                else:
                    out_text = str(last_status)

                parsed = _parse_zdm_output(out_text)
                zdm_status = parsed.get("zdm_status") or "-"
                badge_label, badge_kind = _status_badge(zdm_status)

                cols = st.columns([1.05, 0.85, 1.0])
                with cols[0]:
                    st.metric("Job ID", parsed.get("job_id") or last_job_id)
                with cols[1]:
                    st.metric("Job Type", parsed.get("job_type") or "-")
                with cols[2]:
                    st.metric("ZDM Status", badge_label)

                if badge_kind == "error":
                    st.error("ZDM job status: FAILED")
                elif badge_kind == "success":
                    st.success("ZDM job status: SUCCESS")
                elif badge_kind == "warning":
                    st.warning("ZDM job is still running / in progress")
                else:
                    st.info("ZDM job status is not available yet (or could not be parsed).")

                if api_ok:
                    st.caption(f"API response: {api_ok}")

                phases = parsed.get("phases") or []
                if phases:
                    with st.expander("Phases", expanded=False):
                        for name, stt in phases:
                            st.write(f"- **{name}**: {stt}")

                result_file = parsed.get("result_file")
                if result_file:
                    st.session_state["jobs_preferred_log_file"] = result_file
                    st.session_state["log_select"] = result_file
                    st.session_state["jobs_auto_open_log"] = True

                with st.expander("Raw output", expanded=False):
                    if out_text:
                        st.text_area("Raw output", value=out_text, height=260, disabled=True, label_visibility="collapsed")
                    else:
                        st.info("No output text returned.")

                with st.expander("Raw JSON", expanded=False):
                    st.json(last_status, expanded=False)

            if auto_refresh and last_job_id and hasattr(st, "fragment"):
                @st.fragment(run_every=5)
                def _latest_fragment():
                    _render_latest()
                _latest_fragment()
            else:
                if auto_refresh and not hasattr(st, "fragment"):
                    st.caption("Auto-refresh requires a newer Streamlit version (st.fragment).")
                _render_latest()

    with tab_logs:
            st.markdown("#### Job logs")

            def load_env_value(key: str) -> Optional[str]:
                val = os.getenv(key)
                if val:
                    return val
                env_path = Path(__file__).resolve().parent.parent / ".env"
                if not env_path.exists():
                    return None
                result: Dict[str, str] = {}
                with env_path.open("r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        result[k.strip()] = v.strip().strip('"').strip("'")
                return result.get(key)

            zdm_base = load_env_value("ZDM_BASE") or "/u01/app/zdmbase"
            scheduled_dir = Path(zdm_base) / "chkbase" / "scheduled"

            job_id_logs = st.session_state.get("last_job_id", "")
            log_files: List[str] = []
            if job_id_logs:
                pattern = f"job-{job_id_logs}*"
                if scheduled_dir.exists():
                    log_files = sorted([str(p) for p in scheduled_dir.glob(pattern) if p.is_file()])
                if not log_files:
                    st.warning(f"No log files found matching {pattern} under {scheduled_dir}.")
            else:
                st.info("Query a Job ID above to load its logs.")

            if not log_files:
                st.stop()

            preferred = (st.session_state.get("jobs_preferred_log_file") or "").strip()
            if preferred and preferred in log_files:
                if st.session_state.get("log_select") != preferred:
                    st.session_state["log_select"] = preferred

            top_l, top_r = st.columns([0.72, 0.28], vertical_alignment="bottom")
            with top_l:
                selected_log = st.selectbox("Select log file", log_files, key="log_select")
            with top_r:
                tail_on = st.toggle("Tail (5s, last 400 lines)", value=False, key="jobs_tail_on")

            def _render_log(content: str) -> None:
                def color_line(line: str) -> str:
                    upper = line.upper()
                    if "ORA-" in upper or "ERROR" in upper:
                        return f"<span style='color:#ff5555;font-weight:600'>{line}</span>"
                    if "WARN" in upper:
                        return f"<span style='color:#f0a500'>{line}</span>"
                    return line

                colored = "<br>".join(color_line(l) for l in content.splitlines())
                st.markdown(
                    "<div style='background:#0b0e14;color:#e8e8e8;padding:12px 14px;"
                    "border-radius:8px;overflow:auto;max-height:520px;font-family:SFMono-Regular,Consolas,Menlo,monospace;"
                    "font-size:12px;line-height:1.4;border:1px solid #1f2430;'>"
                    f"{colored}</div>",
                    unsafe_allow_html=True,
                )

            def _fetch_and_show_log() -> None:
                resp = api_request("post", "/ReadJobLog", api_base, auth, payload={"file_path": selected_log}, quiet=True)
                if not resp or resp.get("status") != "success":
                    st.error("Failed to read log.")
                    return
                content = resp.get("content", "") or ""
                if tail_on and content:
                    lines = content.splitlines()[-400:]
                    content = "\n".join(lines)
                _render_log(content)
                st.download_button("Download as text", data=content, file_name=Path(selected_log).name, key="dl-log")

            auto_open = bool(st.session_state.get("jobs_auto_open_log"))
            if auto_open:
                st.session_state["jobs_auto_open_log"] = False

            if tail_on and hasattr(st, "fragment"):
                @st.fragment(run_every=5)
                def _tail_fragment():
                    _fetch_and_show_log()
                _tail_fragment()
            else:
                if auto_open or st.button("View selected log", type="primary"):
                    _fetch_and_show_log()


elif section == "wallet":
    st.subheader("Wallets & Credentials")
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
                data = api_request("post", "/OraPKICreateWallet", api_base, auth, payload=payload)
                if data:
                    st.success(data.get("status", "success"))
                    st.json(data)

    with right:
        st.markdown("### Create credential")
        wallets_resp = api_request("get", "/credentialWallets", api_base, auth, quiet=True) or {}
        wallet_names = []
        if isinstance(wallets_resp, dict):
            wallet_names = [w.get("name") for w in wallets_resp.get("wallets", []) if w.get("name")]
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
                data = api_request("post", "/MkstoreCreateCredential", api_base, auth, payload=payload)
                if data:
                    st.success(data.get("status", "success"))
                    st.json(data)


    st.info(
        "Run: from repo root `streamlit run zdm-microservices/streamlit_app.py` · "
        "Ensure FastAPI is running and accessible from this machine."
    )

# -----------------------------
# DB Discovery (snapshot)
# -----------------------------
elif section == "discovery":
    st.subheader("DB Discovery")
    st.caption("Run a snapshot (schemas, tablespaces, directories, NLS, timezone) against a saved connection.")

    conns = api_request("get", "/dbconnections", api_base, auth, quiet=True) or {}
    conn_names = ["-- Select connection --"] + (list(conns.keys()) if isinstance(conns, dict) else [])

    col_sel, col_pw, col_mt = st.columns([0.5, 0.25, 0.25], vertical_alignment="bottom")
    with col_sel:
        selected_conn = st.selectbox("Connection", conn_names, key="disc_conn")
    with col_pw:
        conn_pw = st.text_input("Password", type="password", key="disc_pw", help="Password for the selected connection user")
    with col_mt:
        migration_type = st.selectbox(
            "Migration type (optional)",
            ["", "LOGICAL_OFFLINE", "PHYSICAL_ONLINE", "PHYSICAL_OFFLINE", "HYBRID_OFFLINE"],
            key="disc_mt",
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

        if mig == "LOGICAL_OFFLINE":
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
            latest = api_request("get", f"/dbconnection/discover/latest/{selected_conn}", api_base, auth, quiet=True)
            if latest and latest.get("status") == "success":
                st.session_state[cache_key] = latest.get("snapshot")
                st.session_state[cache_file_key] = latest.get("file")
                tsd = parse_ts_from_filename(latest.get("file"))
                if tsd:
                    st.session_state[cache_tsdisp_key] = tsd
        snapshot = st.session_state.get(cache_key)
        snapshot_source = "cached" if snapshot is not None else ""

    if run_disc:
        if selected_conn == "-- Select connection --":
            st.error("Select a connection.")
        else:
            payload = {"name": selected_conn, "password": conn_pw or ""}
            if migration_type:
                payload["migration_type"] = migration_type
            data = api_request("post", "/dbconnection/discover", api_base, auth, payload=payload)
            if data:
                snapshot = data.get("snapshot") if isinstance(data, dict) else data
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

        tabs = st.tabs(["Readiness", "Summary", "Schemas", "Tablespaces", "Directories", "NLS & TZ", "Raw JSON"])

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
                {"Field": "User", "Value": conn_meta.get("username")},
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

        with tabs[6]:
            st.json(snapshot, expanded=False)
