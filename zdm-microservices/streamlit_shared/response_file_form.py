from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Mapping, Tuple

from zdm_rules.catalog import MigrationProfile, get_profile, load_profiles
from zdm_rules.environments import (
    project_environment_response_values,
    project_rule_group_values,
)
from zdm_rules.responsefile import response_file_supported


SELECT_PROJECT = "-- Select project --"
SELECT_WALLET = "-- Select wallet --"

ACTIVE_PROFILES = load_profiles()
METHOD_OPTIONS_BY_TYPE: Dict[str, List[str]] = {}
for profile in ACTIVE_PROFILES.values():
    METHOD_OPTIONS_BY_TYPE.setdefault(profile.migration_type, []).append(profile.method)
MIGRATION_TYPE_OPTIONS = list(METHOD_OPTIONS_BY_TYPE)
REMAP_TYPE_OPTIONS = ["REMAP_TABLESPACE", "REMAP_SCHEMA", "REMAP_DATAFILE"]

FIELD_STATE_KEY_OVERRIDES = {
    "DATAPUMPSETTINGS_METADATAREMAPS": "rf_remap_table",
    "INCLUDEOBJECTS": "rf_include_schemas",
}
FIELD_HELP_KEYS = {
    "WALLET_TARGETADMIN": "WALLET_TARGETCONTAINER",
    "INCLUDEOBJECTS": "include_schemas",
}


@dataclass(frozen=True)
class MediumOption:
    value: str
    label: str
    enabled: bool
    disabled_reason: str = ""


@dataclass(frozen=True)
class FieldSpec:
    key: str
    state_key: str
    label: str
    control: str = "text"
    required: bool = False
    options: Tuple[Any, ...] = ()
    default: Any = ""
    min_value: Any = None
    max_value: Any = None
    step: Any = None
    help_key: str = ""


def _profile_for_method(method: Any):
    return get_profile(method)


def _field_spec(
    key: str,
    profile: MigrationProfile,
    required_context: Mapping[str, Any] | None = None,
) -> FieldSpec:
    config = profile.field(key)
    if not config:
        return FieldSpec(
            key=key,
            state_key=_field_state_key(key),
            label=_field_label(key, config),
            required=profile.field_required_hint(key, required_context),
        )
    return FieldSpec(
        key=key,
        state_key=_field_state_key(key),
        label=_field_label(key, config),
        control=str(config.get("control") or "text"),
        required=profile.field_required_hint(key, required_context),
        options=tuple(config.get("options") or ()),
        default=config.get("default", ""),
        min_value=config.get("min_value"),
        max_value=config.get("max_value"),
        step=config.get("step"),
        help_key=FIELD_HELP_KEYS.get(key, ""),
    )


def _field_specs(
    keys: Iterable[str],
    profile: MigrationProfile,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    return tuple(_field_spec(key, profile, required_context) for key in keys)


def _section_field_specs(
    section: str,
    profile: MigrationProfile,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    return _field_specs(profile.section_field_keys(section, required_context), profile, required_context)


def profile_section_field_specs(
    migration_method: Any,
    section: str,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    profile = _profile_for_method(migration_method)
    return _section_field_specs(section, profile, required_context)


def profile_medium_field_specs(
    migration_method: Any,
    medium: Any,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    profile = _profile_for_method(migration_method)
    context = required_context or {"DATA_TRANSFER_MEDIUM": normalize_method(medium)}
    return _field_specs(profile.medium_field_keys(medium, context=context), profile, context)


def profile_medium_unsectioned_field_specs(
    migration_method: Any,
    medium: Any,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    profile = _profile_for_method(migration_method)
    context = required_context or {"DATA_TRANSFER_MEDIUM": normalize_method(medium)}
    return _field_specs(profile.medium_unsectioned_field_keys(medium, context=context), profile, context)


def profile_medium_section_field_specs(
    migration_method: Any,
    medium: Any,
    section: str,
    required_context: Mapping[str, Any] | None = None,
) -> Tuple[FieldSpec, ...]:
    profile = _profile_for_method(migration_method)
    context = required_context or {"DATA_TRANSFER_MEDIUM": normalize_method(medium)}
    return _field_specs(profile.medium_section_field_keys(medium, section, context=context), profile, context)


def profile_response_layout(migration_method: Any) -> List[Dict[str, Any]]:
    profile = _profile_for_method(migration_method)
    return profile.response_layout()


def profile_section_label(migration_method: Any, section: Any) -> str:
    profile = _profile_for_method(migration_method)
    return profile.section_label(str(section))


def profile_medium_section_names(migration_method: Any, medium: Any) -> List[str]:
    profile = _profile_for_method(migration_method)
    return profile.medium_section_names(medium)


def profile_medium_fields_title(migration_method: Any) -> str:
    profile = _profile_for_method(migration_method)
    return profile.medium_fields_title()


def profile_additional_default_rows(migration_method: Any) -> List[Dict[str, str]]:
    profile = _profile_for_method(migration_method)
    return profile.additional_default_rows()


def _field_state_key(key: str) -> str:
    key_s = str(key)
    return FIELD_STATE_KEY_OVERRIDES.get(key_s, "rf_" + key_s.lower())


def _field_label(key: str, config: Mapping[str, Any]) -> str:
    label = config.get("label")
    if label:
        return str(label)
    return str(key).replace("_", " ").title()


def field_spec_keys(specs: Iterable[FieldSpec]) -> List[str]:
    return [spec.key for spec in specs]


RSP_STATE_MAPPING: Dict[str, str] = {}
for profile in ACTIVE_PROFILES.values():
    RSP_STATE_MAPPING.update(
        {
            key: _field_state_key(key)
            for key in profile.fields.keys()
        }
    )
RSP_STATE_MAPPING["DATA_TRANSFER_MEDIUM"] = "rf_medium"
RSP_STATE_MAPPING["MIGRATION_METHOD"] = "rf_migration_method"

RSP_KNOWN_RESPONSE_KEYS = {"DATA_TRANSFER_MEDIUM", "MIGRATION_METHOD"}
for profile in ACTIVE_PROFILES.values():
    RSP_KNOWN_RESPONSE_KEYS.update(profile.all_response_field_keys())

RSP_WALLET_STATE_MAPPING: Dict[str, str] = {}
for profile in ACTIVE_PROFILES.values():
    for key, config in profile.fields.items():
        if not isinstance(config, Mapping):
            continue
        if config.get("control") == "wallet":
            RSP_WALLET_STATE_MAPPING[str(key)] = _field_state_key(str(key))


def normalize_method(value: Any) -> str:
    return str(value or "").strip().upper()


def migration_method_label(value: Any) -> str:
    normalized = normalize_method(value).replace("-", "_").replace(" ", "_")
    labels = {
        "OFFLINE_LOGICAL": "Logical Offline",
        "ONLINE_LOGICAL": "Logical Online",
        "OFFLINE_PHYSICAL": "Physical Offline",
        "ONLINE_PHYSICAL": "Physical Online",
    }
    if normalized in labels:
        return labels[normalized]
    if normalized:
        return normalized.replace("_", " ").title()
    return "Unknown"


def active_migration_method_options() -> Dict[str, str]:
    return {migration_method_label(profile.method): profile.method for profile in ACTIVE_PROFILES.values()}


def method_options(migration_type: str) -> List[str]:
    return list(METHOD_OPTIONS_BY_TYPE.get(migration_type, []))


def default_method(migration_type: str) -> str:
    options = method_options(migration_type)
    return options[0] if options else ""


def migration_type_for_method(migration_method: Any) -> str:
    return str(_profile_for_method(migration_method).migration_type)


def response_method_supported(migration_method: Any) -> bool:
    return response_file_supported(migration_method)


def migration_decision_input_values_from_project(
    migration_method: Any,
    project: Any,
    connections: Any,
) -> Dict[str, Any]:
    profile = _profile_for_method(migration_method)
    values: Dict[str, Any] = {}
    rule_group_refs: Dict[str, Any] = {}
    for name, config in profile.decision_input_controls.items():
        if "default" in config:
            values[str(name)] = config.get("default")
        if "from_rule_group" in config:
            rule_group_refs[str(name)] = config.get("from_rule_group")
    if rule_group_refs:
        values.update(project_rule_group_values(project, connections, rule_group_refs))
    return values


def migration_decision_input_summary_parts(
    migration_method: Any,
    decision_input_values: Mapping[str, Any],
) -> List[str]:
    profile = _profile_for_method(migration_method)
    parts: List[str] = []
    for name in profile.decision_input_controls.keys():
        value = decision_input_values.get(str(name))
        if value in (None, ""):
            continue
        parts.append(migration_decision_input_option_label(migration_method, str(name), value))
    return parts


def migration_decision_input_option_label(migration_method: Any, name: str, option: Any) -> str:
    profile = _profile_for_method(migration_method)
    config = profile.decision_input_control(name)
    labels = config.get("labels") or {}
    if isinstance(labels, Mapping):
        return str(labels.get(normalize_method(option)) or labels.get(option) or option)
    return str(option)


def migration_medium_options(
    migration_method: Any,
    context: Mapping[str, Any] | None = None,
) -> List[MediumOption]:
    profile = _profile_for_method(migration_method)
    options: List[MediumOption] = []
    for option in profile.medium_options(context or {}):
        config = profile.medium(option.value)
        options.append(
            MediumOption(
                value=option.value,
                label=str(config.get("label") or option.value),
                enabled=option.enabled,
                disabled_reason=str(config.get("unavailable_hint") or ""),
            )
        )
    return options


def migration_medium_values(migration_method: Any, context: Mapping[str, Any] | None = None) -> List[str]:
    return [option.value for option in migration_medium_options(migration_method, context) if option.enabled]


def migration_medium_guidance(migration_method: Any, medium: Any) -> str:
    profile = _profile_for_method(migration_method)
    config = profile.medium(medium)
    return str(config.get("hint") or "")


def same_method_copy_candidates(
    projects: Any,
    current_project: str,
    selected_migration_method: str,
) -> List[str]:
    selected = normalize_method(selected_migration_method)
    if not isinstance(projects, dict) or not selected:
        return []

    candidates: List[str] = []
    for candidate_name, candidate_project in projects.items():
        if candidate_name == current_project or not isinstance(candidate_project, dict):
            continue
        candidate_method = normalize_method(candidate_project.get("migration_method"))
        if candidate_method == selected:
            candidates.append(candidate_name)
    return candidates


def parse_rsp_content(text: str) -> Dict[str, Any]:
    parsed: Dict[str, Any] = {"kv": {}, "include_schemas": [], "remaps": []}
    for line in str(text or "").splitlines():
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
            parts: Dict[str, str] = {}
            for segment in val.split(","):
                if ":" in segment:
                    part_key, part_value = segment.split(":", 1)
                    parts[part_key.strip()] = part_value.strip()
            if parts.get("type") and parts.get("oldValue") and parts.get("newValue"):
                parsed["remaps"].append(
                    {
                        "type": parts["type"],
                        "oldValue": parts["oldValue"],
                        "newValue": parts["newValue"],
                    }
                )
            continue
        parsed["kv"][key] = val
    return parsed


def state_updates_from_rsp_content(content: str, wallet_map: Mapping[str, str]) -> Dict[str, Any]:
    parsed = parse_rsp_content(content)
    kv = parsed.get("kv", {})
    updates: Dict[str, Any] = {}

    for key, state_key in RSP_STATE_MAPPING.items():
        if key not in kv:
            continue
        if key in RSP_WALLET_STATE_MAPPING:
            continue
        value: Any = kv[key]
        if key == "SOURCEDATABASE_CONNECTIONDETAILS_PORT":
            try:
                value = int(value)
            except Exception:
                pass
        updates[state_key] = value

    updates["rf_include_schemas"] = "\n".join(parsed.get("include_schemas") or [])

    remaps = parsed.get("remaps") or []
    if remaps:
        updates["rf_remap_prefill"] = remaps

    additional_rows = [
        {"key": key, "value": value}
        for key, value in kv.items()
        if key not in RSP_KNOWN_RESPONSE_KEYS
    ]
    if additional_rows:
        updates["rf_additional_prefill"] = additional_rows

    path_to_wallet = {path: name for name, path in wallet_map.items()}
    wallet_errors: List[Dict[str, str]] = []
    for key, state_key in RSP_WALLET_STATE_MAPPING.items():
        wallet_path = kv.get(key)
        if not wallet_path:
            continue
        if wallet_path in path_to_wallet:
            updates[state_key] = path_to_wallet[wallet_path]
            continue
        wallet_errors.append(
            {
                "field": key,
                "path": str(wallet_path),
                "state_key": state_key,
            }
        )
    if wallet_errors:
        updates["rf_rsp_wallet_contract_errors"] = wallet_errors

    return updates


def include_schemas_from_text(raw_text: str) -> List[str]:
    return [schema.strip() for schema in str(raw_text or "").splitlines() if schema.strip()]


def collect_metadata_remaps(rows: Any) -> List[List[str]]:
    remaps: List[List[str]] = []
    for row in _table_rows(rows):
        remap_type = _cell_text(row.get("type"))
        old_value = _cell_text(row.get("oldValue"))
        new_value = _cell_text(row.get("newValue"))
        if remap_type and old_value and new_value:
            remaps.append([remap_type, old_value, new_value])
    return remaps


def collect_additional_parameters(rows: Any) -> Dict[str, str]:
    additional: Dict[str, str] = {}
    for row in _table_rows(rows):
        key = _cell_text(row.get("key"))
        value = _cell_text(row.get("value"))
        if key:
            additional[key] = value
    return additional


def build_responsefile_payload(
    *,
    project: str,
    migration_type: str,
    migration_method: str,
    medium: str,
    values: Mapping[str, Any],
    remaps: List[List[str]],
    additional: Mapping[str, str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "project": project,
        "filename": project,
        "MIGRATION_METHOD": migration_method,
        "DATA_TRANSFER_MEDIUM": medium,
    }

    profile = _profile_for_method(migration_method)
    payload.update(profile.decision_input_response_values(values))
    _copy_present_keys(payload, values, profile.decision_input_response_field_keys())
    _copy_present_keys(payload, values, profile.derived_response_field_keys())
    active_context = {
        **values,
        "MIGRATION_METHOD": migration_method,
        "DATA_TRANSFER_MEDIUM": medium,
    }
    common_keys = [
        key
        for key in profile.common_response_field_keys(active_context)
        if key not in {"DATAPUMPSETTINGS_METADATAREMAPS", "INCLUDEOBJECTS"}
    ]
    _copy_profile_keys(profile, payload, values, common_keys)
    _copy_profile_keys(profile, payload, values, profile.medium_field_keys(medium, context=active_context))
    include_schemas = values.get("include_schemas")
    if include_schemas:
        payload["include_schemas"] = include_schemas

    if remaps:
        payload["DATAPUMPSETTINGS_METADATAREMAPS"] = remaps
    if additional:
        payload["additional"] = dict(additional)
    return payload


def _copy_profile_keys(
    profile: MigrationProfile,
    target: Dict[str, Any],
    values: Mapping[str, Any],
    keys: Iterable[str],
) -> None:
    context = {**values, **target}
    for key in keys:
        value = values.get(key)
        if profile.should_write_response_value(key, value, context):
            target[key] = value


def _copy_present_keys(target: Dict[str, Any], values: Mapping[str, Any], keys: Iterable[str]) -> None:
    for key in keys:
        if key in values:
            target[key] = values.get(key)


def _table_rows(rows: Any) -> Iterable[Mapping[str, Any]]:
    if rows is None:
        return []
    if hasattr(rows, "iterrows"):
        return [row for _, row in rows.iterrows()]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, Mapping)]
    return []


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value != value:
        return ""
    return str(value).strip()
