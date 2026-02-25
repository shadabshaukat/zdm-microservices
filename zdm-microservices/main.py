"""
############################################################
# Code Contributors
# Shadab Mohammad, Master Principal Cloud Architect
# Suya Huang, Principal Cloud Architect
# Organization: Oracle
############################################################
"""

from fastapi import FastAPI, HTTPException, Depends, Body, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
import json
import tempfile
import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any, Union
from pathlib import Path
import subprocess
import os
import re
import hashlib
from passlib.context import CryptContext
try:
    from .backend_auth import load_users_hashed, AuthConfigError  # package-style
except ImportError:
    from backend_auth import load_users_hashed, AuthConfigError  # script-style

app = FastAPI()

@app.on_event("startup")
async def display_routes():
    routes = [route.path for route in app.routes]
    print("Available API routes:", routes)

security = HTTPBasic()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

try:
    USER_CREDENTIALS = load_users_hashed()
except AuthConfigError as exc:
    raise RuntimeError(str(exc)) from exc

@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/version")
def version():
    return {"version": "1.0.0", "service": "zdm-microservices"}

def verify_credentials(credentials: HTTPBasicCredentials = Depends(security)):
    stored = USER_CREDENTIALS.get(credentials.username)
    if not stored or not pwd_context.verify(credentials.password, stored):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return credentials.username

def ensure_zdm_home():
    if not os.getenv("ZDM_HOME"):
        raise HTTPException(status_code=500, detail="ZDM_HOME environment variable is not set")

ensure_zdm_home()

_zeus_data = os.getenv("ZEUS_DATA")
if not _zeus_data:
    raise RuntimeError("ZEUS_DATA is required (MIGRATION_BASE is set to ZEUS_DATA/migration; no separate MIGRATION_BASE env var).")
MIGRATION_BASE = os.path.join(_zeus_data, "migration").rstrip("/")
os.makedirs(MIGRATION_BASE, exist_ok=True)


SQL_CATALOG_FILE = os.path.join(os.path.dirname(__file__), "sql_catalog.json")  # repo-managed catalog
PROJECTS_FILE = os.path.join(os.path.dirname(__file__), "projects.json")  # legacy location

def _connections_file_path() -> str:
    target_dir = os.path.join(MIGRATION_BASE, "connections")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "db_connections.json")


def _projects_file_path() -> str:
    target_dir = os.path.join(MIGRATION_BASE, "projects")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "projects.json")


def _jobs_file_path() -> str:
    target_dir = os.path.join(MIGRATION_BASE, "jobs")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "jobs.json")


def _sql_catalog_paths() -> List[str]:
    return [SQL_CATALOG_FILE]

# -----------------------------
# Models used across endpoints
# -----------------------------
class LogFileParams(BaseModel):
    file_path: str

# -----------------------------
# Write-only Response File API
# -----------------------------
_SAFE_PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")

class WriteResponseFileRequest(BaseModel):
    project: str
    lines: List[str]


class SavedJobParams(BaseModel):
    name: str
    project: str
    rsp: Optional[str] = None
    run_type: str = "EVAL"
    sourcedb: Optional[str] = None
    sourcenode: Optional[str] = None
    srcauth: Optional[str] = None
    srcarg1: Optional[str] = None
    srcarg2: Optional[str] = None
    srcarg3: Optional[str] = None
    sourcesyswallet: Optional[str] = None
    targetnode: Optional[str] = None
    tgtauth: Optional[str] = None
    tgtarg1: Optional[str] = None
    tgtarg2: Optional[str] = None
    tgtarg3: Optional[str] = None
    advisor_mode: Optional[str] = None  # NONE|ADVISOR|IGNORE_ADVISOR|SKIP_ADVISOR
    flow_control: Optional[str] = None  # NONE|PAUSE_AFTER|STOP_AFTER
    flow_phase: Optional[str] = None
    genfixup: Optional[str] = None      # YES|NO
    ignore: Optional[List[str]] = None
    schedule: Optional[str] = None
    listphases: Optional[bool] = False
    custom_args: Optional[List[str]] = None

def _validate_project_name(project: str) -> str:
    project = (project or "").strip()
    if not project:
        raise HTTPException(status_code=400, detail="project is required")
    # disallow path separators / traversal explicitly
    if any(x in project for x in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="project contains illegal path characters")
    if not _SAFE_PROJECT_RE.match(project):
        raise HTTPException(
            status_code=400,
            detail="project must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        )
    return project

def _normalize_rsp_line_value(value: Any) -> str:
    # Keep this intentionally minimal and ZDM-agnostic.
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        if value.lower() == "true":
            return "TRUE"
        if value.lower() == "false":
            return "FALSE"
        return value
    return str(value)

def _write_responsefile_lines(project: str, lines_in: List[str]) -> Dict[str, Any]:
    project = _validate_project_name(project)

    if not isinstance(lines_in, list) or not all(isinstance(x, str) for x in lines_in):
        raise HTTPException(status_code=400, detail="lines must be a list of strings")

    # Filter out purely-empty lines; keep ordering intact.
    cleaned: List[str] = []
    for ln in lines_in:
        s = ln.rstrip("\n\r")
        if s.strip() == "":
            continue
        cleaned.append(s)

    if not cleaned:
        raise HTTPException(status_code=400, detail="lines must contain at least one non-empty line")

    response_dir = get_responses_dir(project, required=True)
    script_path = os.path.join(response_dir, f"{project}.rsp")
    content = "\n".join(cleaned) + "\n"

    with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)

    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()
    # Best-effort: record rsp name on the project for UI auto-fill
    try:
        projects = load_projects()
        if project in projects:
            projects[project]["rsp"] = f"{project}.rsp"
            save_projects(projects)
    except Exception:
        pass

    return {
        "status": "success",
        "message": f"Response file {project}.rsp written successfully",
        "path": script_path,
        "line_count": len(cleaned),
        "sha256": sha256,
    }

_sql_cache: Optional[Dict[str, str]] = None


def _load_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_json_file(path: str, payload: Dict[str, Any]):
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, indent=2)


def load_connections() -> Dict[str, Dict[str, Any]]:
    payload = _load_json_file(_connections_file_path())
    if isinstance(payload, dict):
        return payload
    return {}


def save_connections(connections: Dict[str, Dict[str, Any]]):
    _save_json_file(_connections_file_path(), connections)


def load_projects() -> Dict[str, Dict[str, Any]]:
    new_path = _projects_file_path()
    payload = _load_json_file(new_path)
    if isinstance(payload, dict):
        return payload
    return {}


def save_projects(projects: Dict[str, Dict[str, Any]]):
    _save_json_file(_projects_file_path(), projects)


def _load_project_or_404(name: str) -> Dict[str, Any]:
    """Return a project dict or raise 404 if missing."""
    project = _validate_project_name(name)
    projects = load_projects()
    proj = projects.get(project)
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    if "name" not in proj:
        proj = {**proj, "name": project}
    return proj


def load_saved_jobs() -> Dict[str, Dict[str, Any]]:
    payload = _load_json_file(_jobs_file_path())
    if isinstance(payload, dict):
        return payload
    return {}


def save_saved_jobs(jobs: Dict[str, Dict[str, Any]]):
    _save_json_file(_jobs_file_path(), jobs)


def _job_ids_file_path() -> str:
    return os.path.join(MIGRATION_BASE, "jobs", "job_ids.json")


def load_job_ids() -> List[str]:
    path = _job_ids_file_path()
    if not os.path.exists(path):
        return []
    try:
        data = _load_json_file(path)
        if isinstance(data, list):
            return [str(x) for x in data]
    except Exception:
        pass
    return []


def save_job_id(job_id: str):
    if not job_id:
        return
    ids = load_job_ids()
    if job_id not in ids:
        ids.append(job_id)
        os.makedirs(os.path.dirname(_job_ids_file_path()), exist_ok=True)
        _save_json_file(_job_ids_file_path(), ids)


def _record_project_job_id(project: str, run_type: str, job_id: str):
    """Persist job_id under projects.json: projects[project]['jobs'][run_type]=[ids]."""
    if not project or not job_id:
        return
    rt = (run_type or "").lower() or "eval"
    projects = load_projects()
    proj = projects.get(project, {"name": project})
    jobs = proj.get("jobs", {})
    lst = jobs.get(rt, [])
    if job_id not in lst:
        lst.append(job_id)
        jobs[rt] = lst
        proj["jobs"] = jobs
        projects[project] = proj
        save_projects(projects)


def find_project_by_job(job_id: str) -> Optional[str]:
    """Return project name that contains this job_id in its jobs map."""
    if not job_id:
        return None
    jid = str(job_id)
    projects = load_projects()
    for pname, proj in projects.items():
        jobs = proj.get("jobs", {})
        if not isinstance(jobs, dict):
            continue
        for ids in jobs.values():
            if isinstance(ids, list) and any(str(x) == jid for x in ids):
                return pname
    return None


@app.get("/jobids")
def list_job_ids(username: str = Depends(verify_credentials)):
    return {"job_ids": load_job_ids()}


def get_sql_catalog() -> Dict[str, Any]:
    global _sql_cache
    if _sql_cache is None:
        for path in _sql_catalog_paths():
            catalog = _load_json_file(path)
            if catalog:
                _sql_cache = catalog
                break
        if _sql_cache is None:
            raise HTTPException(
                status_code=500,
                detail=f"SQL catalog not found or empty. Checked: {', '.join(_sql_catalog_paths())}",
            )
    return _sql_cache


def get_sql(key: str) -> str:
    catalog = get_sql_catalog()
    # direct hit
    sql = catalog.get(key)
    if isinstance(sql, str):
        return sql
    # base bucket
    base = catalog.get("base")
    if isinstance(base, dict) and key in base:
        return base[key]
    # search buckets
    for value in catalog.values():
        if isinstance(value, dict) and key in value:
            return value[key]
    raise HTTPException(status_code=500, detail=f"SQL '{key}' not found in catalog")


def get_sql_bucket(section: str) -> Dict[str, str]:
    catalog = get_sql_catalog()
    bucket = catalog.get(section) if isinstance(catalog, dict) else None
    return bucket if isinstance(bucket, dict) else {}


def derive_container_label(snapshot: Dict[str, Any]) -> str:
    ctx = snapshot.get("container_context") or {}
    curr = snapshot.get("current_container_details") or {}
    cont = snapshot.get("container_info") or {}
    con_name = ctx.get("CON_NAME") or curr.get("NAME") or cont.get("CONTAINER_NAME") or ""
    con_name_up = str(con_name).upper()
    if con_name_up == "CDB$ROOT":
        return "CDB$ROOT"
    if con_name_up == "PDB$SEED":
        return "PDB$SEED"
    if con_name_up:
        return f"PDB: {con_name_up}"
    return "Unknown container"


def derive_platform_type(snapshot: Dict[str, Any]) -> str:
    cloud_identity = snapshot.get("cloud_identity")
    exa_rows = snapshot.get("exadata_cells") or []

    def is_error(val: Any) -> bool:
        return isinstance(val, dict) and "error" in val

    cloud_val = None
    if isinstance(cloud_identity, list) and cloud_identity:
        # pick first non-null value from list of dicts or scalars
        for item in cloud_identity:
            if is_error(item):
                continue
            if isinstance(item, dict):
                for v in item.values():
                    if v:
                        cloud_val = v
                        break
            elif item:
                cloud_val = item
            if cloud_val:
                break
    elif isinstance(cloud_identity, dict):
        if not is_error(cloud_identity):
            for v in cloud_identity.values():
                if v:
                    cloud_val = v
                    break
    elif isinstance(cloud_identity, str):
        cloud_val = cloud_identity

    ci_lower = str(cloud_val or "").lower()
    infra = ""
    try:
        import json as _json
        parsed = _json.loads(cloud_val) if cloud_val else None
        if isinstance(parsed, dict):
            infra = str(parsed.get("INFRASTRUCTURE", "")).lower()
    except Exception:
        infra = ""

    if cloud_val and "autonomousdatabase" in ci_lower:
        if "shared" in infra:
            return "ADB-S"
        if "dedicated" in infra:
            return "ADB-D"
        return "ADB"

    has_exa = isinstance(exa_rows, list) and len(exa_rows) > 0

    if cloud_val and has_exa:
        return "Exadata (OCI)"
    if cloud_val and not has_exa:
        return "OCI DB System"
    if not cloud_val and has_exa:
        return "On-prem Exadata"
    return "On-prem"


def require_oracledb():
    try:
        import oracledb  # type: ignore
    except ImportError:
        raise HTTPException(
            status_code=500,
            detail="python-oracledb is required for DB connection features. Install it in the environment."
        )
    return oracledb


def build_dsn(
    host: str,
    port: int,
    service_name: str,
    protocol: str = "TCP",
    ssl_server_dn_match: Optional[bool] = None,
) -> str:
    security = ""
    if ssl_server_dn_match is not None:
        val = "yes" if ssl_server_dn_match else "no"
        security = f"(SECURITY=(ssl_server_dn_match={val}))"
    return (
        f"(DESCRIPTION="
        f"(ADDRESS=(PROTOCOL={protocol})(HOST={host})(PORT={port}))"
        f"(CONNECT_DATA=(SERVICE_NAME={service_name}))"
        f"{security}"
        f")"
    )


def fetch_one_dict(cursor, sql: str) -> Dict[str, Any]:
    cursor.execute(sql)
    row = cursor.fetchone()
    if row is None:
        return {}
    columns = [col[0] for col in cursor.description]
    return {columns[i]: row[i] for i in range(len(columns))}


def fetch_all_dicts(cursor, sql: str) -> List[Dict[str, Any]]:
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [col[0] for col in cursor.description]
    result = []
    for row in rows:
        result.append({columns[i]: row[i] for i in range(len(columns))})
    return result


def fetch_any(cursor, sql: str) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [col[0] for col in cursor.description]
    if len(rows) == 1:
        return {columns[i]: rows[0][i] for i in range(len(columns))}
    return [{columns[i]: row[i] for i in range(len(columns))} for row in rows]


def fetch_optional(cursor, sql_key: str, mode: str = "any") -> Any:
    try:
        sql = get_sql(sql_key)
        if mode == "one":
            return fetch_one_dict(cursor, sql)
        if mode == "all":
            return fetch_all_dicts(cursor, sql)
        return fetch_any(cursor, sql)
    except Exception as exc:
        # Non-fatal: record error for diagnostics
        return {"error": str(exc)}


def get_connection_dir(name: str) -> str:
    safe = _validate_project_name(name)
    path = os.path.join(MIGRATION_BASE, "connections", safe)
    os.makedirs(path, exist_ok=True)
    return path


def _load_connection_or_404(name: str) -> Dict[str, Any]:
    connections = load_connections()
    conn_info = connections.get(name)
    if not conn_info:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
    return conn_info


def _collect_db_snapshot(
    conn_info: Dict[str, Any],
    conn_name: str,
    password: Optional[str] = None,
    wallet_location: Optional[str] = None,
    protocol_override: Optional[str] = None,
    ssl_server_dn_match: Optional[bool] = None,
    migration_type: Optional[str] = None,
) -> Dict[str, Any]:
    mig = (migration_type or "logical_offline").strip().lower().replace(" ", "_")
    oracledb = require_oracledb()
    dsn = build_dsn(
        conn_info["host"],
        int(conn_info["port"]),
        conn_info["service_name"],
        protocol_override or conn_info.get("protocol", "TCP"),
        ssl_server_dn_match=ssl_server_dn_match,
    )

    connect_kwargs: Dict[str, Any] = {"user": conn_info["username"], "dsn": dsn}
    if password:
        connect_kwargs["password"] = password
    if wallet_location:
        connect_kwargs["config_dir"] = wallet_location
        connect_kwargs["wallet_location"] = wallet_location

    connection = oracledb.connect(**connect_kwargs)
    raw_queries: Dict[str, Any] = {}
    snapshot: Dict[str, Any] = {
        "connection": {
            k: conn_info[k]
            for k in ["host", "port", "service_name", "username", "protocol"]
            if k in conn_info
        },
        "connection_name": conn_name,
    }
    try:
        with connection.cursor() as cursor:
            snapshot["db_info"] = fetch_one_dict(cursor, get_sql("db_info")); raw_queries["db_info"] = snapshot["db_info"]
            snapshot["instance_info"] = fetch_one_dict(cursor, get_sql("instance_info")); raw_queries["instance_info"] = snapshot["instance_info"]
            snapshot["container_info"] = fetch_one_dict(cursor, get_sql("container_name")); raw_queries["container_name"] = snapshot["container_info"]
            snapshot["container_context"] = fetch_optional(cursor, "container_context", mode="one"); raw_queries["container_context"] = snapshot["container_context"]
            snapshot["current_container_details"] = fetch_optional(cursor, "current_container_details", mode="one"); raw_queries["current_container_details"] = snapshot["current_container_details"]
            snapshot["directories"] = fetch_all_dicts(cursor, get_sql("directory_list")); raw_queries["directory_list"] = snapshot["directories"]
            snapshot["schemas_all"] = fetch_all_dicts(cursor, get_sql("schemas_all")); raw_queries["schemas_all"] = snapshot["schemas_all"]
            snapshot["schemas"] = [row["USERNAME"] for row in fetch_all_dicts(cursor, get_sql("non_maintained_users"))]
            raw_queries["non_maintained_users"] = snapshot["schemas"]
            snapshot["tablespaces"] = [row["TABLESPACE_NAME"] for row in fetch_all_dicts(cursor, get_sql("non_temp_tablespaces"))]
            raw_queries["non_temp_tablespaces"] = snapshot["tablespaces"]
            snapshot["nls"] = fetch_all_dicts(cursor, get_sql("nls_info")); raw_queries["nls_info"] = snapshot["nls"]
            snapshot["timezone"] = fetch_one_dict(cursor, get_sql("timezone_version")); raw_queries["timezone_version"] = snapshot["timezone"]
            snapshot["cloud_identity"] = fetch_optional(cursor, "cloud_identity", mode="any"); raw_queries["cloud_identity"] = snapshot["cloud_identity"]
            snapshot["exadata_cells"] = fetch_optional(cursor, "exadata_cells", mode="all"); raw_queries["exadata_cells"] = snapshot["exadata_cells"]
            snapshot["version_banners"] = fetch_optional(cursor, "version_banners", mode="all"); raw_queries["version_banners"] = snapshot["version_banners"]
            snapshot["db_role_open_mode_base"] = fetch_optional(cursor, "db_role_open_mode_base", mode="one"); raw_queries["db_role_open_mode_base"] = snapshot["db_role_open_mode_base"]
            snapshot["rac_info"] = fetch_optional(cursor, "rac_info", mode="one"); raw_queries["rac_info"] = snapshot["rac_info"]

            extras: Dict[str, Any] = {}
            bucket_map = {
                "logical_offline": ["logical_offline_extra"],
                "physical_offline": ["physical_common"],
                "physical_online": ["physical_common", "physical_online_extra"],
                "hybrid": ["physical_common", "hybrid_offline_extra"],
            }
            for bucket_name in bucket_map.get(mig, []):
                bucket_sqls = get_sql_bucket(bucket_name)
                if not bucket_sqls:
                    continue
                extras[bucket_name] = {}
                for key, sql in bucket_sqls.items():
                    try:
                        extras[bucket_name][key] = fetch_any(cursor, sql)
                        raw_queries[f"{bucket_name}.{key}"] = extras[bucket_name][key]
                    except Exception as exc:
                        extras[bucket_name][key] = {"error": str(exc)}
            if extras:
                snapshot["extras"] = extras
            snapshot["migration_type"] = mig
    finally:
        connection.close()

    # derived fields
    snapshot["container_label"] = derive_container_label(snapshot)
    snapshot["platform_type"] = derive_platform_type(snapshot)
    snapshot["raw_queries"] = raw_queries

    # persist raw and processed snapshots separately
    try:
        disc_dir = get_discovery_dir()
        ts = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        base_fname = f"{conn_name}_{conn_info.get('host','conn')}_{conn_info.get('service_name','svc')}_{ts}"
        snap_path = os.path.join(disc_dir, f"{base_fname}_snapshot.json")
        raw_path = os.path.join(disc_dir, f"{base_fname}_raw.json")
        with open(snap_path, "w", encoding="utf-8") as handle:
            json.dump(snapshot, handle, indent=2, default=str)
        with open(raw_path, "w", encoding="utf-8") as handle:
            json.dump(raw_queries, handle, indent=2, default=str)
    except Exception:
        # non-fatal: continue even if writing snapshot fails
        pass
    return snapshot


def resolve_project_name(project: Optional[str], required: bool = False) -> str:
    if not project:
        if required:
            raise HTTPException(status_code=400, detail="project is required")
        raise HTTPException(status_code=400, detail="project is required")
    return project


def ensure_dir(project: Optional[str], subdir: str, required: bool = False) -> str:
    pname = resolve_project_name(project, required=True)
    target_dir = os.path.join(MIGRATION_BASE, pname, subdir)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_responses_dir(project: str, required: bool = True) -> str:
    if not project and required:
        raise HTTPException(status_code=400, detail="project is required for responses")
    target_dir = os.path.join(MIGRATION_BASE, "responses", project)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_scripts_dir(project: str, required: bool = True) -> str:
    if not project and required:
        raise HTTPException(status_code=400, detail="project is required for scripts")
    target_dir = os.path.join(MIGRATION_BASE, "scripts", project)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_tls_wallets_dir() -> str:
    """TLS wallets for TCPS connections (tnsnames/sqlnet/ewallet)."""
    tls_dir = os.path.join(MIGRATION_BASE, "wallets", "tls")
    os.makedirs(tls_dir, exist_ok=True)
    return tls_dir


def get_cred_wallets_dir() -> str:
    """Credential wallets created by orapki/mkstore."""
    cred_dir = os.path.join(MIGRATION_BASE, "wallets", "cred")
    os.makedirs(cred_dir, exist_ok=True)
    return cred_dir


def get_discovery_dir() -> str:
    path = os.path.join(MIGRATION_BASE, "discovery")
    os.makedirs(path, exist_ok=True)
    return path


def resolve_tls_wallet_path(wallet_name: Optional[str], wallet_path: Optional[str]) -> str:
    if wallet_path:
        return wallet_path
    if not wallet_name:
        raise HTTPException(status_code=400, detail="tls_wallet_name is required when wallet_path is not provided")
    base_dir = get_tls_wallets_dir()
    return os.path.join(base_dir, wallet_name)


def resolve_cred_wallet_path(wallet_name: Optional[str], wallet_path: Optional[str]) -> str:
    if wallet_path:
        return wallet_path
    if not wallet_name:
        raise HTTPException(status_code=400, detail="wallet_name is required when wallet_path is not provided")
    base_dir = get_cred_wallets_dir()
    return os.path.join(base_dir, wallet_name)


def resolve_wallet_path(wallet_name: Optional[str], wallet_path: Optional[str]) -> str:
    """Deprecated compatibility helper; now routes to credential wallet resolver."""
    return resolve_cred_wallet_path(wallet_name, wallet_path)


def write_temp_script(prefix: str, content: str, project: Optional[str] = None, required: bool = False) -> str:
    pname = resolve_project_name(project, required=True if required else True)
    target_dir = get_scripts_dir(pname, required=True)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".sh", dir=target_dir)
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.chmod(path, 0o755)
    return path


def resolve_response_dir(project: Optional[str], required: bool = False) -> str:
    pname = resolve_project_name(project, required=True if required else True)
    return get_responses_dir(pname, required=True)

@app.get("/query/{jobid}")
def query(jobid: str, project: Optional[str] = None, username: str = Depends(verify_credentials)):
    # Auto-detect project from projects.json if not provided
    if not project:
        project = find_project_by_job(jobid)
    project = resolve_project_name(project, required=True)
    query_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli query job -jobid {jobid}
    """
    script_path = write_temp_script("query_", query_script, project)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"Query Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)


class ResumeParams(BaseModel):
    project: Optional[str] = None
    pauseafter: Optional[str] = None
    skip: Optional[str] = None
    ignore: Optional[str] = None


@app.post("/resume/{jobid}")
def resume(jobid: str, params: ResumeParams = Body(...), username: str = Depends(verify_credentials)):
    resume_script_parts = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/zdmcli resume job -jobid {jobid}"
    ]
    if params and params.skip:
        resume_script_parts[-1] += f" -skip {params.skip}"
    if params and params.ignore:
        resume_script_parts[-1] += f" -ignore {params.ignore}"
    resume_script = "\n".join(resume_script_parts)
    script_path = write_temp_script("resume_", resume_script, params.project)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        # Since stderr=subprocess.PIPE is set, stderr will always be captured
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        # It's better to log the actual error message for debugging purposes
        error_message = f"Query Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

## API to Resume a Job and Pause Again at Another Stage
@app.post("/resume_pauseagain/{jobid}")
def resume_pauseagain(jobid: str, params: ResumeParams = Body(...), username: str = Depends(verify_credentials)):
    resume_pauseagain_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/zdmcli resume job -jobid {jobid}"
    ]

    if params.pauseafter:
        resume_pauseagain_script.append(f" -pauseafter {params.pauseafter}")
    if params.skip:
        resume_pauseagain_script.append(f" -skip {params.skip}")
    if params.ignore:
        resume_pauseagain_script.append(f" -ignore {params.ignore}")

    # Join the script lines into a single command
    resume_script_v2 = " \\\n".join(resume_pauseagain_script)

    script_path = write_temp_script("resume_pause_", resume_script_v2, params.project)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Resume Pause Again Job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)


class DBConnectionParams(BaseModel):
    name: str
    host: str
    port: int
    service_name: str
    username: str
    db_type: Optional[str] = None
    protocol: Optional[str] = "TCP"
    allow_tls_without_wallet: Optional[bool] = False
    tls_wallet_uploaded_dir: Optional[str] = None


class DBConnectionCheckParams(BaseModel):
    name: str
    password: Optional[str] = None
    use_uploaded_tls_wallet: Optional[bool] = False
    run_snapshot: bool = False

class DBConnectionDiscoverParams(BaseModel):
    name: str
    password: Optional[str] = None
    use_uploaded_tls_wallet: Optional[bool] = False
    migration_type: Optional[str] = "logical_offline"  # logical_offline, physical_offline, physical_online, hybrid
    role: Optional[str] = None  # optional tag for future compare views


class ProjectParams(BaseModel):
    name: str
    rsp: Optional[str] = None
    source_connection: Optional[str] = None
    target_connection: Optional[str] = None


class PrefillParams(BaseModel):
    project: Optional[str] = None
    source_connection: str
    target_connection: str


@app.post("/dbconnection")
def create_db_connection(params: DBConnectionParams, username: str = Depends(verify_credentials)):
    connections = load_connections()
    payload = params.dict()
    connections[params.name] = payload
    save_connections(connections)
    return {"status": "success", "message": f"Connection '{params.name}' saved", "connection": payload}


@app.get("/dbconnections")
def list_db_connections(username: str = Depends(verify_credentials)):
    return load_connections()


@app.delete("/dbconnection/{name}")
def delete_db_connection(name: str, username: str = Depends(verify_credentials)):
    connections = load_connections()
    if name not in connections:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
    connections.pop(name)
    save_connections(connections)
    return {"status": "success", "message": f"Connection '{name}' deleted"}


@app.get("/projects")
def list_projects(username: str = Depends(verify_credentials)):
    return load_projects()


@app.post("/project")
def create_project(params: ProjectParams, username: str = Depends(verify_credentials)):
    projects = load_projects()
    projects[params.name] = {
        "name": params.name,
        "rsp": params.rsp,
        "source_connection": params.source_connection,
        "target_connection": params.target_connection,
    }
    save_projects(projects)
    return {"status": "success", "message": f"Project '{params.name}' saved", "project": projects[params.name]}


@app.delete("/project/{name}")
def delete_project(name: str, username: str = Depends(verify_credentials)):
    projects = load_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")
    projects.pop(name)
    save_projects(projects)
    return {"status": "success", "message": f"Project '{name}' deleted"}


@app.get("/jobsaved")
def list_saved_jobs(username: str = Depends(verify_credentials)):
    return load_saved_jobs()


@app.post("/jobsaved")
def upsert_saved_job(params: SavedJobParams, username: str = Depends(verify_credentials)):
    jobs = load_saved_jobs()
    name = (params.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Job name is required")
    payload = params.dict()
    payload["run_type"] = (params.run_type or "EVAL").upper()
    jobs[name] = payload
    save_saved_jobs(jobs)
    return {"status": "success", "message": f"Job '{name}' saved", "job": payload}


@app.delete("/jobsaved/{name}")
def delete_saved_job(name: str, username: str = Depends(verify_credentials)):
    jobs = load_saved_jobs()
    if name not in jobs:
        raise HTTPException(status_code=404, detail=f"Saved job '{name}' not found")
    jobs.pop(name)
    save_saved_jobs(jobs)
    return {"status": "success", "message": f"Saved job '{name}' deleted"}


@app.post("/dbconnection/{name}/uploadTlsWallet")
def upload_tls_wallet(name: str, wallet: UploadFile = File(...), username: str = Depends(verify_credentials)):
    conn_dir = get_connection_dir(name)
    wallet_dir = os.path.join(conn_dir, "tls_wallet")
    os.makedirs(wallet_dir, exist_ok=True)
    target_path = os.path.join(wallet_dir, wallet.filename)
    with open(target_path, "wb") as handle:
        handle.write(wallet.file.read())

    connections = load_connections()
    if name in connections:
        connections[name]["tls_wallet_uploaded_dir"] = wallet_dir
        save_connections(connections)

    return {"status": "success", "message": "TLS wallet uploaded", "path": target_path, "wallet_dir": wallet_dir}


def _run_connection_check(params: Union[DBConnectionCheckParams, DBConnectionDiscoverParams], run_snapshot: bool, migration_type: Optional[str] = None):
    conn_info = _load_connection_or_404(params.name)
    test_password = params.password
    wallet_location: Optional[str] = None

    protocol = (conn_info.get("protocol") or "").upper()
    wallet_required = protocol == "TCPS" and not conn_info.get("allow_tls_without_wallet")
    if wallet_required:
        wallet_location = conn_info.get("tls_wallet_uploaded_dir")
        if not wallet_location:
            raise HTTPException(status_code=400, detail="TLS wallet is required for this connection; upload it first.")

    if not test_password:
        raise HTTPException(status_code=400, detail="Password is required to run discovery.")

    protocol = "TCPS" if protocol == "TCPS" else "TCP"
    ssl_match = True if (protocol == "TCPS" and conn_info.get("allow_tls_without_wallet")) else None

    try:
        oracledb = require_oracledb()
        dsn = build_dsn(
            conn_info["host"],
            int(conn_info["port"]),
            conn_info["service_name"],
            protocol,
            ssl_server_dn_match=ssl_match,
        )
        connect_kwargs: Dict[str, Any] = {"user": conn_info["username"], "dsn": dsn, "password": test_password}
        if wallet_location:
            connect_kwargs["config_dir"] = wallet_location
            connect_kwargs["wallet_location"] = wallet_location

        with oracledb.connect(**connect_kwargs) as connection:
            if not run_snapshot:
                with connection.cursor() as cursor:
                    cursor.execute(get_sql("basic_connectivity_check"))
                    cursor.fetchone()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"{'Discovery' if run_snapshot else 'Connection test'} failed: {exc}")

    if run_snapshot:
        snapshot = _collect_db_snapshot(
            conn_info,
            conn_name=params.name,
            password=test_password,
            wallet_location=wallet_location,
            protocol_override=protocol,
            ssl_server_dn_match=ssl_match,
            migration_type=migration_type,
        )
        return {"status": "success", "message": f"Discovery for '{params.name}' succeeded", "snapshot": snapshot}
    return {"status": "success", "message": f"Connection '{params.name}' test succeeded"}

@app.post("/dbconnection/test")
def test_db_connection(params: DBConnectionCheckParams, username: str = Depends(verify_credentials)):
    return _run_connection_check(params, run_snapshot=False)


@app.post("/dbconnection/discover")
def discover_db(params: DBConnectionDiscoverParams, username: str = Depends(verify_credentials)):
    return _run_connection_check(params, run_snapshot=True, migration_type=params.migration_type)

@app.get("/dbconnection/discover/latest/{name}")
def get_latest_discovery(name: str, username: str = Depends(verify_credentials)):
    disc_dir = get_discovery_dir()
    prefix = f"{name}_"
    snapshot_files = [
        os.path.join(disc_dir, f)
        for f in os.listdir(disc_dir)
        if f.startswith(prefix) and f.endswith("_snapshot.json")
    ]
    if not snapshot_files:
        return {"status": "not_found"}
    latest_file = max(snapshot_files, key=os.path.getmtime)
    snapshot = _load_json_file(latest_file) or {}
    return {
        "status": "success",
        "file": latest_file,
        "snapshot": snapshot,
    }

@app.post("/WriteResponseFile")
def write_response_file(payload: WriteResponseFileRequest, username: str = Depends(verify_credentials)):
    # Write-only endpoint: the frontend supplies the final response-file lines.
    return _write_responsefile_lines(payload.project, payload.lines)

class RunJobParams(BaseModel):
    project: str
    run_type: str = "EVAL"  # EVAL | MIGRATE
    rsp: Optional[str] = None
    dry_run: Optional[bool] = False
    sourcenode: Optional[str] = None
    srcauth: Optional[str] = None
    srcarg1: Optional[str] = None
    srcarg2: Optional[str] = None
    srcarg3: Optional[str] = None
    sourcesyswallet: Optional[str] = None
    targetnode: Optional[str] = None
    tgtauth: Optional[str] = None
    tgtarg1: Optional[str] = None
    tgtarg2: Optional[str] = None
    tgtarg3: Optional[str] = None
    advisor_mode: Optional[str] = "NONE"  # NONE|ADVISOR|IGNORE_ADVISOR|SKIP_ADVISOR
    flow_control: Optional[str] = "NONE"  # NONE|PAUSE_AFTER|STOP_AFTER
    flow_phase: Optional[str] = None
    genfixup: Optional[str] = None        # YES|NO
    ignore: Optional[List[str]] = None
    schedule: Optional[str] = None        # NOW or ISO datetime
    listphases: Optional[bool] = False
    custom_args: Optional[List[str]] = None


@app.post("/runjob")
def run_job(params: RunJobParams, username: str = Depends(verify_credentials)):
    project = _validate_project_name(params.project)

    # Resolve RSP: prefer request-provided, else from project, else 400
    if not params.rsp:
        proj_obj = _load_project_or_404(project)
        rsp_path = proj_obj.get("rsp")
        if not rsp_path:
            raise HTTPException(status_code=400, detail="rsp is required for job run")
        params.rsp = rsp_path

    # Ensure RSP is absolute: if only filename provided, assume MIGRATION_BASE/responses/<project>/<file>
    if params.rsp and not os.path.isabs(params.rsp):
        rsp_dir = get_responses_dir(project, required=True)
        params.rsp = os.path.join(rsp_dir, params.rsp)

    lines = ["#!/bin/bash", "$ZDM_HOME/bin/zdmcli migrate database \\"]

    def add(flag: str, value: Optional[str]):
        if value:
            lines.append(f"    {flag} {value} \\")

    add("-rsp", params.rsp)
    add("-sourcenode", params.sourcenode)
    add("-srcauth", params.srcauth)
    add("-srcarg1", params.srcarg1)
    add("-srcarg2", params.srcarg2)
    add("-srcarg3", params.srcarg3)
    add("-sourcesyswallet", params.sourcesyswallet)
    add("-targetnode", params.targetnode)
    add("-tgtauth", params.tgtauth)
    add("-tgtarg1", params.tgtarg1)
    add("-tgtarg2", params.tgtarg2)
    add("-tgtarg3", params.tgtarg3)

    # advisor (mutually exclusive)
    advisor = (params.advisor_mode or "NONE").upper()
    if advisor == "ADVISOR":
        lines.append("    -advisor \\")
    elif advisor == "IGNORE_ADVISOR":
        lines.append("    -ignoreadvisor \\")
    elif advisor == "SKIP_ADVISOR":
        lines.append("    -skipadvisor \\")

    # -eval
    if advisor != "ADVISOR" and (params.run_type or "EVAL").upper() == "EVAL":
        lines.append("    -eval \\")

    # genfixup
    if params.genfixup:
        lines.append(f"    -genfixup {params.genfixup} \\")

    # ignore list
    ignore_list = params.ignore or []
    if ignore_list:
        if "ALL" in ignore_list:
            lines.append("    -ignore ALL \\")
        else:
            lines.append(f"    -ignore {','.join(ignore_list)} \\")

    # schedule
    if params.schedule:
        lines.append(f"    -schedule {params.schedule} \\")

    # listphases
    if params.listphases:
        lines.append("    -listphases \\")

    # flow control
    flow = (params.flow_control or "NONE").upper()
    phase = params.flow_phase
    if flow in ("PAUSE_AFTER", "STOP_AFTER"):
        if not phase:
            raise HTTPException(status_code=400, detail=f"{flow.lower()} requires flow_phase")
        flag = "-pauseafter" if flow == "PAUSE_AFTER" else "-stopafter"
        lines.append(f"    {flag} {phase} \\")

    # custom args (list of strings)
    if params.custom_args:
        for arg in params.custom_args:
            a = str(arg).strip()
            if a:
                lines.append(f"    {a} \\")

    if lines[-1].endswith("\\"):
        lines[-1] = lines[-1][:-1]

    script = "\n".join(lines)
    script_path = write_temp_script("runjob_", script, project, required=True)

    if params.dry_run:
        return {"status": "planned", "script_path": script_path, "command": lines, "dry_run": True}

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        # Attempt to extract job ID from output
        job_id = None
        for line in output.splitlines():
            if "job ID" in line:
                # e.g. Operation "zdmcli migrate database" scheduled with the job ID "22".
                import re
                m = re.search(r"job ID \"?(\d+)\"?", line)
                if m:
                    job_id = m.group(1)
                    break
        if job_id:
            save_job_id(job_id)
            _record_project_job_id(project, params.run_type, job_id)
        return {"status": "success", "script_path": script_path, "output": output, "command": lines, "job_id": job_id}
    except subprocess.CalledProcessError as e:
        error_message = f"Run job failed (return code {e.returncode}): {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/responsefile/{project}")
def read_response_file(project: str, username: str = Depends(verify_credentials)):
    project = _validate_project_name(project)
    response_dir = get_responses_dir(project, required=True)
    path = os.path.join(response_dir, f"{project}.rsp")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Response file not found")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read response file: {exc}") from exc
    return {"status": "success", "project": project, "path": path, "content": content}

@app.post("/ReadJobLog")
def read_job_log(params: LogFileParams, username: str = Depends(verify_credentials)):
    file_path = params.file_path
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")

    try:
        with open(file_path, 'r') as file:
            content = file.read()
        return {"status": "success", "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

class WalletFileParams(BaseModel):
    wallet_name: Optional[str] = None
    wallet_path: Optional[str] = None

@app.get("/tlsWallets")
def list_tls_wallets(username: str = Depends(verify_credentials)):
    base_dir = get_tls_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name, "path": path})
    return {"wallets": wallets}


@app.get("/credentialWallets")
def list_credential_wallets(username: str = Depends(verify_credentials)):
    base_dir = get_cred_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name, "path": path})
    return {"wallets": wallets}

@app.post("/OraPKICreateWallet")
def create_wallet(params: WalletFileParams, username: str = Depends(verify_credentials)):
    wallet_path = resolve_cred_wallet_path(params.wallet_name, params.wallet_path)
    create_wallet_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/orapki wallet create -wallet {wallet_path} -auto_login_only"
    ]

    # Join the script lines into a single command
    create_wallet_command = " \\\n".join(create_wallet_script)

    script_path = write_temp_script("create_wallet_", create_wallet_command)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if result.returncode == 0:
            return {"status": "success", "output": output}
        else:
            raise HTTPException(status_code=500, detail={"error": error_output, "output": output})
    except subprocess.CalledProcessError as e:
        error_message = f"Create Wallet failed with return code {e.returncode}: {e.stderr}"
        raise HTTPException(status_code=500, detail=error_message)

class MkstoreParams(BaseModel):
    wallet_name: Optional[str] = None
    wallet_path: Optional[str] = None
    user: str
    password: str

@app.post("/MkstoreCreateCredential")
def create_credential(params: MkstoreParams, username: str = Depends(verify_credentials)):
    wallet_path = resolve_cred_wallet_path(params.wallet_name, params.wallet_path)
    user = params.user
    password = params.password
    create_credential_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/mkstore -wrl {wallet_path} -createCredential store {user} '{password}'"
    ]

    # Join the script lines into a single command
    create_credential_command = " \\\n".join(create_credential_script)

    script_path = write_temp_script("create_credential_", create_credential_command)

    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout.strip()
        error_output = result.stderr.strip()

        if result.returncode == 0:
            return {"status": "success", "output": output}
        else:
            raise HTTPException(status_code=500, detail={"error": error_output, "output": output})
    except subprocess.CalledProcessError as e:
        error_message = f"Create Credential failed with return code {e.returncode}: {e.stderr}"
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/abort/{jobid}")
def abort(jobid: str, project: Optional[str] = None, username: str = Depends(verify_credentials)):
    abort_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli abort job -jobid {jobid}
    """
    abort_script_path = write_temp_script("abort_", abort_script, project)

    try:
        result = subprocess.run(
            ["bash", abort_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Abort job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

@app.post("/suspend/{jobid}")
def suspend(jobid: str, project: Optional[str] = None, username: str = Depends(verify_credentials)):
    suspend_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli suspend job -jobid {jobid}
    """
    suspend_script_path = write_temp_script("suspend_", suspend_script, project)

    try:
        result = subprocess.run(
            ["bash", suspend_script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True
        )
        output = result.stdout
        if result.stderr:
            output += "\nError output:\n" + result.stderr
        return {"status": "success", "output": output}
    except subprocess.CalledProcessError as e:
        error_message = f"Suspend job failed with return code {e.returncode}: {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
