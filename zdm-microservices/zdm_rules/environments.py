from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

ADB_ZDM_TARGET_DBTYPES = ("ADBD", "ADBS", "ADBCC")
DB_CONNECTION_ROLE_OPTIONS = ("source", "target")
ENVIRONMENTS_PATH = Path(__file__).resolve().parent / "definitions" / "catalogs" / "environments.yaml"
ENVIRONMENT_TOP_LEVEL_KEYS = {"display", "migration_support", "notes", "zdm"}
MIGRATION_METHOD_KEYS = {"OFFLINE_LOGICAL", "ONLINE_LOGICAL", "OFFLINE_PHYSICAL", "ONLINE_PHYSICAL"}
SUPPORT_VALUES = {"supported", "unsupported"}
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
    group = str(display.get("group") or "")

    label = name
    if group:
        label = f"{label} ({group})"
    return label


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
    support = env.get("migration_support") if isinstance(env, dict) else {}
    role_support = support.get(normalized_role) if isinstance(support, dict) else {}
    if not isinstance(role_support, dict):
        return False
    return any(str(status).strip().lower() == "supported" for status in role_support.values())


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

    normalized_role = normalize_connection_role(role)
    method = str(migration_method or "").strip().upper()
    if method.endswith("_LOGICAL"):
        mapping_name = "logical_source" if normalized_role == "source" else "logical_target"
    elif method.endswith("_PHYSICAL"):
        mapping_name = "physical_target" if normalized_role == "target" else ""
    else:
        mapping_name = ""

    zdm = env.get("zdm") if isinstance(env.get("zdm"), dict) else {}
    mapping = zdm.get(mapping_name) if mapping_name else {}
    if not isinstance(mapping, Mapping):
        return {}
    return {
        str(key): str(value)
        for key, value in mapping.items()
        if value not in (None, "")
    }


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


def project_logical_scenario_values(project: Any, connections: Any) -> dict[str, str]:
    if not isinstance(project, Mapping) or not isinstance(connections, Mapping):
        return {"source_type": "ORACLE_DATABASE", "target_type": "ADB"}

    source_name = project.get("source_connection")
    target_name = project.get("target_connection")
    source = connections.get(source_name) if source_name else None
    target = connections.get(target_name) if target_name else None

    source_type = "ORACLE_DATABASE"
    if isinstance(source, Mapping):
        source_values = db_connection_zdm_values(source.get("db_type"), "source", "OFFLINE_LOGICAL")
        if (
            normalize_connection_type(source_values.get("SOURCEDATABASE_ENVIRONMENT_NAME")) == "AMAZON"
            and normalize_connection_type(source_values.get("SOURCEDATABASE_ENVIRONMENT_DBTYPE")) == "RDS_ORACLE"
        ):
            source_type = "AWS_RDS_ORACLE"

    target_type = "ADB"
    if isinstance(target, Mapping):
        target_values = db_connection_zdm_values(target.get("db_type"), "target", "OFFLINE_LOGICAL")
        target_dbtype = normalize_connection_type(target_values.get("TARGETDATABASE_DBTYPE"))
        target_connection_type = normalize_connection_type(target.get("db_type"))
        if target_dbtype in ADB_ZDM_TARGET_DBTYPES:
            target_type = "ADB"
        elif target_connection_type == "ORACLE_DATABASE":
            target_type = "USER_MANAGED"
        elif target_dbtype:
            target_type = "CO_MANAGED"

    return {"source_type": source_type, "target_type": target_type}


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
    if set(value.keys()) != ENVIRONMENT_TOP_LEVEL_KEYS:
        raise RuntimeError(f"{key} must define display, migration_support, notes, and zdm")

    display = value.get("display")
    if (
        not isinstance(display, dict)
        or not str(display.get("group") or "").strip()
        or not str(display.get("name") or "").strip()
    ):
        raise RuntimeError(f"{key} display must define group and name")

    notes = value.get("notes")
    if not isinstance(notes, list) or not all(isinstance(note, str) and note.strip() for note in notes):
        raise RuntimeError(f"{key} notes must be a list of non-empty strings")

    support = value.get("migration_support")
    if not isinstance(support, dict) or not support:
        raise RuntimeError(f"{key} migration_support must define source and/or target")
    for role, role_support in support.items():
        if role not in DB_CONNECTION_ROLE_OPTIONS:
            raise RuntimeError(f"{key} migration_support has invalid role: {role}")
        if not isinstance(role_support, dict) or set(role_support.keys()) != MIGRATION_METHOD_KEYS:
            raise RuntimeError(f"{key} {role} migration_support must define every migration method")
        if not set(str(status) for status in role_support.values()).issubset(SUPPORT_VALUES):
            raise RuntimeError(f"{key} {role} migration_support has invalid support status")

    zdm = value.get("zdm")
    if not isinstance(zdm, dict) or set(zdm.keys()) != ZDM_MAPPING_KEYS:
        raise RuntimeError(f"{key} zdm must define logical_source, logical_target, and physical_target")
    for mapping_name, mapping in zdm.items():
        if mapping is None:
            continue
        if not isinstance(mapping, dict):
            raise RuntimeError(f"{key} {mapping_name} must be a mapping or null")
        if not all(str(map_key).strip() and str(map_value).strip() for map_key, map_value in mapping.items()):
            raise RuntimeError(f"{key} {mapping_name} must contain non-empty ZDM values")

    return value


CONNECTION_ENVIRONMENTS = load_connection_environments()
DB_CONNECTION_TYPE_OPTIONS = tuple(CONNECTION_ENVIRONMENTS.keys())
