from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from zdm_rules.catalog import get_profile


SELECT_WALLET = "-- Select wallet --"


@dataclass(frozen=True)
class JobFieldSpec:
    key: str
    state_key: str
    label: str
    control: str = "text"


@dataclass(frozen=True)
class JobRunControlSpec:
    key: str
    state_key: str
    label: str
    control: str = "text"
    options: Tuple[Any, ...] = ()
    default: Any = None
    help: str = ""
    now_state_key: str = ""
    text_state_key: str = ""
    now_label: str = ""
    text_label: str = ""
    text_help: str = ""
    now_value: str = "NOW"


def job_field_state_key(field: str) -> str:
    return f"runjob_{field}"


def job_run_control_state_key(field: str) -> str:
    return f"runjob_{field}"


def profile_job_field_keys(migration_method: Any) -> Tuple[str, ...]:
    return tuple(get_profile(migration_method).common_job_field_keys())


def profile_job_section_field_specs(migration_method: Any, section: str) -> Tuple[JobFieldSpec, ...]:
    profile = get_profile(migration_method)
    return _job_field_specs(profile.job_section_field_keys(section))


def profile_job_field_specs(migration_method: Any) -> Tuple[JobFieldSpec, ...]:
    return _job_field_specs(profile_job_field_keys(migration_method))


def profile_job_run_control_specs(migration_method: Any) -> Tuple[JobRunControlSpec, ...]:
    profile = get_profile(migration_method)
    return tuple(
        _job_run_control_spec(key, config)
        for key, config in profile.job_run_controls.items()
    )


def job_form_state_keys(migration_method: Any) -> Tuple[str, ...]:
    profile_keys = tuple(job_field_state_key(field) for field in profile_job_field_keys(migration_method))
    control_keys: List[str] = []
    for spec in profile_job_run_control_specs(migration_method):
        if spec.control == "schedule":
            control_keys.extend([spec.now_state_key, spec.text_state_key])
        else:
            control_keys.append(spec.state_key)
    return profile_keys + tuple(control_keys)


def collect_job_parameters(
    migration_method: Any,
    session_state: Mapping[str, Any],
    wallet_map: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    wallets = wallet_map or {}
    collected: Dict[str, Any] = {}
    for spec in profile_job_field_specs(migration_method):
        value = session_state.get(spec.state_key)
        if spec.control == "wallet":
            value = wallets.get(value, "") if value != SELECT_WALLET else ""
        collected[spec.key] = value
    return collected


def collect_job_run_controls(
    migration_method: Any,
    session_state: Mapping[str, Any],
) -> Dict[str, Any]:
    collected: Dict[str, Any] = {}
    for spec in profile_job_run_control_specs(migration_method):
        if spec.control == "schedule":
            if session_state.get(spec.now_state_key):
                collected[spec.key] = spec.now_value
            else:
                collected[spec.key] = _blank_to_none(session_state.get(spec.text_state_key))
            continue
        if spec.control == "checkbox":
            value = session_state.get(spec.state_key)
            collected[spec.key] = bool(spec.default) if value is None else bool(value)
            continue
        if spec.control == "multiselect":
            value = session_state.get(spec.state_key)
            collected[spec.key] = list(value) if isinstance(value, list) and value else None
            continue
        if spec.control == "textarea":
            collected[spec.key] = [
                line.strip()
                for line in str(session_state.get(spec.state_key) or "").splitlines()
                if line.strip()
            ]
            continue

        value = session_state.get(spec.state_key, spec.default)
        if spec.control == "select" and value in (None, ""):
            collected[spec.key] = None
        else:
            collected[spec.key] = _blank_to_none(value) if spec.control == "text" else value
    return collected


def job_run_control_state_updates(migration_method: Any, job: Mapping[str, Any]) -> Dict[str, Any]:
    updates: Dict[str, Any] = {}
    for spec in profile_job_run_control_specs(migration_method):
        value = job.get(spec.key)
        if spec.control == "schedule":
            schedule = str(value or "")
            is_now = schedule.upper() == spec.now_value.upper()
            updates[spec.now_state_key] = is_now
            updates[spec.text_state_key] = "" if is_now else schedule
            continue
        if spec.control == "checkbox":
            updates[spec.state_key] = bool(spec.default) if value is None else bool(value)
            continue
        if spec.control == "multiselect":
            updates[spec.state_key] = list(value) if isinstance(value, list) else []
            continue
        if spec.control == "textarea":
            if isinstance(value, list):
                updates[spec.state_key] = "\n".join(str(item) for item in value)
            else:
                updates[spec.state_key] = str(value or "")
            continue
        if value in (None, "") and spec.default not in (None, ""):
            value = spec.default
        updates[spec.state_key] = "" if value is None else value
    return updates


def wallet_name_for_path(path: Any, wallet_map: Mapping[str, str], default: str = SELECT_WALLET) -> str:
    path_s = str(path or "")
    if not path_s:
        return default
    for name, wallet_path in wallet_map.items():
        if wallet_path == path_s:
            return name
    return default


def _job_field_specs(fields: Iterable[str]) -> Tuple[JobFieldSpec, ...]:
    return tuple(
        JobFieldSpec(
            key=str(field),
            state_key=job_field_state_key(str(field)),
            label=f"-{field}",
            control=_job_field_control(str(field)),
        )
        for field in fields
    )


def _job_run_control_spec(key: str, config: Mapping[str, Any]) -> JobRunControlSpec:
    control = str(config.get("control") or "text")
    state_key = job_run_control_state_key(key)
    return JobRunControlSpec(
        key=str(key),
        state_key=state_key,
        label=str(config.get("label") or str(key).replace("_", " ").title()),
        control=control,
        options=tuple(config.get("options") or ()),
        default=config.get("default"),
        help=str(config.get("help") or ""),
        now_state_key=f"{state_key}_now" if control == "schedule" else "",
        text_state_key=f"{state_key}_text" if control == "schedule" else "",
        now_label=str(config.get("now_label") or "Now"),
        text_label=str(config.get("text_label") or str(config.get("label") or key)),
        text_help=str(config.get("text_help") or ""),
        now_value=str(config.get("now_value") or "NOW"),
    )


def _job_field_control(field: str) -> str:
    return "wallet" if field.lower().endswith("wallet") else "text"


def _blank_to_none(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return value
