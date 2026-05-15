from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, Mapping, Tuple

from zdm_rules.catalog import get_profile


SELECT_WALLET = "-- Select wallet --"


@dataclass(frozen=True)
class JobFieldSpec:
    key: str
    state_key: str
    label: str
    control: str = "text"


def job_field_state_key(field: str) -> str:
    return f"runjob_{field}"


def profile_job_field_keys(migration_method: Any) -> Tuple[str, ...]:
    return tuple(get_profile(migration_method).common_job_field_keys())


def profile_job_section_field_specs(migration_method: Any, section: str) -> Tuple[JobFieldSpec, ...]:
    profile = get_profile(migration_method)
    return _job_field_specs(profile.job_section_field_keys(section))


def profile_job_field_specs(migration_method: Any) -> Tuple[JobFieldSpec, ...]:
    return _job_field_specs(profile_job_field_keys(migration_method))


def job_form_state_keys(migration_method: Any) -> Tuple[str, ...]:
    profile_keys = tuple(job_field_state_key(field) for field in profile_job_field_keys(migration_method))
    generic_keys = (
        "runjob_advisor_mode",
        "runjob_flow_control",
        "runjob_flow_phase",
        "runjob_genfixup",
        "runjob_ignore",
        "runjob_schedule_now",
        "runjob_schedule_text",
        "runjob_listphases",
        "runjob_custom_args",
    )
    return profile_keys + generic_keys


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


def _job_field_control(field: str) -> str:
    return "wallet" if field.lower().endswith("wallet") else "text"
