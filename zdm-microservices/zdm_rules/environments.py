from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

DB_CONNECTION_ROLE_OPTIONS = ("source", "target")
ENVIRONMENTS_PATH = Path(__file__).resolve().parent / "definitions" / "catalogs" / "environments.yaml"
ENVIRONMENT_REQUIRED_KEYS = {"display", "supports", "rule_groups", "zdm"}
ENVIRONMENT_OPTIONAL_KEYS = {"notes"}
MIGRATION_METHOD_KEYS = {"OFFLINE_LOGICAL", "ONLINE_LOGICAL", "OFFLINE_PHYSICAL", "ONLINE_PHYSICAL"}
RULE_GROUP_FAMILIES = {"logical", "physical"}
ZDM_MAPPING_KEYS = {"logical_source", "logical_target", "physical_target"}


def load_connection_environments(path: Path = ENVIRONMENTS_PATH) -> dict[str, dict[str, Any]]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path.name} must define a mapping")
    environments = raw.get("environments")
    if not isinstance(environments, dict):
        raise RuntimeError(f"{path.name} must define an environments mapping")
    if not environments:
        raise RuntimeError(f"{path.name} must contain at least one environment")
    if raw.get("schema_version") != 1:
        raise RuntimeError(f"{path.name} schema_version must be 1")
    if not str(raw.get("zdm_version") or "").strip():
        raise RuntimeError(f"{path.name} zdm_version is required")

    validated: dict[str, dict[str, Any]] = {}
    for key, value in environments.items():
        env_key = str(key)
        validated[env_key] = _validate_environment(env_key, value)
    return validated


def normalize_connection_role(value: Any) -> str:
    role = str(value or "").strip().lower()
    return role if role in DB_CONNECTION_ROLE_OPTIONS else ""


def normalize_connection_type(value: Any) -> str:
    return str(value or "").strip().upper()


def connection_environment(value: Any) -> dict[str, Any]:
    env = CONNECTION_ENVIRONMENTS.get(normalize_connection_type(value))
    return env if isinstance(env, dict) else {}


def db_connection_role_label(value: Any) -> str:
    role = normalize_connection_role(value)
    return role.title() if role else str(value or "")


def db_connection_type_label(value: Any) -> str:
    env = connection_environment(value)
    display = env.get("display") if isinstance(env.get("display"), dict) else {}
    name = str(display.get("name") or value or "")
    return name


def db_connection_type_options_for_role(role: Any) -> tuple[str, ...]:
    normalized_role = normalize_connection_role(role)
    if not normalized_role:
        return ()

    options = []
    for key, env in CONNECTION_ENVIRONMENTS.items():
        if db_connection_type_supports_role(key, normalized_role):
            options.append(key)
    return tuple(options)


def db_connection_type_supports_role(value: Any, role: Any) -> bool:
    normalized_role = normalize_connection_role(role)
    if not normalized_role:
        return False

    env = connection_environment(value)
    support = env.get("supports") if isinstance(env, dict) else {}
    role_support = support.get(normalized_role) if isinstance(support, dict) else {}
    if not isinstance(role_support, list):
        return False
    return bool(role_support)


def db_connection_type_supports_method(value: Any, role: Any, migration_method: Any) -> bool:
    normalized_role = normalize_connection_role(role)
    method = str(migration_method or "").strip().upper()
    if not normalized_role or not method:
        return False

    env = connection_environment(value)
    support = env.get("supports") if isinstance(env, dict) else {}
    role_support = support.get(normalized_role) if isinstance(support, dict) else []
    if not isinstance(role_support, list):
        return False
    return method in {str(item).strip().upper() for item in role_support}


def db_connection_names_for_role(connections: Any, role: Any) -> tuple[str, ...]:
    normalized_role = normalize_connection_role(role)
    if not normalized_role or not isinstance(connections, dict):
        return ()

    names = []
    for name, info in connections.items():
        if not isinstance(info, dict):
            continue
        if normalize_connection_role(info.get("connection_role")) == normalized_role:
            names.append(str(name))
    return tuple(names)


def db_connection_type_notes(value: Any) -> tuple[str, ...]:
    env = connection_environment(value)
    notes = env.get("notes") or []
    if not isinstance(notes, list):
        return ()
    return tuple(str(note) for note in notes if str(note or "").strip())


def db_connection_zdm_values(value: Any, role: Any, migration_method: Any) -> dict[str, str]:
    env = connection_environment(value)
    if not env:
        return {}

    mapping_name = _zdm_mapping_name_for_role_method(role, migration_method)

    zdm = env.get("zdm") if isinstance(env.get("zdm"), dict) else {}
    mapping = zdm.get(mapping_name) if mapping_name else {}
    if not isinstance(mapping, Mapping):
        return {}
    return {
        str(key): str(value)
        for key, value in mapping.items()
        if value not in (None, "")
    }


def db_connection_zdm_keys_for_role(role: Any, migration_method: Any) -> tuple[str, ...]:
    mapping_name = _zdm_mapping_name_for_role_method(role, migration_method)
    if not mapping_name:
        return ()

    keys: set[str] = set()
    for env in CONNECTION_ENVIRONMENTS.values():
        zdm = env.get("zdm") if isinstance(env.get("zdm"), Mapping) else {}
        mapping = zdm.get(mapping_name) if isinstance(zdm.get(mapping_name), Mapping) else {}
        keys.update(str(key) for key in mapping.keys())
    return tuple(sorted(keys))


def db_connection_rule_group(value: Any, rule_group_ref: Any) -> str:
    env = connection_environment(value)
    if not env:
        return ""
    family, role = _parse_rule_group_ref(rule_group_ref)
    rule_groups = env.get("rule_groups") if isinstance(env.get("rule_groups"), dict) else {}
    family_groups = rule_groups.get(family) if isinstance(rule_groups.get(family), dict) else {}
    return str(family_groups.get(role) or "").strip()


def project_environment_response_values(
    project: Any,
    connections: Any,
    migration_method: Any,
) -> dict[str, str]:
    if not isinstance(project, Mapping) or not isinstance(connections, Mapping):
        return {}

    source_name = project.get("source_connection")
    target_name = project.get("target_connection")
    source = connections.get(source_name) if source_name else None
    target = connections.get(target_name) if target_name else None

    values: dict[str, str] = {}
    if isinstance(source, Mapping):
        values.update(db_connection_zdm_values(source.get("db_type"), "source", migration_method))
    if isinstance(target, Mapping):
        values.update(db_connection_zdm_values(target.get("db_type"), "target", migration_method))
    return values


def project_rule_group_values(
    project: Any,
    connections: Any,
    rule_group_refs: Mapping[str, Any],
) -> dict[str, str]:
    if not isinstance(project, Mapping) or not isinstance(connections, Mapping):
        return {}

    source_name = project.get("source_connection")
    target_name = project.get("target_connection")
    source = connections.get(source_name) if source_name else None
    target = connections.get(target_name) if target_name else None

    out: dict[str, str] = {}
    for output_name, rule_group_ref in rule_group_refs.items():
        _, role = _parse_rule_group_ref(rule_group_ref)
        connection = source if role == "source" else target
        if not isinstance(connection, Mapping):
            continue
        value = db_connection_rule_group(connection.get("db_type"), rule_group_ref)
        if value:
            out[str(output_name)] = value
    return out


def _zdm_mapping_name_for_role_method(role: Any, migration_method: Any) -> str:
    normalized_role = normalize_connection_role(role)
    method = str(migration_method or "").strip().upper()
    if method.endswith("_LOGICAL"):
        return "logical_source" if normalized_role == "source" else "logical_target"
    if method.endswith("_PHYSICAL"):
        return "physical_target" if normalized_role == "target" else ""
    return ""


def is_adb_database_type(value: Any) -> bool:
    normalized = normalize_connection_type(value)
    if normalized in ADB_ZDM_TARGET_DBTYPES:
        return True
    logical_target = db_connection_zdm_values(normalized, "target", "OFFLINE_LOGICAL")
    return (
        str(logical_target.get("TARGETDATABASE_DBTYPE") or "").strip().upper()
        in ADB_ZDM_TARGET_DBTYPES
    )


def _validate_environment(key: str, value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RuntimeError(f"{key} must define an environment mapping")
    unknown_keys = set(value.keys()) - (ENVIRONMENT_REQUIRED_KEYS | ENVIRONMENT_OPTIONAL_KEYS)
    if unknown_keys:
        raise RuntimeError(f"{key} has invalid keys: " + ", ".join(sorted(unknown_keys)))
    missing_keys = ENVIRONMENT_REQUIRED_KEYS - set(value.keys())
    if missing_keys:
        raise RuntimeError(f"{key} must define " + ", ".join(sorted(missing_keys)))

    display = value.get("display")
    if (
        not isinstance(display, dict)
        or not str(display.get("group") or "").strip()
        or not str(display.get("name") or "").strip()
    ):
        raise RuntimeError(f"{key} display must define group and name")

    notes = value.get("notes", [])
    if not isinstance(notes, list) or not all(isinstance(note, str) and note.strip() for note in notes):
        raise RuntimeError(f"{key} notes must be a list of non-empty strings")

    support = value.get("supports")
    if not isinstance(support, dict) or not support:
        raise RuntimeError(f"{key} supports must define source and/or target")
    for role, methods in support.items():
        if role not in DB_CONNECTION_ROLE_OPTIONS:
            raise RuntimeError(f"{key} supports has invalid role: {role}")
        if not isinstance(methods, list) or not methods:
            raise RuntimeError(f"{key} supports.{role} must be a non-empty list")
        if len(set(str(method) for method in methods)) != len(methods):
            raise RuntimeError(f"{key} supports.{role} must not contain duplicate migration methods")
        invalid_methods = sorted(str(method) for method in methods if str(method) not in MIGRATION_METHOD_KEYS)
        if invalid_methods:
            raise RuntimeError(
                f"{key} supports.{role} has invalid migration method: " + ", ".join(invalid_methods)
            )

    rule_groups = value.get("rule_groups")
    if not isinstance(rule_groups, dict):
        raise RuntimeError(f"{key} rule_groups must define logical and/or physical groups")
    _validate_rule_groups(key, rule_groups)

    zdm = value.get("zdm")
    if not isinstance(zdm, dict) or not zdm:
        raise RuntimeError(f"{key} zdm must define at least one mapping")
    invalid_zdm_keys = sorted(str(mapping_name) for mapping_name in zdm.keys() if str(mapping_name) not in ZDM_MAPPING_KEYS)
    if invalid_zdm_keys:
        raise RuntimeError(f"{key} zdm has invalid mapping: " + ", ".join(invalid_zdm_keys))
    for mapping_name, mapping in zdm.items():
        if not isinstance(mapping, dict) or not mapping:
            raise RuntimeError(f"{key} {mapping_name} must be a non-empty mapping")
        if not all(str(map_key).strip() and str(map_value).strip() for map_key, map_value in mapping.items()):
            raise RuntimeError(f"{key} {mapping_name} must contain non-empty ZDM values")

    _validate_supported_rule_groups(key, support, rule_groups)
    _validate_supported_zdm_mappings(key, support, zdm)

    return value


def _parse_rule_group_ref(value: Any) -> tuple[str, str]:
    parts = str(value or "").strip().lower().split(".")
    if len(parts) != 2 or parts[0] not in RULE_GROUP_FAMILIES or parts[1] not in DB_CONNECTION_ROLE_OPTIONS:
        raise ValueError(f"Invalid rule group reference: {value}")
    return parts[0], parts[1]


def _validate_rule_groups(key: str, rule_groups: Mapping[str, Any]) -> None:
    for family, groups in rule_groups.items():
        if family not in RULE_GROUP_FAMILIES:
            raise RuntimeError(f"{key} rule_groups has invalid family: {family}")
        if not isinstance(groups, dict) or not groups:
            raise RuntimeError(f"{key} rule_groups.{family} must be a non-empty mapping")
        for role, group_value in groups.items():
            if role not in DB_CONNECTION_ROLE_OPTIONS:
                raise RuntimeError(f"{key} rule_groups.{family} has invalid role: {role}")
            if not str(group_value or "").strip():
                raise RuntimeError(f"{key} rule_groups.{family}.{role} must be non-empty")


def _validate_supported_rule_groups(
    key: str,
    support: Mapping[str, Any],
    rule_groups: Mapping[str, Any],
) -> None:
    for role, methods in support.items():
        for method in methods:
            family = "logical" if str(method).endswith("_LOGICAL") else "physical"
            if family == "physical" and role == "source":
                continue
            family_groups = rule_groups.get(family) if isinstance(rule_groups.get(family), dict) else {}
            if role not in family_groups:
                raise RuntimeError(f"{key} rule_groups.{family}.{role} is required")


def _validate_supported_zdm_mappings(
    key: str,
    support: Mapping[str, Any],
    zdm: Mapping[str, Any],
) -> None:
    target_methods = support.get("target") or []
    if any(str(method).endswith("_LOGICAL") for method in target_methods) and "logical_target" not in zdm:
        raise RuntimeError(f"{key} zdm.logical_target is required")
    if any(str(method).endswith("_PHYSICAL") for method in target_methods) and "physical_target" not in zdm:
        raise RuntimeError(f"{key} zdm.physical_target is required")


CONNECTION_ENVIRONMENTS = load_connection_environments()
DB_CONNECTION_TYPE_OPTIONS = tuple(CONNECTION_ENVIRONMENTS.keys())


def _adb_zdm_target_dbtypes(environments: Mapping[str, Mapping[str, Any]]) -> tuple[str, ...]:
    values: set[str] = set()
    for env in environments.values():
        rule_groups = env.get("rule_groups") if isinstance(env.get("rule_groups"), Mapping) else {}
        logical = rule_groups.get("logical") if isinstance(rule_groups.get("logical"), Mapping) else {}
        if str(logical.get("target") or "").strip().upper() != "ADB":
            continue
        zdm = env.get("zdm") if isinstance(env.get("zdm"), Mapping) else {}
        logical_target = zdm.get("logical_target") if isinstance(zdm.get("logical_target"), Mapping) else {}
        dbtype = str(logical_target.get("TARGETDATABASE_DBTYPE") or "").strip().upper()
        if dbtype:
            values.add(dbtype)
    return tuple(sorted(values))


ADB_ZDM_TARGET_DBTYPES = _adb_zdm_target_dbtypes(CONNECTION_ENVIRONMENTS)
