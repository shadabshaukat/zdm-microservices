from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional


DATABASE_DISCOVERY_STATUSES = {
    "informational",
    "passed",
    "difference",
    "source_only",
    "target_only",
    "readiness_issue",
    "not_applicable",
    "not_returned",
}
DATABASE_DISCOVERY_SNAPSHOT_STATUSES = {"available", "missing", "failed"}


def _raise_contract_error(endpoint: str, detail: str) -> None:
    raise ValueError(f"{endpoint} API contract error: {detail}")


def _object(payload: Any, endpoint: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, "expected JSON object")
    return dict(payload)


def _exact_keys(payload: Mapping[str, Any], endpoint: str, expected_keys: set[str]) -> None:
    keys = {str(key) for key in payload.keys()}
    if keys == expected_keys:
        return
    details: List[str] = []
    missing = sorted(expected_keys - keys)
    extra = sorted(keys - expected_keys)
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    _raise_contract_error(endpoint, "; ".join(details))


def _status(payload: Mapping[str, Any], endpoint: str, expected: str = "success") -> None:
    if payload.get("status") != expected:
        _raise_contract_error(endpoint, f"expected status {expected}")


def _text(payload: Mapping[str, Any], endpoint: str, key: str, *, allow_empty: bool = False) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or (not allow_empty and not value):
        detail = f"{key} must be a string" if allow_empty else f"{key} must be a non-empty string"
        _raise_contract_error(endpoint, detail)
    return value


def _named_record_mapping(payload: Any, endpoint: str) -> Dict[str, Dict[str, Any]]:
    data = _object(payload, endpoint)
    result: Dict[str, Dict[str, Any]] = {}
    for name, record in data.items():
        record_name = str(name)
        if not record_name:
            _raise_contract_error(endpoint, "record key must be a non-empty string")
        if not isinstance(record, Mapping):
            _raise_contract_error(endpoint, f"{record_name} must be an object")
        record_dict = dict(record)
        embedded_name = record_dict.get("name")
        if embedded_name not in (None, record_name):
            _raise_contract_error(endpoint, f"{record_name}.name must match its record key")
        result[record_name] = record_dict
    return result


def _optional_text(payload: Mapping[str, Any], endpoint: str, key: str) -> None:
    value = payload.get(key)
    if value is not None and not isinstance(value, str):
        _raise_contract_error(endpoint, f"{key} must be a string or null")


def _project_record(record_name: str, record: Mapping[str, Any], endpoint: str) -> Dict[str, Any]:
    required = {"name", "rsp", "source_connection", "target_connection", "migration_method"}
    optional = {"jobs"}
    keys = {str(key) for key in record.keys()}
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    details: List[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    if details:
        _raise_contract_error(endpoint, f"{record_name} has invalid fields ({'; '.join(details)})")
    if record.get("name") != record_name:
        _raise_contract_error(endpoint, f"{record_name}.name must match its record key")
    _optional_text(record, endpoint, "rsp")
    _text(record, endpoint, "source_connection")
    _text(record, endpoint, "target_connection")
    _text(record, endpoint, "migration_method")
    jobs = record.get("jobs")
    if jobs is not None:
        if not isinstance(jobs, Mapping):
            _raise_contract_error(endpoint, f"{record_name}.jobs must be an object")
        for run_type, job_ids in jobs.items():
            if str(run_type).lower() not in {"eval", "migrate"}:
                _raise_contract_error(endpoint, f"{record_name}.jobs has unsupported run type {run_type}")
            if not isinstance(job_ids, list) or not all(isinstance(job_id, str) for job_id in job_ids):
                _raise_contract_error(endpoint, f"{record_name}.jobs.{run_type} must be a list of strings")
    return dict(record)


def _dbconnection_record(record_name: str, record: Mapping[str, Any], endpoint: str) -> Dict[str, Any]:
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
    optional = {"tls_wallet_uploaded_dir", "credential_wallet_name"}
    keys = {str(key) for key in record.keys()}
    missing = sorted(required - keys)
    extra = sorted(keys - required - optional)
    details: List[str] = []
    if missing:
        details.append("missing " + ", ".join(missing))
    if extra:
        details.append("unexpected " + ", ".join(extra))
    if details:
        _raise_contract_error(endpoint, f"{record_name} has invalid fields ({'; '.join(details)})")
    if record.get("name") != record_name:
        _raise_contract_error(endpoint, f"{record_name}.name must match its record key")
    _text(record, endpoint, "host")
    port = record.get("port")
    if not isinstance(port, int) or isinstance(port, bool):
        _raise_contract_error(endpoint, f"{record_name}.port must be an integer")
    _text(record, endpoint, "service_name")
    _text(record, endpoint, "db_type")
    role = record.get("connection_role")
    if role not in {"source", "target"}:
        _raise_contract_error(endpoint, f"{record_name}.connection_role must be source or target")
    protocol = record.get("protocol")
    if protocol not in {"TCP", "TCPS"}:
        _raise_contract_error(endpoint, f"{record_name}.protocol must be TCP or TCPS")
    if not isinstance(record.get("allow_tls_without_wallet"), bool):
        _raise_contract_error(endpoint, f"{record_name}.allow_tls_without_wallet must be a boolean")
    _optional_text(record, endpoint, "tls_wallet_uploaded_dir")
    _optional_text(record, endpoint, "credential_wallet_name")
    return dict(record)


def validate_projects_response(payload: Any) -> Dict[str, Dict[str, Any]]:
    endpoint = "GET /projects"
    records = _named_record_mapping(payload, endpoint)
    return {
        name: _project_record(name, record, endpoint)
        for name, record in records.items()
    }


def validate_dbconnections_response(payload: Any) -> Dict[str, Dict[str, Any]]:
    endpoint = "GET /dbconnections"
    records = _named_record_mapping(payload, endpoint)
    return {
        name: _dbconnection_record(name, record, endpoint)
        for name, record in records.items()
    }


def validate_project_create_response(payload: Any, *, expected_project: str) -> Dict[str, Any]:
    endpoint = "POST /projects"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message", "project"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    project = data.get("project")
    if not isinstance(project, Mapping):
        _raise_contract_error(endpoint, "project must be an object")
    data["project"] = _project_record(expected_project, project, endpoint)
    return data


def validate_project_delete_response(payload: Any) -> Dict[str, Any]:
    endpoint = "DELETE /projects/{name}"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message", "removed_saved_jobs", "removed_dirs"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    if not isinstance(data.get("removed_saved_jobs"), int) or isinstance(data.get("removed_saved_jobs"), bool):
        _raise_contract_error(endpoint, "removed_saved_jobs must be an integer")
    if not isinstance(data.get("removed_dirs"), list) or not all(isinstance(item, str) for item in data["removed_dirs"]):
        _raise_contract_error(endpoint, "removed_dirs must be a list of strings")
    return data


def validate_dbconnection_save_response(payload: Any, *, expected_name: str) -> Dict[str, Any]:
    endpoint = "POST /dbconnections"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message", "connection"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    connection = data.get("connection")
    if not isinstance(connection, Mapping):
        _raise_contract_error(endpoint, "connection must be an object")
    data["connection"] = _dbconnection_record(expected_name, connection, endpoint)
    return data


def validate_dbconnection_delete_response(payload: Any) -> Dict[str, Any]:
    endpoint = "DELETE /dbconnections/{name}"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    return data


def validate_tls_wallet_upload_response(payload: Any) -> Dict[str, Any]:
    endpoint = "POST /dbconnections/{name}/tls-wallet"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message", "path", "wallet_dir"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    _text(data, endpoint, "path")
    _text(data, endpoint, "wallet_dir")
    return data


def validate_dbconnection_test_response(payload: Any) -> Dict[str, Any]:
    endpoint = "POST /dbconnections/test"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    return data


def validate_discovery_response(payload: Any) -> Dict[str, Any]:
    endpoint = "POST /dbconnections/discover"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "message", "snapshot"})
    _status(data, endpoint)
    _text(data, endpoint, "message")
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, Mapping):
        _raise_contract_error(endpoint, "snapshot must be an object")
    return dict(snapshot)


def validate_discovery_latest_response(payload: Any) -> Optional[Dict[str, Any]]:
    endpoint = "GET /dbconnections/{name}/discovery/latest"
    data = _object(payload, endpoint)
    status = data.get("status")
    if status == "not_found":
        _exact_keys(data, endpoint, {"status"})
        return None
    _exact_keys(data, endpoint, {"status", "file", "snapshot"})
    _status(data, endpoint)
    _text(data, endpoint, "file")
    snapshot = data.get("snapshot")
    if not isinstance(snapshot, Mapping):
        _raise_contract_error(endpoint, "snapshot must be an object")
    return dict(snapshot)


def validate_database_discovery_response(payload: Any) -> Dict[str, Any]:
    endpoint = "GET /projects/{project}/database-discovery"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "project", "snapshots", "summary", "sections", "diagnostics"})
    _status(data, endpoint)

    project = data.get("project")
    if not isinstance(project, Mapping):
        _raise_contract_error(endpoint, "project must be an object")
    _exact_keys(project, endpoint, {"name", "migration_method", "source_connection", "target_connection"})
    _text(project, endpoint, "name")
    _text(project, endpoint, "migration_method")
    _text(project, endpoint, "source_connection")
    _text(project, endpoint, "target_connection")
    data["project"] = dict(project)

    snapshots = data.get("snapshots")
    if not isinstance(snapshots, Mapping):
        _raise_contract_error(endpoint, "snapshots must be an object")
    _exact_keys(snapshots, endpoint, {"source", "target"})
    data["snapshots"] = {
        "source": _database_discovery_snapshot(snapshots.get("source"), endpoint, "snapshots.source"),
        "target": _database_discovery_snapshot(snapshots.get("target"), endpoint, "snapshots.target"),
    }

    data["summary"] = _database_discovery_summary(data.get("summary"), endpoint)
    sections = data.get("sections")
    if not isinstance(sections, list):
        _raise_contract_error(endpoint, "sections must be a list")
    data["sections"] = [
        _database_discovery_section(section, endpoint, index)
        for index, section in enumerate(sections, start=1)
    ]

    diagnostics = data.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        _raise_contract_error(endpoint, "diagnostics must be an object")
    _exact_keys(diagnostics, endpoint, {"source_snapshot_file", "target_snapshot_file"})
    _optional_text(diagnostics, endpoint, "source_snapshot_file")
    _optional_text(diagnostics, endpoint, "target_snapshot_file")
    data["diagnostics"] = dict(diagnostics)
    return data


def _database_discovery_snapshot(payload: Any, endpoint: str, label: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, f"{label} must be an object")
    _exact_keys(payload, endpoint, {"status", "connection_name", "captured_at", "migration_method", "summary", "message"})
    if payload.get("status") not in DATABASE_DISCOVERY_SNAPSHOT_STATUSES:
        _raise_contract_error(endpoint, f"{label}.status is invalid")
    _text(payload, endpoint, "connection_name")
    _optional_text(payload, endpoint, "captured_at")
    _text(payload, endpoint, "migration_method")
    _optional_text(payload, endpoint, "message")
    if not isinstance(payload.get("summary"), Mapping):
        _raise_contract_error(endpoint, f"{label}.summary must be an object")
    return dict(payload)


def _database_discovery_summary(payload: Any, endpoint: str) -> Dict[str, int]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, "summary must be an object")
    _exact_keys(payload, endpoint, {"readiness_issues", "differences", "source_only", "target_only"})
    result: Dict[str, int] = {}
    for key, value in payload.items():
        if not isinstance(value, int) or isinstance(value, bool):
            _raise_contract_error(endpoint, f"summary.{key} must be an integer")
        result[str(key)] = value
    return result


def _database_discovery_section(payload: Any, endpoint: str, index: int) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, f"sections[{index}] must be an object")
    _exact_keys(payload, endpoint, {"key", "label", "rows"})
    _text(payload, endpoint, "key")
    _text(payload, endpoint, "label")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        _raise_contract_error(endpoint, f"sections[{index}].rows must be a list")
    return {
        "key": payload["key"],
        "label": payload["label"],
        "rows": [
            _database_discovery_row(row, endpoint, f"sections[{index}].rows[{row_index}]")
            for row_index, row in enumerate(rows, start=1)
        ],
    }


def _database_discovery_row(payload: Any, endpoint: str, label: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, f"{label} must be an object")
    _exact_keys(payload, endpoint, {"key", "label", "source", "target", "status", "severity", "message", "guidance", "details"})
    _text(payload, endpoint, "key")
    _text(payload, endpoint, "label")
    if payload.get("status") not in DATABASE_DISCOVERY_STATUSES:
        _raise_contract_error(endpoint, f"{label}.status is invalid")
    _text(payload, endpoint, "severity", allow_empty=True)
    _text(payload, endpoint, "message", allow_empty=True)
    _text(payload, endpoint, "guidance", allow_empty=True)
    details = payload.get("details")
    if not isinstance(details, list):
        _raise_contract_error(endpoint, f"{label}.details must be a list")
    return {
        "key": payload["key"],
        "label": payload["label"],
        "source": _database_discovery_side(payload.get("source"), endpoint, f"{label}.source"),
        "target": _database_discovery_side(payload.get("target"), endpoint, f"{label}.target"),
        "status": payload["status"],
        "severity": payload["severity"],
        "message": payload["message"],
        "guidance": payload["guidance"],
        "details": [
            _database_discovery_detail(detail, endpoint, f"{label}.details[{detail_index}]")
            for detail_index, detail in enumerate(details, start=1)
        ],
    }


def _database_discovery_detail(payload: Any, endpoint: str, label: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, f"{label} must be an object")
    _exact_keys(payload, endpoint, {"side", "label", "format", "value"})
    _text(payload, endpoint, "side")
    _text(payload, endpoint, "label")
    _text(payload, endpoint, "format")
    if payload.get("side") not in {"source", "target"}:
        _raise_contract_error(endpoint, f"{label}.side is invalid")
    if payload.get("format") not in {"text", "sql", "json"}:
        _raise_contract_error(endpoint, f"{label}.format is invalid")
    if "value" not in payload:
        _raise_contract_error(endpoint, f"{label}.value is required")
    return {
        "side": payload["side"],
        "label": payload["label"],
        "format": payload["format"],
        "value": payload.get("value"),
    }


def _database_discovery_side(payload: Any, endpoint: str, label: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, f"{label} must be an object")
    _exact_keys(payload, endpoint, {"present", "value"})
    if not isinstance(payload.get("present"), bool):
        _raise_contract_error(endpoint, f"{label}.present must be a boolean")
    return {"present": payload["present"], "value": payload.get("value")}


def validate_jobs_dashboard_response(payload: Any) -> Dict[str, Any]:
    endpoint = "GET /jobs"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "source", "last_refreshed", "jobs", "warnings"})
    _status(data, endpoint)
    _text(data, endpoint, "source")
    if data.get("last_refreshed") is not None and not isinstance(data.get("last_refreshed"), str):
        _raise_contract_error(endpoint, "last_refreshed must be a string or null")
    if not isinstance(data.get("jobs"), list):
        _raise_contract_error(endpoint, "jobs must be a list")
    if not isinstance(data.get("warnings"), list):
        _raise_contract_error(endpoint, "warnings must be a list")
    for index, record in enumerate(data["jobs"], start=1):
        if (
            not isinstance(record, Mapping)
            or not isinstance(record.get("job"), Mapping)
            or not isinstance(record.get("inventory"), Mapping)
        ):
            _raise_contract_error(endpoint, f"jobs[{index}] must include job and inventory objects")
    return data


def validate_job_ids_response(payload: Any) -> List[str]:
    endpoint = "GET /jobs/ids"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"job_ids"})
    job_ids = data.get("job_ids")
    if not isinstance(job_ids, list) or not all(isinstance(job_id, str) for job_id in job_ids):
        _raise_contract_error(endpoint, "job_ids must be a list of strings")
    return list(job_ids)


def validate_job_query_response(payload: Any) -> Dict[str, Any]:
    endpoint = "GET /jobs/{jobid}"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "output"})
    _status(data, endpoint)
    _text(data, endpoint, "output", allow_empty=True)
    return data


def validate_run_job_response(payload: Any, *, dry_run: bool = False) -> Dict[str, Any]:
    endpoint = "POST /jobs"
    data = _object(payload, endpoint)
    if dry_run:
        _exact_keys(data, endpoint, {"status", "script_path", "command", "dry_run"})
        _status(data, endpoint, "planned")
        if data.get("dry_run") is not True:
            _raise_contract_error(endpoint, "dry_run must be true")
    else:
        _exact_keys(data, endpoint, {"status", "script_path", "output", "command", "job_id"})
        _status(data, endpoint, "submitted")
        _text(data, endpoint, "output", allow_empty=True)
        if data.get("job_id") is not None and not isinstance(data.get("job_id"), str):
            _raise_contract_error(endpoint, "job_id must be a string or null")
    _text(data, endpoint, "script_path")
    command = data.get("command")
    if not isinstance(command, list) or not all(isinstance(line, str) for line in command):
        _raise_contract_error(endpoint, "command must be a list of strings")
    return data


def validate_joblogs_response(payload: Any, *, expected_job_id: str) -> List[Dict[str, Any]]:
    endpoint = "GET /joblogs"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "job_id", "logs"})
    _status(data, endpoint)
    if data.get("job_id") != expected_job_id:
        _raise_contract_error(endpoint, f"job_id must be {expected_job_id}")
    logs = data.get("logs")
    if not isinstance(logs, list):
        _raise_contract_error(endpoint, "logs must be a list")
    for index, entry in enumerate(logs, start=1):
        if not isinstance(entry, Mapping):
            _raise_contract_error(endpoint, f"logs[{index}] must be an object")
        _exact_keys(entry, endpoint, {"name", "size_bytes", "modified_time"})
        _text(entry, endpoint, "name")
        _text(entry, endpoint, "modified_time")
        if not isinstance(entry.get("size_bytes"), int) or isinstance(entry.get("size_bytes"), bool):
            _raise_contract_error(endpoint, f"logs[{index}].size_bytes must be an integer")
    return [dict(entry) for entry in logs]


def validate_joblog_read_response(
    payload: Any,
    *,
    expected_job_id: str,
    expected_name: str,
) -> Dict[str, Any]:
    endpoint = "POST /joblogs/read"
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "job_id", "name", "content"})
    _status(data, endpoint)
    if data.get("job_id") != expected_job_id:
        _raise_contract_error(endpoint, f"job_id must be {expected_job_id}")
    if data.get("name") != expected_name:
        _raise_contract_error(endpoint, f"name must be {expected_name}")
    _text(data, endpoint, "content", allow_empty=True)
    return data


def validate_cli_command_response(payload: Any, *, endpoint: str) -> Dict[str, Any]:
    data = _object(payload, endpoint)
    _exact_keys(data, endpoint, {"status", "output"})
    _status(data, endpoint)
    _text(data, endpoint, "output", allow_empty=True)
    return data
