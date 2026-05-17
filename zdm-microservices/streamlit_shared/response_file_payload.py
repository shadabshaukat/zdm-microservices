from __future__ import annotations

from typing import Any, Dict, List, Mapping


def _normalize_method(value: Any) -> str:
    return str(value or "").strip().upper()


def _raise_contract_error(endpoint: str, detail: str) -> None:
    raise ValueError(f"{endpoint} API contract error: {detail}")


def _contract_object(payload: Any, endpoint: str) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, "expected JSON object")
    return dict(payload)


def _contract_exact_keys(payload: Mapping[str, Any], endpoint: str, expected_keys: set[str]) -> None:
    keys = {str(key) for key in payload.keys()}
    if keys == expected_keys:
        return
    parts: List[str] = []
    missing = sorted(expected_keys - keys)
    extra = sorted(keys - expected_keys)
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("unexpected " + ", ".join(extra))
    _raise_contract_error(endpoint, "; ".join(parts))


def _contract_status(payload: Mapping[str, Any], endpoint: str, expected_status: str) -> None:
    if payload.get("status") != expected_status:
        _raise_contract_error(endpoint, f"expected status {expected_status}")


def _contract_text(payload: Mapping[str, Any], endpoint: str, key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        _raise_contract_error(endpoint, f"{key} must be a non-empty string")
    return value


def _contract_project(payload: Mapping[str, Any], endpoint: str, key: str, expected_project: str) -> None:
    if payload.get(key) != expected_project:
        _raise_contract_error(endpoint, f"{key} must be {expected_project}")


def _contract_method(payload: Mapping[str, Any], endpoint: str, expected_method: str) -> None:
    if _normalize_method(payload.get("migration_method")) != _normalize_method(expected_method):
        _raise_contract_error(endpoint, f"migration_method must be {_normalize_method(expected_method)}")


def validate_responsefile_preview_response(
    payload: Any,
    *,
    expected_project: str,
    expected_method: str,
) -> List[str]:
    endpoint = "POST /responsefiles/preview"
    data = _contract_object(payload, endpoint)
    _contract_exact_keys(data, endpoint, {"status", "project", "filename", "lines", "migration_method"})
    _contract_status(data, endpoint, "planned")
    _contract_project(data, endpoint, "project", expected_project)
    _contract_method(data, endpoint, expected_method)
    if data.get("filename") != f"{expected_project}.rsp":
        _raise_contract_error(endpoint, f"filename must be {expected_project}.rsp")
    lines = data.get("lines")
    if not isinstance(lines, list) or not all(isinstance(line, str) for line in lines):
        _raise_contract_error(endpoint, "lines must be a list of strings")
    return list(lines)


def validate_responsefile_write_response(
    payload: Any,
    *,
    expected_project: str,
    expected_method: str,
) -> Dict[str, Any]:
    endpoint = "POST /responsefiles"
    data = _contract_object(payload, endpoint)
    _contract_exact_keys(
        data,
        endpoint,
        {"status", "message", "project", "path", "line_count", "sha256", "migration_method"},
    )
    _contract_status(data, endpoint, "success")
    _contract_project(data, endpoint, "project", expected_project)
    _contract_method(data, endpoint, expected_method)
    _contract_text(data, endpoint, "message")
    _contract_text(data, endpoint, "path")
    _contract_text(data, endpoint, "sha256")
    if not isinstance(data.get("line_count"), int) or isinstance(data.get("line_count"), bool):
        _raise_contract_error(endpoint, "line_count must be an integer")
    return data


def validate_responsefile_read_response(
    payload: Any,
    *,
    expected_project: str,
) -> Dict[str, Any]:
    endpoint = "GET /responsefiles/{project}"
    data = _contract_object(payload, endpoint)
    _contract_exact_keys(data, endpoint, {"status", "project", "path", "content"})
    _contract_status(data, endpoint, "success")
    _contract_project(data, endpoint, "project", expected_project)
    _contract_text(data, endpoint, "path")
    content = data.get("content")
    if not isinstance(content, str):
        _raise_contract_error(endpoint, "content must be a string")
    return data


def validate_responsefile_copy_response(
    payload: Any,
    *,
    expected_source_project: str,
    expected_target_project: str,
    expected_method: str,
) -> Dict[str, Any]:
    endpoint = "POST /responsefiles/copy"
    data = _contract_object(payload, endpoint)
    _contract_exact_keys(
        data,
        endpoint,
        {
            "status",
            "message",
            "project",
            "path",
            "line_count",
            "sha256",
            "migration_method",
            "source_project",
            "target_project",
        },
    )
    _contract_status(data, endpoint, "success")
    _contract_project(data, endpoint, "project", expected_target_project)
    _contract_project(data, endpoint, "source_project", expected_source_project)
    _contract_project(data, endpoint, "target_project", expected_target_project)
    _contract_method(data, endpoint, expected_method)
    _contract_text(data, endpoint, "message")
    _contract_text(data, endpoint, "path")
    _contract_text(data, endpoint, "sha256")
    if not isinstance(data.get("line_count"), int) or isinstance(data.get("line_count"), bool):
        _raise_contract_error(endpoint, "line_count must be an integer")
    return data
