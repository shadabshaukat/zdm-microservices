from __future__ import annotations

from typing import Any, Dict, Mapping


JOB_PAYLOAD_FIELDS = [
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
]
SAVED_JOB_RECORD_FIELDS = frozenset(["name", *JOB_PAYLOAD_FIELDS])
SAVED_JOB_SAVE_RESPONSE_FIELDS = frozenset(["status", "message", "job"])
SAVED_JOB_DELETE_RESPONSE_FIELDS = frozenset(["status", "message"])
SAVED_JOB_COPY_RESPONSE_FIELDS = frozenset(
    ["status", "message", "source_project", "target_project", "migration_method", "run_type", "job"]
)
SAVED_JOB_RUN_TYPES = {"EVAL", "MIGRATE"}


def canonical_saved_job_name(project: Any, run_type: Any) -> str:
    return f"{str(project or '').strip()}_{str(run_type or '').strip().lower()}"


def compact_job_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    cleaned = dict(payload)
    job_parameters = cleaned.get("job_parameters") or {}
    if isinstance(job_parameters, Mapping):
        compacted_params = {
            str(key): value
            for key, value in job_parameters.items()
            if value not in (None, "", [])
        }
        cleaned["job_parameters"] = compacted_params
    return cleaned


def validate_saved_job_record(
    record_name: Any,
    job: Any,
    *,
    enforce_key_match: bool = True,
) -> Dict[str, Any]:
    name = str(record_name or "").strip()
    if not name:
        raise ValueError("Saved job data is invalid: saved job key must be a non-empty string.")
    if not isinstance(job, Mapping):
        raise ValueError(f"Saved job data is invalid: saved job '{name}' must be an object.")

    keys = set(str(key) for key in job.keys())
    if keys != SAVED_JOB_RECORD_FIELDS:
        missing = sorted(SAVED_JOB_RECORD_FIELDS - keys)
        extra = sorted(keys - SAVED_JOB_RECORD_FIELDS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(
            f"Saved job data is invalid: saved job '{name}' has invalid fields ({'; '.join(details)})."
        )

    job_name = str(job.get("name") or "").strip()
    project = str(job.get("project") or "").strip()
    run_type = str(job.get("run_type") or "").strip().upper()
    if not job_name:
        raise ValueError(f"Saved job data is invalid: saved job '{name}' is missing name.")
    if enforce_key_match and job_name != name:
        raise ValueError(
            f"Saved job data is invalid: saved job key '{name}' does not match record name '{job_name}'."
        )
    if not project:
        raise ValueError(f"Saved job data is invalid: saved job '{name}' is missing project.")
    if run_type not in SAVED_JOB_RUN_TYPES:
        raise ValueError(f"Saved job data is invalid: saved job '{name}' has invalid run_type.")
    expected_name = canonical_saved_job_name(project, run_type)
    if job_name != expected_name:
        raise ValueError(
            f"Saved job data is invalid: saved job '{name}' must be named '{expected_name}'."
        )
    if not isinstance(job.get("job_parameters"), Mapping):
        raise ValueError(
            f"Saved job data is invalid: saved job '{name}' job_parameters must be an object."
        )

    ignore = job.get("ignore")
    if ignore is not None and not isinstance(ignore, list):
        raise ValueError(f"Saved job data is invalid: saved job '{name}' ignore must be a list.")
    custom_args = job.get("custom_args")
    if custom_args is not None and not isinstance(custom_args, list):
        raise ValueError(f"Saved job data is invalid: saved job '{name}' custom_args must be a list.")
    listphases = job.get("listphases")
    if listphases is not None and not isinstance(listphases, bool):
        raise ValueError(f"Saved job data is invalid: saved job '{name}' listphases must be a boolean.")

    return dict(job)


def validate_saved_jobs_response(payload: Any) -> Dict[str, Dict[str, Any]]:
    if not isinstance(payload, Mapping):
        raise ValueError("Saved job data is invalid: expected an object keyed by saved job name.")
    return {
        str(name): validate_saved_job_record(name, job)
        for name, job in payload.items()
    }


def validate_saved_job_save_response(payload: Any, expected_name: Any) -> Dict[str, Any]:
    expected_name_s = str(expected_name or "").strip()
    if not isinstance(payload, Mapping):
        raise ValueError("Saved job save response is invalid: expected an object.")
    keys = set(str(key) for key in payload.keys())
    if keys != SAVED_JOB_SAVE_RESPONSE_FIELDS:
        missing = sorted(SAVED_JOB_SAVE_RESPONSE_FIELDS - keys)
        extra = sorted(keys - SAVED_JOB_SAVE_RESPONSE_FIELDS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(f"Saved job save response is invalid: invalid fields ({'; '.join(details)}).")
    if payload.get("status") != "success":
        raise ValueError("Saved job save response is invalid: status must be success.")
    return validate_saved_job_record(expected_name_s, payload.get("job"))


def validate_saved_job_delete_response(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Saved job delete response is invalid: expected an object.")
    keys = set(str(key) for key in payload.keys())
    if keys != SAVED_JOB_DELETE_RESPONSE_FIELDS:
        missing = sorted(SAVED_JOB_DELETE_RESPONSE_FIELDS - keys)
        extra = sorted(keys - SAVED_JOB_DELETE_RESPONSE_FIELDS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(f"Saved job delete response is invalid: invalid fields ({'; '.join(details)}).")
    if payload.get("status") != "success":
        raise ValueError("Saved job delete response is invalid: status must be success.")
    if not isinstance(payload.get("message"), str) or not payload.get("message"):
        raise ValueError("Saved job delete response is invalid: message must be a non-empty string.")
    return dict(payload)


def validate_saved_job_copy_response(
    payload: Any,
    *,
    expected_source_project: str,
    expected_target_project: str,
    expected_method: str,
    expected_run_type: str,
    expected_name: str,
) -> Dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise ValueError("Saved job copy response is invalid: expected an object.")
    keys = set(str(key) for key in payload.keys())
    if keys != SAVED_JOB_COPY_RESPONSE_FIELDS:
        missing = sorted(SAVED_JOB_COPY_RESPONSE_FIELDS - keys)
        extra = sorted(keys - SAVED_JOB_COPY_RESPONSE_FIELDS)
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if extra:
            details.append("unexpected " + ", ".join(extra))
        raise ValueError(f"Saved job copy response is invalid: invalid fields ({'; '.join(details)}).")
    if payload.get("status") != "success":
        raise ValueError("Saved job copy response is invalid: status must be success.")
    if payload.get("source_project") != expected_source_project:
        raise ValueError("Saved job copy response is invalid: source_project mismatch.")
    if payload.get("target_project") != expected_target_project:
        raise ValueError("Saved job copy response is invalid: target_project mismatch.")
    if str(payload.get("migration_method") or "").strip().upper() != str(expected_method or "").strip().upper():
        raise ValueError("Saved job copy response is invalid: migration_method mismatch.")
    if str(payload.get("run_type") or "").strip().upper() != str(expected_run_type or "").strip().upper():
        raise ValueError("Saved job copy response is invalid: run_type mismatch.")
    copied_job = validate_saved_job_record(expected_name, payload.get("job"))
    return {**dict(payload), "job": copied_job}


def job_payload_from_saved_job(job: Mapping[str, Any], dry_run: bool = False) -> Dict[str, Any]:
    validated = validate_saved_job_record(
        job.get("name") if isinstance(job, Mapping) else "",
        job,
        enforce_key_match=False,
    )
    payload = {field: validated.get(field) for field in JOB_PAYLOAD_FIELDS}
    if dry_run:
        payload["dry_run"] = True
    return compact_job_payload(payload)
