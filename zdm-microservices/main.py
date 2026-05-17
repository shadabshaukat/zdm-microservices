"""
############################################################
# Code Contributors
# Shadab Mohammad, Master Principal Cloud Architect
# Suya Huang, Principal Cloud Architect
# Organization: Oracle
############################################################
"""

from fastapi import FastAPI, HTTPException, Depends, UploadFile, File
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel
try:
    from pydantic import ConfigDict
except ImportError:
    ConfigDict = None
import json
import tempfile
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union, Tuple
from pathlib import Path
import subprocess
import os
import re
import shlex
import hashlib
import shutil
from passlib.context import CryptContext
try:
    from .backend_auth import load_users_hashed, AuthConfigError  # package-style
except ImportError:
    from backend_auth import load_users_hashed, AuthConfigError  # script-style
try:
    from .zdm_rules.catalog import get_profile  # package-style
    from .zdm_rules.environments import (
        CONNECTION_ENVIRONMENTS,
        db_connection_zdm_keys_for_role,
        db_connection_type_supports_role,
        normalize_connection_role,
        normalize_connection_type,
        project_environment_response_values,
        project_rule_group_values,
    )
    from .zdm_rules.jobs import build_migrate_command, validate_job_run_controls
    from .zdm_rules.responsefile import build_response_file_lines
except ImportError:
    from zdm_rules.catalog import get_profile  # script-style
    from zdm_rules.environments import (
        CONNECTION_ENVIRONMENTS,
        db_connection_zdm_keys_for_role,
        db_connection_type_supports_role,
        normalize_connection_role,
        normalize_connection_type,
        project_environment_response_values,
        project_rule_group_values,
    )
    from zdm_rules.jobs import build_migrate_command, validate_job_run_controls
    from zdm_rules.responsefile import build_response_file_lines

app = FastAPI()

MKSTORE_CREDENTIAL_CONNECT_STRING = "store"

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


DISCOVERY_MIGRATION_TYPE_BUCKETS: Dict[str, List[str]] = {
    "OFFLINE_LOGICAL": ["logical_common", "logical_offline_extra"],
    "ONLINE_LOGICAL": ["logical_common"],
    "OFFLINE_PHYSICAL": ["physical_common"],
    "ONLINE_PHYSICAL": ["physical_common", "physical_online_extra"],
    "HYBRID_OFFLINE": ["physical_common", "hybrid_offline_extra"],
}


def _allowed_discovery_migration_types() -> str:
    return ", ".join(DISCOVERY_MIGRATION_TYPE_BUCKETS.keys())


def normalize_discovery_migration_type(value: Optional[str]) -> str:
    normalized = str(value or "").strip().upper().replace(" ", "_").replace("-", "_")
    if not normalized or normalized not in DISCOVERY_MIGRATION_TYPE_BUCKETS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid migration_type. Allowed values: {_allowed_discovery_migration_types()}",
        )
    return normalized


def discovery_sql_buckets(migration_type: str) -> List[str]:
    return list(DISCOVERY_MIGRATION_TYPE_BUCKETS[normalize_discovery_migration_type(migration_type)])

# -----------------------------
# Models used across endpoints
# -----------------------------
class StrictRequestModel(BaseModel):
    if ConfigDict:
        model_config = ConfigDict(extra="forbid")
    else:
        class Config:
            extra = "forbid"


class LogFileReadParams(StrictRequestModel):
    job_id: str
    name: str

# -----------------------------
# Write-only Response File API
# -----------------------------
_SAFE_PROJECT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")
_SAFE_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
class ResponseFileRequest(StrictRequestModel):
    project: str
    migration_method: str
    values: Dict[str, Any]


class CopyResponseFileRequest(StrictRequestModel):
    source_project: str
    target_project: str
    migration_method: str


class CopySavedJobRequest(StrictRequestModel):
    source_project: str
    target_project: str
    migration_method: str
    run_type: str


class SavedJobParams(StrictRequestModel):
    name: str
    project: str
    rsp: Optional[str] = None
    run_type: str
    job_parameters: Optional[Dict[str, Any]] = None
    advisor_mode: Optional[str] = None  # NONE|ADVISOR|IGNORE_ADVISOR|SKIP_ADVISOR
    flow_control: Optional[str] = None  # NONE|PAUSE_AFTER|STOP_AFTER
    flow_phase: Optional[str] = None
    genfixup: Optional[str] = None      # YES|NO
    ignore: Optional[List[str]] = None
    schedule: Optional[str] = None
    listphases: Optional[bool] = False
    custom_args: Optional[List[str]] = None


def _model_to_dict(model: BaseModel) -> Dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump()
    return model.dict()


def _model_to_supplied_dict(model: BaseModel) -> Dict[str, Any]:
    dump = getattr(model, "model_dump", None)
    if callable(dump):
        return dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def _validate_upload_filename(filename: Optional[str]) -> str:
    candidate = str(filename or "").strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or "/" in candidate
        or "\\" in candidate
        or candidate != os.path.basename(candidate)
        or "\x00" in candidate
    ):
        raise HTTPException(status_code=400, detail="Invalid wallet filename")
    return candidate


_TLS_WALLET_STORAGE_NAMES = {
    ".zip": "tls_wallet.zip",
    ".p12": "tls_wallet.p12",
}


def _tls_wallet_storage_filename(filename: Optional[str]) -> str:
    uploaded_name = _validate_upload_filename(filename)
    suffix = Path(uploaded_name).suffix.lower()
    if suffix not in _TLS_WALLET_STORAGE_NAMES:
        raise HTTPException(status_code=400, detail="TLS wallet must be a .zip or .p12 file")
    return _TLS_WALLET_STORAGE_NAMES[suffix]


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


def _validate_connection_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="connection name is required")
    if any(x in name for x in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="connection name contains illegal path characters")
    if not _SAFE_PROJECT_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="connection name must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        )
    return name


def _validate_connection_role(role: Optional[str]) -> Optional[str]:
    if role is None:
        return None
    raw = str(role).strip().lower()
    if not raw:
        return None
    normalized = normalize_connection_role(raw)
    if not normalized:
        raise HTTPException(status_code=400, detail="connection_role must be source or target")
    return normalized


def _validate_connection_type(db_type: Optional[str]) -> Optional[str]:
    if db_type is None:
        return None
    normalized = normalize_connection_type(db_type)
    if not normalized:
        return None
    if normalized not in CONNECTION_ENVIRONMENTS:
        raise HTTPException(status_code=400, detail="db_type must be a ZEUS connection environment")
    return normalized


def _validate_connection_type_for_role(db_type: Optional[str], role: Optional[str]) -> None:
    normalized_type = _validate_connection_type(db_type)
    normalized_role = _validate_connection_role(role)
    if not normalized_type or not normalized_role:
        return
    if not db_connection_type_supports_role(normalized_type, normalized_role):
        raise HTTPException(
            status_code=400,
            detail=f"db_type '{normalized_type}' is not valid for {normalized_role} connections",
        )


def _validate_connection_record_contract(payload: Dict[str, Any]) -> None:
    normalized_role = _validate_connection_role(payload.get("connection_role"))
    if not normalized_role:
        raise HTTPException(status_code=400, detail="connection_role is required")

    normalized_type = _validate_connection_type(payload.get("db_type"))
    if not normalized_type:
        raise HTTPException(status_code=400, detail="db_type is required")

    _validate_connection_type_for_role(normalized_type, normalized_role)
    payload["connection_role"] = normalized_role
    payload["db_type"] = normalized_type


def _api_contract_error(endpoint: str, detail: str) -> None:
    raise HTTPException(status_code=500, detail=f"{endpoint} API contract error: {detail}")


def _api_record_keys(
    record: Dict[str, Any],
    endpoint: str,
    record_name: str,
    required: set[str],
    optional: set[str],
    *,
    allow_extra: bool = False,
) -> None:
    keys = {str(key) for key in record.keys()}
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    details = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra and not allow_extra:
        details.append("unexpected " + ", ".join(extra))
    if details:
        _api_contract_error(endpoint, f"{record_name} has invalid fields ({'; '.join(details)})")


def _require_api_text(record: Dict[str, Any], endpoint: str, record_name: str, key: str) -> None:
    value = record.get(key)
    if not isinstance(value, str) or not value:
        _api_contract_error(endpoint, f"{record_name}.{key} must be a non-empty string")


def _optional_api_text(record: Dict[str, Any], endpoint: str, record_name: str, key: str) -> None:
    value = record.get(key)
    if value is not None and not isinstance(value, str):
        _api_contract_error(endpoint, f"{record_name}.{key} must be a string or null")


def _project_api_record(record_name: str, record: Any, endpoint: str = "GET /projects") -> Dict[str, Any]:
    if not isinstance(record, dict):
        _api_contract_error(endpoint, f"{record_name} must be an object")
    required = {"name", "rsp", "source_connection", "target_connection"}
    optional = {"migration_method", "jobs"}
    _api_record_keys(record, endpoint, record_name, required, optional)
    if record.get("name") != record_name:
        _api_contract_error(endpoint, f"{record_name}.name must match its record key")
    _optional_api_text(record, endpoint, record_name, "rsp")
    _require_api_text(record, endpoint, record_name, "source_connection")
    _require_api_text(record, endpoint, record_name, "target_connection")
    _optional_api_text(record, endpoint, record_name, "migration_method")
    jobs = record.get("jobs")
    if jobs is not None:
        if not isinstance(jobs, dict):
            _api_contract_error(endpoint, f"{record_name}.jobs must be an object")
        for run_type, job_ids in jobs.items():
            if str(run_type).lower() not in {"eval", "migrate"}:
                _api_contract_error(endpoint, f"{record_name}.jobs has unsupported run type {run_type}")
            if not isinstance(job_ids, list) or not all(isinstance(job_id, str) for job_id in job_ids):
                _api_contract_error(endpoint, f"{record_name}.jobs.{run_type} must be a list of strings")
    return dict(record)


def _projects_api_response() -> Dict[str, Dict[str, Any]]:
    projects = load_projects()
    return {
        name: _project_api_record(name, record)
        for name, record in projects.items()
    }


def _dbconnection_api_record(
    record_name: str,
    record: Any,
    endpoint: str = "GET /dbconnections",
    *,
    allow_storage_extra: bool = False,
) -> Dict[str, Any]:
    if not isinstance(record, dict):
        _api_contract_error(endpoint, f"{record_name} must be an object")
    if "username" in record:
        _api_contract_error(endpoint, f"{record_name} has invalid fields (unexpected username)")
    required = {
        "name",
        "host",
        "port",
        "service_name",
        "db_type",
        "connection_role",
        "protocol",
        "allow_tls_without_wallet",
    }
    optional = {"tls_wallet_uploaded_dir"}
    _api_record_keys(record, endpoint, record_name, required, optional, allow_extra=allow_storage_extra)
    if record.get("name") != record_name:
        _api_contract_error(endpoint, f"{record_name}.name must match its record key")
    _require_api_text(record, endpoint, record_name, "host")
    port = record.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        _api_contract_error(endpoint, f"{record_name}.port must be an integer")
    _require_api_text(record, endpoint, record_name, "service_name")
    _require_api_text(record, endpoint, record_name, "db_type")
    role = record.get("connection_role")
    if role not in {"source", "target"}:
        _api_contract_error(endpoint, f"{record_name}.connection_role must be source or target")
    protocol = record.get("protocol")
    if protocol not in {"TCP", "TCPS"}:
        _api_contract_error(endpoint, f"{record_name}.protocol must be TCP or TCPS")
    if not isinstance(record.get("allow_tls_without_wallet"), bool):
        _api_contract_error(endpoint, f"{record_name}.allow_tls_without_wallet must be a boolean")
    _optional_api_text(record, endpoint, record_name, "tls_wallet_uploaded_dir")
    response_keys = [
        "name",
        "host",
        "port",
        "service_name",
        "db_type",
        "connection_role",
        "protocol",
        "allow_tls_without_wallet",
        "tls_wallet_uploaded_dir",
    ]
    return {
        key: record[key]
        for key in response_keys
        if key in record
    }


def _dbconnections_api_response() -> Dict[str, Dict[str, Any]]:
    connections = load_connections()
    return {
        name: _dbconnection_api_record(name, record, allow_storage_extra=True)
        for name, record in connections.items()
    }


def _require_project_connection_role(
    connections: Dict[str, Dict[str, Any]],
    connection_name: Optional[str],
    role: str,
    field_name: str,
) -> str:
    name = _validate_connection_name(connection_name or "")
    info = connections.get(name)
    if not isinstance(info, dict):
        raise HTTPException(status_code=400, detail=f"{field_name} references an unknown connection")
    if normalize_connection_role(info.get("connection_role")) != role:
        raise HTTPException(status_code=400, detail=f"{field_name} must reference a {role} connection")
    _validate_connection_type_for_role(info.get("db_type"), role)
    return name


def _project_environment_values_or_400(
    project_record: Dict[str, Any],
    connections: Dict[str, Dict[str, Any]],
    migration_method: str,
) -> Dict[str, str]:
    _require_project_connection_role(
        connections,
        project_record.get("source_connection"),
        "source",
        "source_connection",
    )
    _require_project_connection_role(
        connections,
        project_record.get("target_connection"),
        "target",
        "target_connection",
    )
    return project_environment_response_values(project_record, connections, migration_method)


def _reject_project_environment_conflicts(
    values: Dict[str, Any],
    environment_values: Dict[str, str],
    migration_method: str,
) -> None:
    method = _normalize_migration_method(migration_method)
    controlled_by_source = set(db_connection_zdm_keys_for_role("source", method))
    controlled_by_target = set(db_connection_zdm_keys_for_role("target", method))

    for key in sorted(controlled_by_source | controlled_by_target):
        if key not in values or values.get(key) in (None, ""):
            continue
        expected = environment_values.get(key)
        if expected and _normalize_migration_method(values.get(key)) == _normalize_migration_method(expected):
            continue
        owner = "source" if key in controlled_by_source else "target"
        if expected:
            raise HTTPException(
                status_code=400,
                detail=f"{key} conflicts with project {owner} connection; expected {expected}",
            )
        raise HTTPException(
            status_code=400,
            detail=f"{key} is controlled by project {owner} connection and must be omitted",
        )


def _validate_project_medium_selection(
    profile: Any,
    project_record: Dict[str, Any],
    connections: Dict[str, Dict[str, Any]],
    values: Dict[str, Any],
) -> None:
    medium = _normalize_migration_method(values.get("DATA_TRANSFER_MEDIUM"))
    if not medium or medium not in profile.medium_keys():
        return

    if profile.method.endswith("_LOGICAL"):
        rule_group_refs = {
            str(name): config.get("from_rule_group")
            for name, config in profile.decision_input_controls.items()
            if isinstance(config, dict) and config.get("from_rule_group")
        }
        allowed = profile.enabled_medium_keys(
            project_rule_group_values(project_record, connections, rule_group_refs)
        )
    elif profile.method.endswith("_PHYSICAL"):
        environment_values = project_environment_response_values(project_record, connections, profile.method)
        platform = environment_values.get("PLATFORM_TYPE") or values.get("PLATFORM_TYPE")
        allowed = profile.platform_medium_keys(platform)
        if not allowed:
            allowed = profile.enabled_medium_keys({"PLATFORM_TYPE": platform})
    else:
        allowed = []

    if allowed and medium not in allowed:
        raise HTTPException(
            status_code=400,
            detail=(
                f"DATA_TRANSFER_MEDIUM {medium} is not available for project source/target "
                f"environment; allowed values: {', '.join(allowed)}"
            ),
        )


def _normalize_migration_method(value: Any) -> str:
    return str(value or "").strip().upper()


def _require_migration_method(value: Any) -> str:
    migration_method = _normalize_migration_method(value)
    if not migration_method:
        raise HTTPException(status_code=400, detail="migration_method is required")
    return migration_method


def _require_run_type(value: Any) -> str:
    run_type = str(value or "").strip().upper()
    if run_type not in {"EVAL", "MIGRATE"}:
        raise HTTPException(status_code=400, detail="run_type must be EVAL or MIGRATE")
    return run_type


def _project_profile_or_400(project: str):
    project_record = _load_project_or_404(project)
    migration_method = _normalize_migration_method(project_record.get("migration_method"))
    if not migration_method:
        raise HTTPException(status_code=400, detail="Project migration_method is required")
    try:
        return get_profile(migration_method)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _compact_job_parameters(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="job_parameters must be an object")
    return {
        str(key): item
        for key, item in value.items()
        if item not in (None, "", [])
    }


def _validate_job_parameter_keys(profile: Any, job_parameters: Dict[str, Any]) -> None:
    allowed = set(profile.common_job_field_keys())
    unknown = sorted(key for key in job_parameters if key not in allowed)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported job parameter for {profile.method}: {', '.join(unknown)}",
        )


def _validate_job_run_controls_or_400(profile: Any, payload: Dict[str, Any]) -> None:
    try:
        validate_job_run_controls(profile, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _saved_job_name(project: str, run_type: str) -> str:
    return f"{project}_{run_type.lower()}"


_SAVED_JOB_API_FIELDS = {
    "name",
    "project",
    "run_type",
    "rsp",
    "job_parameters",
    "advisor_mode",
    "flow_control",
    "flow_phase",
    "genfixup",
    "ignore",
    "schedule",
    "listphases",
    "custom_args",
}


def _validate_saved_job_api_record(record_name: str, job: Any) -> Dict[str, Any]:
    if not isinstance(job, dict):
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' storage record must be an object")

    keys = set(str(key) for key in job.keys())
    if keys != _SAVED_JOB_API_FIELDS:
        missing = sorted(_SAVED_JOB_API_FIELDS - keys)
        extra = sorted(keys - _SAVED_JOB_API_FIELDS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise HTTPException(
            status_code=500,
            detail=f"Saved job '{record_name}' violates API contract: {'; '.join(details)}",
        )

    run_type = str(job.get("run_type") or "").strip().upper()
    if run_type not in {"EVAL", "MIGRATE"}:
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' has invalid run_type")
    try:
        project = _validate_project_name(job.get("project") or "")
    except HTTPException as exc:
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' has invalid project") from exc
    expected_name = _saved_job_name(project, run_type)
    if record_name != expected_name or job.get("name") != expected_name:
        raise HTTPException(
            status_code=500,
            detail=f"Saved job '{record_name}' violates API contract: expected name '{expected_name}'",
        )
    if not isinstance(job.get("job_parameters"), dict):
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' job_parameters must be an object")
    if job.get("ignore") is not None and not isinstance(job.get("ignore"), list):
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' ignore must be a list")
    if job.get("custom_args") is not None and not isinstance(job.get("custom_args"), list):
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' custom_args must be a list")
    if job.get("listphases") is not None and not isinstance(job.get("listphases"), bool):
        raise HTTPException(status_code=500, detail=f"Saved job '{record_name}' listphases must be a boolean")
    return job


def _validate_saved_job_profile_contract(record_name: str, job: Dict[str, Any]) -> Dict[str, Any]:
    try:
        profile = _project_profile_or_400(job.get("project"))
        _validate_job_parameter_keys(profile, job["job_parameters"])
        validate_job_run_controls(profile, job)
    except HTTPException as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Saved job '{record_name}' violates API contract: {exc.detail}",
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Saved job '{record_name}' violates API contract: {exc}",
        ) from exc
    return job


def _saved_jobs_api_response() -> Dict[str, Dict[str, Any]]:
    jobs = load_saved_jobs()
    return {
        name: _validate_saved_job_profile_contract(
            name,
            _validate_saved_job_api_record(name, job),
        )
        for name, job in jobs.items()
    }


def _is_identity_response_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or "=" not in stripped:
        return False
    key = stripped.split("=", 1)[0].strip().lower()
    return key in {"project", "filename"}


def _responsefile_path(project: str, create_dir: bool = True) -> str:
    project = _validate_project_name(project)
    if create_dir:
        response_dir = get_responses_dir(project, required=True)
    else:
        response_dir = os.path.join(MIGRATION_BASE, "responses", project)
    return os.path.join(response_dir, f"{project}.rsp")


def _validate_project_responsefile_name(value: Any) -> str:
    candidate = str(value or "").strip()
    if (
        not candidate
        or candidate in {".", ".."}
        or os.path.isabs(candidate)
        or "/" in candidate
        or "\\" in candidate
        or candidate != os.path.basename(candidate)
        or "\x00" in candidate
    ):
        raise HTTPException(
            status_code=400,
            detail="rsp must be a project-owned response file name",
        )
    return candidate


def _project_responsefile_path(project: str, rsp_name: Any) -> str:
    project = _validate_project_name(project)
    filename = _validate_project_responsefile_name(rsp_name)
    response_dir = Path(get_responses_dir(project, required=True))
    rsp_path = response_dir / filename
    resolved_response_dir = response_dir.resolve(strict=False)
    resolved_rsp_path = rsp_path.resolve(strict=False)
    try:
        resolved_rsp_path.relative_to(resolved_response_dir)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="rsp must be a project-owned response file name",
        ) from exc
    return str(rsp_path)


def _sync_project_response_metadata(project: str, migration_method: Optional[str] = None) -> None:
    projects = load_projects()
    if project not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{project}' not found")

    projects[project]["rsp"] = f"{project}.rsp"

    normalized_method = _normalize_migration_method(migration_method)
    if normalized_method:
        projects[project]["migration_method"] = normalized_method

    save_projects(projects)


def _validate_responsefile_rendered_lines(lines_in: List[str]) -> List[str]:
    if not isinstance(lines_in, list) or not all(isinstance(x, str) for x in lines_in):
        raise HTTPException(status_code=400, detail="lines must be a list of strings")

    cleaned: List[str] = []
    for index, line in enumerate(lines_in, start=1):
        if "\n" in line or "\r" in line:
            raise HTTPException(
                status_code=400,
                detail=f"Response file line {index} must not contain newline characters",
            )
        if line.strip() == "":
            continue
        cleaned.append(line)

    if not cleaned:
        raise HTTPException(status_code=400, detail="lines must contain at least one non-empty line")
    return cleaned


def _write_responsefile_lines(project: str, lines_in: List[str], migration_method: Optional[str] = None) -> Dict[str, Any]:
    project = _validate_project_name(project)
    _load_project_or_404(project)

    cleaned = _validate_responsefile_rendered_lines(lines_in)

    response_dir = get_responses_dir(project, required=True)
    script_path = os.path.join(response_dir, f"{project}.rsp")
    content = "\n".join(cleaned) + "\n"

    with open(script_path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)

    sha256 = hashlib.sha256(content.encode("utf-8")).hexdigest()

    effective_migration_method = _normalize_migration_method(migration_method)
    _sync_project_response_metadata(project, effective_migration_method)

    result = {
        "status": "success",
        "message": f"Response file {project}.rsp written successfully",
        "project": project,
        "path": script_path,
        "line_count": len(cleaned),
        "sha256": sha256,
    }
    if effective_migration_method:
        result["migration_method"] = effective_migration_method
    return result


def _compile_responsefile_lines(project: str, migration_method: str, values: Dict[str, Any]) -> Tuple[str, List[str]]:
    project = _validate_project_name(project)
    project_record = _load_project_or_404(project)
    normalized_method = _require_migration_method(migration_method)
    if not isinstance(values, dict):
        raise HTTPException(status_code=400, detail="values must be an object")

    if "MIGRATION_METHOD" in values:
        payload_method = _normalize_migration_method(values.get("MIGRATION_METHOD"))
        if payload_method != normalized_method:
            raise HTTPException(
                status_code=400,
                detail="values.MIGRATION_METHOD conflicts with migration_method",
            )

    connections = load_connections()
    environment_values = _project_environment_values_or_400(
        project_record,
        connections,
        normalized_method,
    )
    _reject_project_environment_conflicts(values, environment_values, normalized_method)

    compiled_values: Dict[str, Any] = {"MIGRATION_METHOD": normalized_method}
    compiled_values.update(values)
    compiled_values.update(environment_values)
    compiled_values["MIGRATION_METHOD"] = normalized_method

    try:
        profile = get_profile(normalized_method)
        _validate_project_medium_selection(profile, project_record, connections, compiled_values)
        lines = build_response_file_lines(compiled_values, profile=profile)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return normalized_method, _validate_responsefile_rendered_lines(lines)


def _preview_responsefile(payload: ResponseFileRequest) -> Dict[str, Any]:
    project = _validate_project_name(payload.project)
    normalized_method, lines = _compile_responsefile_lines(project, payload.migration_method, payload.values)
    return {
        "status": "planned",
        "project": project,
        "filename": f"{project}.rsp",
        "lines": lines,
        "migration_method": normalized_method,
    }


def _copy_responsefile_from_project(source_project: str, target_project: str, migration_method: str) -> Dict[str, Any]:
    source_project = _validate_project_name(source_project)
    target_project = _validate_project_name(target_project)
    requested_method = _require_migration_method(migration_method)

    projects = load_projects()
    source_record = projects.get(source_project)
    target_record = projects.get(target_project)

    if not source_record:
        raise HTTPException(status_code=404, detail=f"Source project '{source_project}' not found")
    if not target_record:
        raise HTTPException(status_code=404, detail=f"Target project '{target_project}' not found")

    source_method = _normalize_migration_method(source_record.get("migration_method"))
    if not source_method:
        raise HTTPException(status_code=400, detail="Source project migration_method is required")
    if source_method != requested_method:
        raise HTTPException(status_code=400, detail="Source project migration_method does not match requested migration_method")

    target_method = _normalize_migration_method(target_record.get("migration_method"))
    if target_method and target_method != requested_method:
        raise HTTPException(status_code=400, detail="Target project migration_method does not match requested migration_method")

    source_path = _responsefile_path(source_project, create_dir=False)
    if not os.path.exists(source_path):
        raise HTTPException(status_code=404, detail="Source response file not found")

    try:
        with open(source_path, "r", encoding="utf-8") as handle:
            source_lines = handle.read().splitlines()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read source response file: {exc}") from exc

    copied_lines = [line for line in source_lines if not _is_identity_response_line(line)]
    result = _write_responsefile_lines(target_project, copied_lines, migration_method=requested_method)
    result["source_project"] = source_project
    result["target_project"] = target_project
    result["migration_method"] = requested_method
    result["message"] = f"Response file values copied from '{source_project}' to '{target_project}'"
    return result


def _copy_saved_job_from_project(source_project: str, target_project: str, migration_method: str, run_type: str) -> Dict[str, Any]:
    source_project = _validate_project_name(source_project)
    target_project = _validate_project_name(target_project)
    requested_method = _require_migration_method(migration_method)
    requested_run_type = _require_run_type(run_type)

    projects = load_projects()
    source_record = projects.get(source_project)
    target_record = projects.get(target_project)

    if not source_record:
        raise HTTPException(status_code=404, detail=f"Source project '{source_project}' not found")
    if not target_record:
        raise HTTPException(status_code=404, detail=f"Target project '{target_project}' not found")

    source_method = _normalize_migration_method(source_record.get("migration_method"))
    if source_method != requested_method:
        raise HTTPException(status_code=400, detail="Source project migration_method does not match requested migration_method")

    target_method = _normalize_migration_method(target_record.get("migration_method"))
    if target_method != requested_method:
        raise HTTPException(status_code=400, detail="Target project migration_method does not match requested migration_method")

    jobs = load_saved_jobs()
    source_name = _saved_job_name(source_project, requested_run_type)
    source_job = jobs.get(source_name)
    if (
        not isinstance(source_job, dict)
        or str(source_job.get("project")) != source_project
        or str(source_job.get("run_type") or "").strip().upper() != requested_run_type
    ):
        raise HTTPException(status_code=404, detail="Source saved job definition not found for requested run_type")
    source_job = _validate_saved_job_api_record(source_name, source_job)
    source_job = _validate_saved_job_profile_contract(source_name, source_job)

    target_rsp_value = target_record.get("rsp")
    target_rsp = target_rsp_value.strip() if isinstance(target_rsp_value, str) and target_rsp_value.strip() else f"{target_project}.rsp"
    target_name = _saved_job_name(target_project, requested_run_type)
    copied_params = SavedJobParams(
        **{
            **source_job,
            "name": target_name,
            "project": target_project,
            "rsp": target_rsp,
            "run_type": requested_run_type,
        }
    )
    copied_job = _model_to_dict(copied_params)
    target_profile = _project_profile_or_400(target_project)
    copied_job["job_parameters"] = _compact_job_parameters(copied_job.get("job_parameters"))
    _validate_job_parameter_keys(target_profile, copied_job["job_parameters"])
    _validate_job_run_controls_or_400(target_profile, copied_job)

    jobs[target_name] = copied_job
    save_saved_jobs(jobs)

    return {
        "status": "success",
        "message": f"Saved job definition copied from '{source_project}' to '{target_project}'",
        "source_project": source_project,
        "target_project": target_project,
        "migration_method": requested_method,
        "run_type": requested_run_type,
        "job": copied_job,
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
    if not isinstance(proj, dict):
        raise HTTPException(status_code=404, detail="Project not found")
    return _project_api_record(project, proj, "projects storage")


def _project_owned_dir(category: str, project: str) -> Path:
    base_dir = (Path(MIGRATION_BASE) / category).resolve(strict=False)
    target_dir = (base_dir / project).resolve(strict=False)
    try:
        target_dir.relative_to(base_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid project {category} path") from exc
    return target_dir


def _delete_project_owned_dirs(project: str) -> List[str]:
    removed: List[str] = []
    for category in ("responses", "scripts"):
        target_dir = _project_owned_dir(category, project)
        if target_dir.exists():
            shutil.rmtree(target_dir)
            removed.append(str(target_dir))
    return removed


def _delete_project_saved_jobs(project: str) -> int:
    saved_jobs = load_saved_jobs()
    kept: Dict[str, Dict[str, Any]] = {}
    removed_count = 0
    for name, job in saved_jobs.items():
        belongs_to_project = False
        if isinstance(job, dict):
            belongs_to_project = str(job.get("project") or "") == project
        if belongs_to_project:
            removed_count += 1
            continue
        kept[name] = job
    if removed_count:
        save_saved_jobs(kept)
    return removed_count


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
    proj = _project_api_record(project, projects.get(project), "projects storage")
    jobs = dict(proj.get("jobs") or {})
    lst = list(jobs.get(rt, []))
    if job_id not in lst:
        lst.append(job_id)
        jobs[rt] = lst
        proj["jobs"] = jobs
        projects[project] = _project_api_record(project, proj, "projects storage")
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


@app.get("/jobs/ids")
def list_job_ids(username: str = Depends(verify_credentials)):
    return {"job_ids": load_job_ids()}


def _zdm_job_snapshot_file_path() -> str:
    target_dir = os.path.join(MIGRATION_BASE, "jobs")
    os.makedirs(target_dir, exist_ok=True)
    return os.path.join(target_dir, "zdm_job_snapshot.json")


def _load_zdm_job_snapshot() -> Dict[str, Any]:
    payload = _load_json_file(_zdm_job_snapshot_file_path())
    return payload if isinstance(payload, dict) else {}


def _save_zdm_job_snapshot(snapshot: Dict[str, Any]) -> None:
    _save_json_file(_zdm_job_snapshot_file_path(), snapshot)


def _snapshot_with_runtime_warning(snapshot: Dict[str, Any], warning: str) -> Dict[str, Any]:
    payload = dict(snapshot)
    raw_warnings = payload.get("warnings")
    warnings = list(raw_warnings) if isinstance(raw_warnings, list) else []
    if warning:
        warnings.append(warning)
    payload["warnings"] = warnings
    return payload


def _called_process_error_text(exc: subprocess.CalledProcessError) -> str:
    parts = []
    for value in (getattr(exc, "output", None), getattr(exc, "stdout", None), getattr(exc, "stderr", None)):
        text = str(value) if value else ""
        if text and text not in parts:
            parts.append(text)
    return "\n".join(parts).strip()


def _cached_job_query_output(jobid: str, query_error: str) -> str:
    snapshot = _load_zdm_job_snapshot()
    jobs = snapshot.get("jobs")
    if not isinstance(jobs, list):
        return ""

    for job in jobs:
        if isinstance(job, dict) and str(job.get("job_id") or "") == jobid:
            last_refreshed = str(snapshot.get("last_refreshed") or "unknown")
            return "\n".join(
                [
                    f"Live ZDM query failed; showing cached job snapshot from {last_refreshed}.",
                    "",
                    query_error,
                    "",
                    json.dumps(job, indent=2),
                ]
            ).strip()
    return ""


def _clean_zdm_value(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2 and cleaned[0] == cleaned[-1] and cleaned[0] in ("'", '"'):
        return cleaned[1:-1]
    return cleaned


def _attribute_key(label: str) -> str:
    key = re.sub(r"[^A-Za-z0-9]+", "_", label.strip().lower()).strip("_")
    return key or "attribute"


def _parse_elapsed_seconds(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    units = {
        "day": 86400,
        "days": 86400,
        "hour": 3600,
        "hours": 3600,
        "minute": 60,
        "minutes": 60,
        "second": 1,
        "seconds": 1,
    }
    total = 0
    found = False
    for amount, unit in re.findall(r"(\d+)\s*(days?|hours?|minutes?|seconds?)", text.lower()):
        found = True
        total += int(amount) * units[unit]
    return total if found else None


def _parse_scheduled_command_args(command: str) -> Dict[str, Any]:
    if not command:
        return {}
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    args: Dict[str, Any] = {}
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if not token.startswith("-") or token == "-":
            index += 1
            continue

        key = token.lstrip("-")
        value: Any = True
        if index + 1 < len(tokens) and not tokens[index + 1].startswith("-"):
            value = tokens[index + 1]
            index += 1

        existing = args.get(key)
        if existing is None:
            args[key] = value
        elif isinstance(existing, list):
            existing.append(value)
        else:
            args[key] = [existing, value]
        index += 1
    return args


def _derive_current_phase(phases: List[Dict[str, str]]) -> Optional[str]:
    if not phases:
        return None
    for phase in phases:
        if (phase.get("status") or "").upper() == "FAILED":
            return phase.get("name")

    active_statuses = {"RUNNING", "EXECUTING", "STARTED", "IN_PROGRESS"}
    for phase in phases:
        if (phase.get("status") or "").upper() in active_statuses:
            return phase.get("name")

    for phase in reversed(phases):
        if (phase.get("status") or "").upper() != "PENDING":
            return phase.get("name")
    return None


def _parse_zdm_query_job_output(output: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    jobs: List[Dict[str, Any]] = []
    warnings: List[str] = []
    current: Optional[Dict[str, Any]] = None
    in_embedded_result = False

    def new_job(job_id: str) -> Dict[str, Any]:
        return {
            "job_id": str(job_id),
            "times": {},
            "files": {},
            "phases": [],
            "attributes": {},
            "warnings": [],
        }

    def finish_job(job: Dict[str, Any]) -> Dict[str, Any]:
        command = job.get("scheduled_command") or ""
        job["scheduled_args"] = _parse_scheduled_command_args(command)
        elapsed = job.get("times", {}).get("elapsed_text")
        elapsed_seconds = _parse_elapsed_seconds(elapsed)
        if elapsed_seconds is not None:
            job["times"]["elapsed_seconds"] = elapsed_seconds
        current_phase = _derive_current_phase(job.get("phases", []))
        if current_phase:
            job["current_phase"] = current_phase
        return job

    phase_re = re.compile(r"^([A-Z][A-Z0-9_]+)\s+\.{2,}\s+([A-Z][A-Z0-9_ -]*)$")

    for raw_line in (output or "").splitlines():
        line = raw_line.strip()
        job_match = re.match(r"^Job ID:\s*(\S+)\s*$", line)
        if job_match:
            if current is not None:
                jobs.append(finish_job(current))
            current = new_job(job_match.group(1))
            in_embedded_result = False
            continue

        if current is None:
            continue
        if not line:
            continue

        if line.startswith("Result file ") and line.endswith(" contents:"):
            in_embedded_result = True
            continue
        if "JOB_EXECUTION_DETAILS_START" in line:
            in_embedded_result = True
            continue
        if "JOB_EXECUTION_DETAILS_END" in line:
            in_embedded_result = False
            continue
        if in_embedded_result:
            continue

        phase_match = phase_re.match(line)
        if phase_match:
            current["phases"].append({
                "name": phase_match.group(1),
                "status": phase_match.group(2).strip().upper(),
            })
            continue

        if ":" not in line:
            continue

        label, value_raw = line.split(":", 1)
        label = label.strip()
        value = _clean_zdm_value(value_raw)
        if label == "Scheduled job execution start time":
            value = value.split(". Equivalent local time:", 1)[0].strip()
            current["times"]["scheduled_start"] = value
        elif label == "Job Type":
            current["job_type"] = value
        elif label == "Scheduled job command":
            current["scheduled_command"] = value
        elif label == "Current status":
            current["status"] = value.upper()
        elif label == "Result file path":
            current["files"]["result"] = value
        elif label == "Metrics file path":
            current["files"]["metrics"] = value
        elif label == "Excluded objects file path":
            current["files"]["excluded_objects"] = value
        elif label == "Job execution start time":
            current["times"]["execution_start"] = value
        elif label == "Job execution end time":
            current["times"]["execution_end"] = value
        elif label == "Job execution elapsed time":
            current["times"]["elapsed_text"] = value
        else:
            current["attributes"][_attribute_key(label)] = value

    if current is not None:
        jobs.append(finish_job(current))

    return jobs, warnings


def _link_project_for_zdm_job(job: Dict[str, Any], projects: Dict[str, Dict[str, Any]]) -> Optional[str]:
    job_id = str(job.get("job_id") or "")
    if job_id:
        for project_name, project in projects.items():
            job_map = project.get("jobs", {})
            if not isinstance(job_map, dict):
                continue
            for ids in job_map.values():
                if isinstance(ids, list) and any(str(value) == job_id for value in ids):
                    return project_name

    rsp = str((job.get("scheduled_args") or {}).get("rsp") or "")
    if rsp:
        match = re.search(r"/responses/([^/]+)/", rsp)
        if match and match.group(1) in projects:
            return match.group(1)
        rsp_name = Path(rsp).stem
        if rsp_name in projects:
            return rsp_name
    return None


def _read_responsefile_values_from_path(path: str) -> Dict[str, str]:
    if not path:
        return {}
    try:
        if not os.path.exists(path):
            return {}
        values: Dict[str, str] = {}
        with open(path, "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if not stripped or stripped.startswith("#") or "=" not in stripped:
                    continue
                key, value = stripped.split("=", 1)
                values[key.strip()] = value.strip()
        return values
    except Exception:
        return {}


def _read_responsefile_values(project: str) -> Dict[str, str]:
    if not project:
        return {}
    return _read_responsefile_values_from_path(_responsefile_path(project, create_dir=False))


def _inventory_for_zdm_job(
    job: Dict[str, Any],
    projects: Dict[str, Dict[str, Any]],
    connections: Dict[str, Dict[str, Any]],
) -> Dict[str, Any]:
    project_name = job.get("project")
    project = projects.get(project_name, {}) if project_name else {}
    source_name = project.get("source_connection") if isinstance(project, dict) else None
    target_name = project.get("target_connection") if isinstance(project, dict) else None
    response_file = _read_responsefile_values(project_name) if project_name else {}
    if not response_file:
        rsp = str((job.get("scheduled_args") or {}).get("rsp") or "")
        if os.path.isabs(rsp):
            response_file = _read_responsefile_values_from_path(rsp)
    return {
        "project": dict(project) if isinstance(project, dict) else {},
        "source_connection": dict(connections.get(source_name, {})) if source_name else {},
        "target_connection": dict(connections.get(target_name, {})) if target_name else {},
        "response_file": response_file,
    }


def _refresh_zdm_job_snapshot() -> Dict[str, Any]:
    query_script = """
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli query job
    """
    script_path = write_temp_script("query_jobs_", query_script, "_global")
    result = subprocess.run(
        ["/bin/bash", script_path],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
    )
    if result.returncode != 0:
        raise HTTPException(
            status_code=500,
            detail=f"Query jobs failed with return code {result.returncode}: {result.stderr or result.stdout}",
        )

    jobs, warnings = _parse_zdm_query_job_output(result.stdout)
    projects = load_projects()
    for job in jobs:
        project = _link_project_for_zdm_job(job, projects)
        if project:
            job["project"] = project

    snapshot = {
        "schema_version": 1,
        "last_refreshed": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "command": "$ZDM_HOME/bin/zdmcli query job",
        "return_code": result.returncode,
        "raw_stdout": result.stdout,
        "raw_stderr": result.stderr,
        "jobs": jobs,
        "warnings": warnings,
    }
    _save_zdm_job_snapshot(snapshot)
    return snapshot


@app.get("/jobs")
def list_zdm_jobs(
    refresh: bool = False,
    username: str = Depends(verify_credentials),
):
    snapshot = _load_zdm_job_snapshot()
    source = "cache"
    if refresh or not snapshot:
        try:
            snapshot = _refresh_zdm_job_snapshot()
            source = "zdmcli"
        except HTTPException as exc:
            if not snapshot:
                snapshot = {"last_refreshed": None, "jobs": [], "warnings": [str(exc.detail)]}
                source = "zdmcli-unavailable"
            else:
                snapshot = _snapshot_with_runtime_warning(snapshot, str(exc.detail))
                source = "cache"

    jobs = snapshot.get("jobs", [])
    if not isinstance(jobs, list):
        jobs = []

    projects = load_projects()
    connections = load_connections()

    records = []
    for job in jobs:
        inventory = _inventory_for_zdm_job(job, projects, connections)
        records.append({"job": job, "inventory": inventory})

    return {
        "status": "success",
        "source": source,
        "last_refreshed": snapshot.get("last_refreshed"),
        "jobs": records,
        "warnings": snapshot.get("warnings", []),
    }


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

    cloud_row: Dict[str, Any] = {}
    rows = cloud_identity if isinstance(cloud_identity, list) else [cloud_identity]
    for row in rows:
        if isinstance(row, dict) and "error" not in row and row.get("DATABASE_OCID"):
            cloud_row = row
            break

    cloud_val = str(cloud_row.get("DATABASE_OCID") or "")
    infra = str(cloud_row.get("INFRASTRUCTURE") or "").lower()
    ci_lower = cloud_val.lower()

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


def _json_safe_db_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, list):
        return [_json_safe_db_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe_db_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe_db_value(item) for key, item in value.items()}
    read = getattr(value, "read", None)
    if callable(read):
        return read()
    return str(value)


def fetch_one_dict(cursor, sql: str) -> Dict[str, Any]:
    cursor.execute(sql)
    row = cursor.fetchone()
    if row is None:
        return {}
    columns = [col[0] for col in cursor.description]
    return {columns[i]: _json_safe_db_value(row[i]) for i in range(len(columns))}


def fetch_all_dicts(cursor, sql: str) -> List[Dict[str, Any]]:
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [col[0] for col in cursor.description]
    result = []
    for row in rows:
        result.append({columns[i]: _json_safe_db_value(row[i]) for i in range(len(columns))})
    return result


def fetch_any(cursor, sql: str) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    cursor.execute(sql)
    rows = cursor.fetchall()
    if not rows:
        return []
    columns = [col[0] for col in cursor.description]
    if len(rows) == 1:
        return {columns[i]: _json_safe_db_value(rows[0][i]) for i in range(len(columns))}
    return [{columns[i]: _json_safe_db_value(row[i]) for i in range(len(columns))} for row in rows]


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


def fetch_discovery_extra_query(cursor, key: str, sql: str) -> Union[Dict[str, Any], List[Dict[str, Any]]]:
    if key == "db_profiles":
        return fetch_all_dicts(cursor, sql)
    return fetch_any(cursor, sql)


def get_connection_dir(name: str) -> str:
    safe = _validate_connection_name(name)
    path = os.path.join(MIGRATION_BASE, "connections", safe)
    os.makedirs(path, exist_ok=True)
    return path


def _safe_filename_component(value: Any, default: str) -> str:
    component = re.sub(r"[^A-Za-z0-9_-]+", "_", str(value or default).strip())
    component = re.sub(r"_+", "_", component).strip("_-")
    return component or default


def _discovery_snapshot_base_filename(conn_name: str, conn_info: Dict[str, Any], ts: str) -> str:
    return "_".join(
        [
            _safe_filename_component(conn_name, "conn"),
            _safe_filename_component(conn_info.get("host"), "conn"),
            _safe_filename_component(conn_info.get("service_name"), "svc"),
            _safe_filename_component(ts, "snapshot"),
        ]
    )


def _load_connection_or_404(name: str) -> Dict[str, Any]:
    name = _validate_connection_name(name)
    connections = load_connections()
    conn_info = connections.get(name)
    if not conn_info:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
    return conn_info


def _collect_db_snapshot(
    conn_info: Dict[str, Any],
    conn_name: str,
    auth_kwargs: Dict[str, Any],
    wallet_location: Optional[str] = None,
    protocol_override: Optional[str] = None,
    ssl_server_dn_match: Optional[bool] = None,
    migration_type: Optional[str] = None,
) -> Dict[str, Any]:
    mig = normalize_discovery_migration_type(migration_type)
    oracledb = require_oracledb()
    dsn = build_dsn(
        conn_info["host"],
        int(conn_info["port"]),
        conn_info["service_name"],
        protocol_override or conn_info.get("protocol", "TCP"),
        ssl_server_dn_match=ssl_server_dn_match,
    )

    connect_kwargs: Dict[str, Any] = {"dsn": dsn, **auth_kwargs}
    if wallet_location:
        connect_kwargs["config_dir"] = wallet_location
        connect_kwargs["wallet_location"] = wallet_location

    connection = oracledb.connect(**connect_kwargs)
    raw_queries: Dict[str, Any] = {}
    snapshot: Dict[str, Any] = {
        "connection": {
            k: conn_info[k]
            for k in ["host", "port", "service_name", "protocol"]
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
            for bucket_name in discovery_sql_buckets(mig):
                bucket_sqls = get_sql_bucket(bucket_name)
                if not bucket_sqls:
                    continue
                extras[bucket_name] = {}
                for key, sql in bucket_sqls.items():
                    try:
                        extras[bucket_name][key] = fetch_discovery_extra_query(cursor, key, sql)
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
        base_fname = _discovery_snapshot_base_filename(conn_name, conn_info, ts)
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


def resolve_project_name(project: Optional[str], required: bool = False, default: str = "_global") -> str:
    if project:
        if project == default:
            return default
        return _validate_project_name(project)
    if required:
        raise HTTPException(status_code=400, detail="project is required")
    return default


def resolve_project_for_job(project: Optional[str], jobid: Optional[str] = None, required: bool = False) -> str:
    if project:
        return project
    if jobid:
        inferred = find_project_by_job(jobid)
        if inferred:
            return inferred
    if required:
        raise HTTPException(status_code=400, detail="project is required for this operation")
    return "_global"


def _validate_job_id(job_id: str) -> str:
    candidate = str(job_id or "").strip()
    if not _SAFE_JOB_ID_RE.fullmatch(candidate):
        raise HTTPException(status_code=400, detail="Invalid job_id")
    return candidate


def get_zdm_scheduled_dir() -> Path:
    zdm_base = os.getenv("ZDM_BASE") or "/u01/app/zdmbase"
    return Path(zdm_base) / "chkbase" / "scheduled"


def _validate_log_file_name(name: str) -> str:
    candidate = str(name or "").strip()
    if not candidate or candidate != os.path.basename(candidate) or "\x00" in candidate:
        raise HTTPException(status_code=400, detail="Invalid log file name")
    return candidate


def _is_job_log_name(job_id: str, name: str) -> bool:
    prefix = f"job-{job_id}"
    return name == prefix or name.startswith(f"{prefix}-") or name.startswith(f"{prefix}.")


def _resolve_job_log_path(job_id: str, name: str) -> Path:
    job_id = _validate_job_id(job_id)
    name = _validate_log_file_name(name)
    if not _is_job_log_name(job_id, name):
        raise HTTPException(status_code=400, detail="Log file name does not match job_id")

    scheduled_dir = get_zdm_scheduled_dir().resolve(strict=False)
    log_path = (scheduled_dir / name).resolve(strict=False)
    try:
        log_path.relative_to(scheduled_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid log file name") from exc
    return log_path


def get_responses_dir(project: str, required: bool = True) -> str:
    pname = resolve_project_name(project, required=required)
    target_dir = os.path.join(MIGRATION_BASE, "responses", pname)
    os.makedirs(target_dir, exist_ok=True)
    return target_dir


def get_scripts_dir(project: str, required: bool = True) -> str:
    pname = resolve_project_name(project, required=required)
    target_dir = os.path.join(MIGRATION_BASE, "scripts", pname)
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


def resolve_cred_wallet_path(wallet_name: Optional[str]) -> str:
    if not wallet_name:
        raise HTTPException(status_code=400, detail="wallet_name is required")
    base_dir = get_cred_wallets_dir()
    return os.path.join(base_dir, _validate_wallet_name(wallet_name))


def _validate_wallet_name(name: str) -> str:
    name = (name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="wallet name is required")
    if any(x in name for x in ("/", "\\", "..")):
        raise HTTPException(status_code=400, detail="wallet name contains illegal path characters")
    if not _SAFE_PROJECT_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="wallet name must match ^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$",
        )
    return name


def write_temp_script(prefix: str, content: str, project: Optional[str] = None, required: bool = False) -> str:
    pname = resolve_project_name(project, required=required)
    target_dir = get_scripts_dir(pname, required=False)
    fd, path = tempfile.mkstemp(prefix=prefix, suffix=".sh", dir=target_dir)
    os.close(fd)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    os.chmod(path, 0o755)
    return path


@app.get("/jobs/{jobid}")
def query(jobid: str, project: Optional[str] = None, username: str = Depends(verify_credentials)):
    jobid = _validate_job_id(jobid)
    # Auto-detect project from projects.json if not provided
    project = resolve_project_for_job(project, jobid=jobid, required=False)
    query_script = f"""
    #!/bin/bash
    $ZDM_HOME/bin/zdmcli query job -jobid {shlex.quote(jobid)}
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
        error_text = _called_process_error_text(e)
        error_message = f"Query Job failed with return code {e.returncode}: {error_text}"
        cached_output = _cached_job_query_output(jobid, error_message)
        if cached_output:
            return {"status": "success", "output": cached_output}
        return {
            "status": "success",
            "output": "\n\n".join(
                [
                    "Live ZDM query failed; no cached job snapshot is available.",
                    error_message,
                ]
            ),
        }


class DBConnectionParams(StrictRequestModel):
    name: str
    host: str
    port: int
    service_name: str
    db_type: Optional[str] = None
    connection_role: Optional[str] = None
    protocol: Optional[str] = "TCP"
    allow_tls_without_wallet: Optional[bool] = False


class DBAuthParams(StrictRequestModel):
    method: str
    username: Optional[str] = None
    password: Optional[str] = None
    wallet_name: Optional[str] = None


class DBConnectionCheckParams(StrictRequestModel):
    name: str
    auth: DBAuthParams
    run_snapshot: bool = False


class DBConnectionDiscoverParams(StrictRequestModel):
    name: str
    auth: DBAuthParams
    migration_type: str  # OFFLINE_LOGICAL, ONLINE_LOGICAL, OFFLINE_PHYSICAL, ONLINE_PHYSICAL, HYBRID_OFFLINE
    role: Optional[str] = None  # optional tag for future compare views


class ProjectParams(StrictRequestModel):
    name: str
    rsp: Optional[str] = None
    source_connection: Optional[str] = None
    target_connection: Optional[str] = None


class PrefillParams(StrictRequestModel):
    project: Optional[str] = None
    source_connection: str
    target_connection: str


@app.post("/dbconnections")
def create_db_connection(params: DBConnectionParams, username: str = Depends(verify_credentials)):
    name = _validate_connection_name(params.name)
    connections = load_connections()
    existing = connections.get(name)
    payload = dict(existing) if isinstance(existing, dict) else {}
    payload.pop("username", None)
    incoming = _model_to_supplied_dict(params) if isinstance(existing, dict) else _model_to_dict(params)
    for key, value in incoming.items():
        if value is None and key in payload:
            continue
        payload[key] = value
    payload["name"] = name
    _validate_connection_record_contract(payload)
    api_payload = _dbconnection_api_record(name, payload, "POST /dbconnections", allow_storage_extra=True)
    connections[name] = payload
    save_connections(connections)
    return {"status": "success", "message": f"Connection '{name}' saved", "connection": api_payload}


@app.get("/dbconnections")
def list_db_connections(username: str = Depends(verify_credentials)):
    return _dbconnections_api_response()


@app.delete("/dbconnections/{name}")
def delete_db_connection(name: str, username: str = Depends(verify_credentials)):
    name = _validate_connection_name(name)
    connections = load_connections()
    if name not in connections:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")
    connections.pop(name)
    save_connections(connections)
    return {"status": "success", "message": f"Connection '{name}' deleted"}


@app.get("/projects")
def list_projects(username: str = Depends(verify_credentials)):
    return _projects_api_response()


@app.post("/projects")
def create_project(params: ProjectParams, username: str = Depends(verify_credentials)):
    name = _validate_project_name(params.name)
    projects = load_projects()
    if name in projects:
        raise HTTPException(status_code=409, detail=f"Project '{name}' already exists. Delete it before creating it again.")
    connections = load_connections()
    source_connection = _require_project_connection_role(
        connections,
        params.source_connection,
        "source",
        "source_connection",
    )
    target_connection = _require_project_connection_role(
        connections,
        params.target_connection,
        "target",
        "target_connection",
    )
    projects[name] = {
        "name": name,
        "rsp": params.rsp,
        "source_connection": source_connection,
        "target_connection": target_connection,
    }
    project_payload = _project_api_record(name, projects[name], "POST /projects")
    projects[name] = project_payload
    save_projects(projects)
    return {"status": "success", "message": f"Project '{name}' saved", "project": project_payload}


@app.delete("/projects/{name}")
def delete_project(name: str, username: str = Depends(verify_credentials)):
    name = _validate_project_name(name)
    projects = load_projects()
    if name not in projects:
        raise HTTPException(status_code=404, detail=f"Project '{name}' not found")

    removed_dirs = _delete_project_owned_dirs(name)
    removed_saved_jobs = _delete_project_saved_jobs(name)
    projects.pop(name)
    save_projects(projects)
    return {
        "status": "success",
        "message": f"Project '{name}' deleted",
        "removed_saved_jobs": removed_saved_jobs,
        "removed_dirs": removed_dirs,
    }


@app.get("/saved-jobs")
def list_saved_jobs(username: str = Depends(verify_credentials)):
    return _saved_jobs_api_response()


@app.post("/saved-jobs")
def upsert_saved_job(params: SavedJobParams, username: str = Depends(verify_credentials)):
    jobs = load_saved_jobs()
    name = (params.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Job name is required")
    project = _validate_project_name(params.project)
    run_type = _require_run_type(params.run_type)
    expected_name = _saved_job_name(project, run_type)
    if name != expected_name:
        raise HTTPException(
            status_code=400,
            detail=f"Job name must be '{expected_name}' for project '{project}' and run_type '{run_type}'",
        )
    profile = _project_profile_or_400(project)
    payload = _model_to_dict(params)
    payload["name"] = expected_name
    payload["run_type"] = run_type
    payload["project"] = project
    payload["job_parameters"] = _compact_job_parameters(payload.get("job_parameters"))
    _validate_job_parameter_keys(profile, payload["job_parameters"])
    _validate_job_run_controls_or_400(profile, payload)
    jobs[expected_name] = payload
    save_saved_jobs(jobs)
    return {"status": "success", "message": f"Job '{expected_name}' saved", "job": payload}


@app.delete("/saved-jobs/{name}")
def delete_saved_job(name: str, username: str = Depends(verify_credentials)):
    jobs = load_saved_jobs()
    if name not in jobs:
        raise HTTPException(status_code=404, detail=f"Saved job '{name}' not found")
    jobs.pop(name)
    save_saved_jobs(jobs)
    return {"status": "success", "message": f"Saved job '{name}' deleted"}


@app.post("/saved-jobs/copy")
def copy_saved_job(payload: CopySavedJobRequest, username: str = Depends(verify_credentials)):
    return _copy_saved_job_from_project(
        payload.source_project,
        payload.target_project,
        payload.migration_method,
        payload.run_type,
    )


@app.post("/dbconnections/{name}/tls-wallet")
def upload_tls_wallet(name: str, wallet: UploadFile = File(...), username: str = Depends(verify_credentials)):
    name = _validate_connection_name(name)
    connections = load_connections()
    if name not in connections:
        raise HTTPException(status_code=404, detail=f"Connection '{name}' not found")

    conn_dir = get_connection_dir(name)
    wallet_dir = Path(conn_dir) / "tls_wallet"
    wallet_dir.mkdir(parents=True, exist_ok=True)
    wallet_dir_resolved = wallet_dir.resolve(strict=False)
    wallet_filename = _tls_wallet_storage_filename(wallet.filename)
    target_path = (wallet_dir_resolved / wallet_filename).resolve(strict=False)
    try:
        target_path.relative_to(wallet_dir_resolved)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid wallet filename") from exc

    for storage_name in _TLS_WALLET_STORAGE_NAMES.values():
        stale_path = wallet_dir_resolved / storage_name
        if stale_path != target_path and stale_path.exists():
            stale_path.unlink()

    with target_path.open("wb") as handle:
        handle.write(wallet.file.read())

    connections[name]["tls_wallet_uploaded_dir"] = str(wallet_dir_resolved)
    _dbconnection_api_record(
        name,
        connections[name],
        "POST /dbconnections/{name}/tls-wallet",
        allow_storage_extra=True,
    )
    save_connections(connections)

    return {
        "status": "success",
        "message": "TLS wallet uploaded",
        "path": str(target_path),
        "wallet_dir": str(wallet_dir_resolved),
    }


def _resolve_db_auth(auth: DBAuthParams) -> Tuple[Dict[str, Any], Optional[str]]:
    method = (auth.method or "").strip().lower()
    if method == "password":
        if auth.wallet_name:
            raise HTTPException(status_code=400, detail="auth.wallet_name is not valid for password auth")
        db_user = (auth.username or "").strip()
        password = auth.password or ""
        if not db_user:
            raise HTTPException(status_code=400, detail="auth.username is required for password auth")
        if not password:
            raise HTTPException(status_code=400, detail="auth.password is required for password auth")
        return {"user": db_user, "password": password}, None

    if method == "credential_wallet":
        if auth.username or auth.password:
            raise HTTPException(status_code=400, detail="auth.username and auth.password are not valid for credential wallet auth")
        wallet_name = (auth.wallet_name or "").strip()
        wallet_path = resolve_cred_wallet_path(wallet_name)
        if not os.path.isdir(wallet_path):
            raise HTTPException(status_code=404, detail=f"Credential wallet '{wallet_name}' not found")
        credentials = _credential_wallet_credentials(wallet_path)
        if not credentials:
            raise HTTPException(status_code=400, detail="Selected wallet has no credential. Add a credential first.")
        return credentials, None

    raise HTTPException(status_code=400, detail="auth.method must be password or credential_wallet")


def _run_connection_check(params: Union[DBConnectionCheckParams, DBConnectionDiscoverParams], run_snapshot: bool, migration_type: Optional[str] = None):
    if run_snapshot:
        migration_type = normalize_discovery_migration_type(migration_type)

    conn_info = _load_connection_or_404(params.name)
    auth_kwargs, credential_wallet_location = _resolve_db_auth(params.auth)
    wallet_location: Optional[str] = None

    protocol = (conn_info.get("protocol") or "").upper()
    wallet_required = protocol == "TCPS" and not conn_info.get("allow_tls_without_wallet")
    if wallet_required:
        wallet_location = conn_info.get("tls_wallet_uploaded_dir")
        if not wallet_location:
            raise HTTPException(status_code=400, detail="TLS wallet is required for this connection; upload it first.")

    protocol = "TCPS" if protocol == "TCPS" else "TCP"
    ssl_match = True if (protocol == "TCPS" and conn_info.get("allow_tls_without_wallet")) else None
    active_wallet_location = credential_wallet_location or wallet_location

    try:
        oracledb = require_oracledb()
        dsn = build_dsn(
            conn_info["host"],
            int(conn_info["port"]),
            conn_info["service_name"],
            protocol,
            ssl_server_dn_match=ssl_match,
        )
        connect_kwargs: Dict[str, Any] = {"dsn": dsn, **auth_kwargs}
        if active_wallet_location:
            connect_kwargs["config_dir"] = active_wallet_location
            connect_kwargs["wallet_location"] = active_wallet_location

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
            auth_kwargs=auth_kwargs,
            wallet_location=active_wallet_location,
            protocol_override=protocol,
            ssl_server_dn_match=ssl_match,
            migration_type=migration_type,
        )
        return {"status": "success", "message": f"Discovery for '{params.name}' succeeded", "snapshot": snapshot}
    return {"status": "success", "message": f"Connection '{params.name}' test succeeded"}

@app.post("/dbconnections/test")
def test_db_connection(params: DBConnectionCheckParams, username: str = Depends(verify_credentials)):
    return _run_connection_check(params, run_snapshot=False)


@app.post("/dbconnections/discover")
def discover_db(params: DBConnectionDiscoverParams, username: str = Depends(verify_credentials)):
    return _run_connection_check(params, run_snapshot=True, migration_type=params.migration_type)

@app.get("/dbconnections/{name}/discovery/latest")
def get_latest_discovery(name: str, username: str = Depends(verify_credentials)):
    name = _validate_connection_name(name)
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

@app.post("/responsefiles/preview")
def preview_response_file(payload: ResponseFileRequest, username: str = Depends(verify_credentials)):
    return _preview_responsefile(payload)


@app.post("/responsefiles")
def write_response_file(payload: ResponseFileRequest, username: str = Depends(verify_credentials)):
    project = _validate_project_name(payload.project)
    normalized_method, lines = _compile_responsefile_lines(project, payload.migration_method, payload.values)
    return _write_responsefile_lines(project, lines, migration_method=normalized_method)


@app.post("/responsefiles/copy")
def copy_response_file(payload: CopyResponseFileRequest, username: str = Depends(verify_credentials)):
    return _copy_responsefile_from_project(payload.source_project, payload.target_project, payload.migration_method)


class RunJobParams(StrictRequestModel):
    project: str
    run_type: str  # EVAL | MIGRATE
    rsp: Optional[str] = None
    dry_run: Optional[bool] = False
    job_parameters: Optional[Dict[str, Any]] = None
    advisor_mode: Optional[str] = "NONE"  # NONE|ADVISOR|IGNORE_ADVISOR|SKIP_ADVISOR
    flow_control: Optional[str] = "NONE"  # NONE|PAUSE_AFTER|STOP_AFTER
    flow_phase: Optional[str] = None
    genfixup: Optional[str] = None        # YES|NO
    ignore: Optional[List[str]] = None
    schedule: Optional[str] = None        # NOW or ISO datetime
    listphases: Optional[bool] = False
    custom_args: Optional[List[str]] = None


@app.post("/jobs")
def run_job(params: RunJobParams, username: str = Depends(verify_credentials)):
    project = _validate_project_name(params.project)
    proj_obj = _load_project_or_404(project)

    rsp_name = params.rsp or proj_obj.get("rsp")
    if not rsp_name:
        raise HTTPException(status_code=400, detail="rsp is required for job run")
    rsp_path = _project_responsefile_path(project, rsp_name)

    try:
        migration_method = _normalize_migration_method(proj_obj.get("migration_method"))
        response_file_values: Dict[str, str] = {}
        if not migration_method:
            response_file_values = _read_responsefile_values_from_path(rsp_path)
            migration_method = _normalize_migration_method(response_file_values.get("MIGRATION_METHOD"))
        else:
            response_file_values = _read_responsefile_values_from_path(rsp_path)
        profile = get_profile(migration_method)
        params_dict = _model_to_dict(params)
        params_dict["rsp"] = rsp_path
        params_dict["response_file_values"] = response_file_values
        params_dict["job_parameters"] = _compact_job_parameters(params_dict.get("job_parameters"))
        _validate_job_parameter_keys(profile, params_dict["job_parameters"])
        lines = build_migrate_command(profile, params_dict)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

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
        return {"status": "submitted", "script_path": script_path, "output": output, "command": lines, "job_id": job_id}
    except subprocess.CalledProcessError as e:
        error_message = f"Run job failed (return code {e.returncode}): {e.output}"
        raise HTTPException(status_code=500, detail=error_message)

@app.get("/responsefiles/{project}")
def read_response_file(project: str, username: str = Depends(verify_credentials)):
    project = _validate_project_name(project)
    _load_project_or_404(project)
    path = _responsefile_path(project, create_dir=False)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Response file not found")
    try:
        with open(path, "r", encoding="utf-8") as handle:
            content = handle.read()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read response file: {exc}") from exc
    return {"status": "success", "project": project, "path": path, "content": content}

@app.get("/joblogs")
def list_job_logs(job_id: str, username: str = Depends(verify_credentials)):
    job_id = _validate_job_id(job_id)
    scheduled_dir = get_zdm_scheduled_dir()
    logs: List[Dict[str, Any]] = []
    if scheduled_dir.exists():
        for path in sorted(scheduled_dir.iterdir(), key=lambda item: item.name):
            if not path.is_file() or not _is_job_log_name(job_id, path.name):
                continue
            resolved_path = path.resolve(strict=False)
            try:
                resolved_path.relative_to(scheduled_dir.resolve(strict=False))
            except ValueError:
                continue
            stat = path.stat()
            logs.append(
                {
                    "name": path.name,
                    "size_bytes": stat.st_size,
                    "modified_time": datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
                }
            )
    return {"status": "success", "job_id": job_id, "logs": logs}


@app.post("/joblogs/read")
def read_job_log(params: LogFileReadParams, username: str = Depends(verify_credentials)):
    job_id = _validate_job_id(params.job_id)
    log_path = _resolve_job_log_path(job_id, params.name)
    if not log_path.is_file():
        raise HTTPException(status_code=404, detail="Log file not found")

    try:
        with log_path.open("r", encoding="utf-8", errors="replace") as file:
            content = file.read()
        return {"status": "success", "job_id": job_id, "name": log_path.name, "content": content}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading file: {str(e)}")

class WalletFileParams(StrictRequestModel):
    wallet_name: str


def _parse_mkstore_credential_entries(output: str) -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    seen: set[int] = set()
    for line in (output or "").splitlines():
        stripped = line.strip()
        match = re.match(r"^(\d+)\s*:\s+(\S+)\s+(\S+)\s*$", stripped)
        if match:
            index = int(match.group(1))
            if index in seen:
                continue
            seen.add(index)
            entries.append(
                {
                    "index": index,
                    "connect_string": match.group(2).strip(),
                    "username": match.group(3).strip(),
                }
            )
    return entries


def _parse_mkstore_credential_users(output: str) -> List[str]:
    users: List[str] = []
    seen = set()
    for entry in _parse_mkstore_credential_entries(output):
        user = str(entry["username"])
        if user and user not in seen:
            seen.add(user)
            users.append(user)
    return users


def _list_credential_wallet_entries(wallet_path: str) -> List[Dict[str, Any]]:
    script = "\n".join(
        [
            "#!/bin/bash",
            f"$ZDM_HOME/bin/mkstore -wrl {shlex.quote(wallet_path)} -listCredential",
        ]
    )
    script_path = write_temp_script("list_credential_", script)
    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as exc:
        error_text = _called_process_error_text(exc)
        raise HTTPException(status_code=500, detail=f"List credentials failed with return code {exc.returncode}: {error_text}") from exc
    return _parse_mkstore_credential_entries(result.stdout)


def _list_credential_wallet_users(wallet_path: str) -> List[str]:
    users: List[str] = []
    seen = set()
    for entry in _list_credential_wallet_entries(wallet_path):
        user = str(entry["username"])
        if user and user not in seen:
            seen.add(user)
            users.append(user)
    return users


def _parse_mkstore_entry_value(output: str, entry_name: str) -> Optional[str]:
    pattern = re.compile(rf"^\s*{re.escape(entry_name)}\s*=\s*(.*)\s*$")
    for line in (output or "").splitlines():
        match = pattern.match(line)
        if match:
            value = match.group(1).strip()
            return value if value else None
    return None


def _view_credential_wallet_entry(wallet_path: str, entry_name: str) -> Optional[str]:
    script = "\n".join(
        [
            "#!/bin/bash",
            f"$ZDM_HOME/bin/mkstore -wrl {shlex.quote(wallet_path)} -viewEntry {shlex.quote(entry_name)}",
        ]
    )
    script_path = write_temp_script("view_credential_entry_", script)
    try:
        result = subprocess.run(
            ["/bin/bash", script_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as exc:
        error_text = _called_process_error_text(exc)
        raise HTTPException(status_code=500, detail=f"View credential entry failed with return code {exc.returncode}: {error_text}") from exc
    return _parse_mkstore_entry_value(result.stdout, entry_name)


def _credential_wallet_credentials(wallet_path: str) -> Optional[Dict[str, str]]:
    entries = _list_credential_wallet_entries(wallet_path)
    entry = next(
        (
            item
            for item in entries
            if item.get("connect_string") == MKSTORE_CREDENTIAL_CONNECT_STRING
        ),
        None,
    )
    if not entry:
        return None
    password_entry = f"oracle.security.client.password{entry['index']}"
    password = _view_credential_wallet_entry(wallet_path, password_entry)
    if not password:
        raise HTTPException(status_code=400, detail="Selected wallet credential password could not be read.")
    return {"user": str(entry["username"]), "password": password}


def _credential_wallet_username(wallet_path: str) -> Optional[str]:
    users = _list_credential_wallet_users(wallet_path)
    return users[0] if users else None


@app.get("/tls-wallets")
def list_tls_wallets(username: str = Depends(verify_credentials)):
    base_dir = get_tls_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name, "path": path})
    return {"wallets": wallets}


@app.get("/credential-wallets")
def list_credential_wallets(username: str = Depends(verify_credentials)):
    base_dir = get_cred_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name, "path": path, "credential_username": _credential_wallet_username(path)})
    return {"wallets": wallets}


@app.get("/credential-wallets/names")
def list_credential_wallet_names(username: str = Depends(verify_credentials)):
    base_dir = get_cred_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name})
    return {"wallets": wallets}


@app.get("/credential-wallets/paths")
def list_credential_wallet_paths(username: str = Depends(verify_credentials)):
    base_dir = get_cred_wallets_dir()
    wallets = []
    for name in sorted(os.listdir(base_dir)):
        path = os.path.join(base_dir, name)
        if os.path.isdir(path):
            wallets.append({"name": name, "path": path})
    return {"wallets": wallets}


@app.delete("/credential-wallets/{name}")
def delete_credential_wallet(name: str, username: str = Depends(verify_credentials)):
    name = _validate_wallet_name(name)
    wallet_path = resolve_cred_wallet_path(name)
    if not os.path.isdir(wallet_path):
        raise HTTPException(status_code=404, detail=f"Credential wallet '{name}' not found")
    shutil.rmtree(wallet_path)
    return {"status": "success", "message": f"Credential wallet '{name}' deleted", "name": name}

@app.post("/wallets/ora-pki")
def create_wallet(params: WalletFileParams, username: str = Depends(verify_credentials)):
    wallet_path = resolve_cred_wallet_path(params.wallet_name)
    if os.path.exists(wallet_path):
        raise HTTPException(status_code=409, detail="Credential wallet already exists")
    create_wallet_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/orapki wallet create -wallet {shlex.quote(wallet_path)} -auto_login_only"
    ]

    create_wallet_command = "\n".join(create_wallet_script)

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

class MkstoreParams(StrictRequestModel):
    wallet_name: str
    user: str
    password: str

@app.post("/wallets/mkstore-credential")
def create_credential(params: MkstoreParams, username: str = Depends(verify_credentials)):
    wallet_path = resolve_cred_wallet_path(params.wallet_name)
    if not os.path.isdir(wallet_path):
        raise HTTPException(status_code=404, detail="Credential wallet not found")
    user = params.user.strip()
    if not user:
        raise HTTPException(status_code=400, detail="user is required")
    if _credential_wallet_username(wallet_path):
        raise HTTPException(
            status_code=409,
            detail="Credential already exists in this wallet. Delete and recreate the wallet if it is wrong.",
        )
    password = params.password
    create_credential_script = [
        "#!/bin/bash",
        f"$ZDM_HOME/bin/mkstore -wrl {shlex.quote(wallet_path)} -createCredential {MKSTORE_CREDENTIAL_CONNECT_STRING} {shlex.quote(user)} {shlex.quote(password)}"
    ]

    create_credential_command = "\n".join(create_credential_script)

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

if __name__ == "__main__":
    import uvicorn

    host = os.getenv("ZEUS_HOST", "127.0.0.1")
    port = int(os.getenv("ZEUS_PORT", "8001"))
    base = os.getenv("ZEUS_BASE")
    if not base:
        raise RuntimeError("ZEUS_BASE must be set for TLS path resolution.")
    ssl_cert = os.getenv("ZEUS_SSL_CERTFILE", f"{base}/certs/zeus.crt")
    ssl_key = os.getenv("ZEUS_SSL_KEYFILE", f"{base}/certs/zeus.key")

    # Require TLS assets; refuse to start without them.
    if not os.path.isfile(ssl_cert):
        raise RuntimeError(f"SSL cert not found at {ssl_cert}; set ZEUS_SSL_CERTFILE.")
    if not os.path.isfile(ssl_key):
        raise RuntimeError(f"SSL key not found at {ssl_key}; set ZEUS_SSL_KEYFILE.")

    uvicorn.run(
        app,
        host=host,
        port=port,
        ssl_certfile=ssl_cert,
        ssl_keyfile=ssl_key,
    )
