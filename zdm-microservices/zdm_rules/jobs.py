from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from zdm_rules.catalog import MigrationProfile, normalize_method
from zdm_rules.common import nonblank


SUPPORTED_RUN_TYPES = ("EVAL", "MIGRATE")
SUPPORTED_JOB_METHODS = {"OFFLINE_LOGICAL"}


def job_method_supported(method: Any) -> bool:
    return normalize_method(method) in SUPPORTED_JOB_METHODS


def build_migrate_command(profile: MigrationProfile, params: Mapping[str, Any]) -> List[str]:
    _validate_migrate_params(profile, params)

    run_type = normalize_method(params.get("run_type"))
    job_parameters = _job_parameters(params.get("job_parameters"))
    lines = ["#!/bin/bash", "$ZDM_HOME/bin/zdmcli migrate database \\"]

    def add(flag: str, value: Optional[Any]) -> None:
        if value:
            lines.append(f"    {flag} {value} \\")

    add("-rsp", params.get("rsp"))
    for field in profile.common_job_field_keys():
        add(f"-{field}", job_parameters.get(field))

    advisor = normalize_method(params.get("advisor_mode") or "NONE")
    if advisor == "ADVISOR":
        lines.append("    -advisor \\")
    elif advisor == "IGNORE_ADVISOR":
        lines.append("    -ignoreadvisor \\")
    elif advisor == "SKIP_ADVISOR":
        lines.append("    -skipadvisor \\")

    if advisor != "ADVISOR" and run_type == "EVAL":
        lines.append("    -eval \\")

    if params.get("genfixup"):
        lines.append(f"    -genfixup {params.get('genfixup')} \\")

    ignore_list = params.get("ignore") or []
    if ignore_list:
        if "ALL" in ignore_list:
            lines.append("    -ignore ALL \\")
        else:
            lines.append(f"    -ignore {','.join(ignore_list)} \\")

    if params.get("schedule"):
        lines.append(f"    -schedule {params.get('schedule')} \\")

    if params.get("listphases"):
        lines.append("    -listphases \\")

    flow = normalize_method(params.get("flow_control") or "NONE")
    phase = params.get("flow_phase")
    if flow in ("PAUSE_AFTER", "STOP_AFTER"):
        flag = "-pauseafter" if flow == "PAUSE_AFTER" else "-stopafter"
        lines.append(f"    {flag} {phase} \\")
    else:
        default_pause = _default_pause_after(profile, params, run_type)
        if default_pause:
            lines.append(f"    -pauseafter {default_pause} \\")

    if params.get("custom_args"):
        for arg in params.get("custom_args") or []:
            a = str(arg).strip()
            if a:
                lines.append(f"    {a} \\")

    if lines[-1].endswith("\\"):
        lines[-1] = lines[-1][:-1]

    return lines


def _validate_migrate_params(profile: MigrationProfile, params: Mapping[str, Any]) -> None:
    if not job_method_supported(profile.method):
        raise ValueError(f"{profile.method} job submission is not supported yet")

    run_type = normalize_method(params.get("run_type"))
    if run_type not in SUPPORTED_RUN_TYPES:
        raise ValueError("run_type must be EVAL or MIGRATE")

    if not nonblank(params.get("rsp")):
        raise ValueError("rsp is required")

    flow_control = normalize_method(params.get("flow_control") or "NONE")
    if flow_control in ("PAUSE_AFTER", "STOP_AFTER") and not nonblank(params.get("flow_phase")):
        raise ValueError(f"{flow_control.lower()} requires flow_phase")
    _validate_job_parameters(profile, params)


def _default_pause_after(profile: MigrationProfile, params: Mapping[str, Any], run_type: str) -> str:
    response_file_values = params.get("response_file_values") or {}
    if not isinstance(response_file_values, Mapping):
        response_file_values = {}
    medium = (
        response_file_values.get("DATA_TRANSFER_MEDIUM")
        or params.get("data_transfer_medium")
        or ""
    )
    defaults = profile.run_defaults(medium, run_type)
    return defaults.get("pauseafter", "")


def _job_parameters(value: Any) -> Dict[str, Any]:
    if value in (None, ""):
        return {}
    if not isinstance(value, Mapping):
        raise ValueError("job_parameters must be an object")
    return {str(key): val for key, val in value.items()}


def _validate_job_parameters(profile: MigrationProfile, params: Mapping[str, Any]) -> None:
    job_parameters = _job_parameters(params.get("job_parameters"))
    allowed = set(profile.common_job_field_keys())
    unknown = sorted(key for key in job_parameters if key not in allowed)
    if unknown:
        raise ValueError(
            f"Unsupported job parameter for {profile.method}: {', '.join(unknown)}"
        )
