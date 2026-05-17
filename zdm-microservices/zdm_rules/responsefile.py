from __future__ import annotations

import re
from typing import Any, List, Mapping, Optional, Tuple

from zdm_rules.catalog import MigrationProfile, get_profile, normalize_method
from zdm_rules.common import normalize_rsp_value


SUPPORTED_RESPONSE_FILE_METHODS = {"OFFLINE_LOGICAL"}
ADDITIONAL_PARAMETER_RE = re.compile(r"^[A-Z][A-Z0-9_]*(?:-[0-9]+)?$")


def response_file_supported(method: Any) -> bool:
    return normalize_method(method) in SUPPORTED_RESPONSE_FILE_METHODS


def build_response_file_lines(
    values: Mapping[str, Any],
    profile: Optional[MigrationProfile] = None,
) -> List[str]:
    profile = profile or _profile_from_values(values)
    render_values = profile.response_values_with_defaults(values)
    _validate_response_file_values(profile, render_values)

    out: List[str] = []
    for key, value in render_values.items():
        if key in ("project", "filename"):
            continue

        if value is None:
            continue

        if key == "include_schemas" and isinstance(value, list):
            for include_index, schema in enumerate(value, start=1):
                schema_s = str(schema).strip()
                if not schema_s:
                    continue
                out.append(f"INCLUDEOBJECTS-{include_index}=owner:{schema_s}")
            continue

        if key == "DATAPUMPSETTINGS_METADATAREMAPS" and isinstance(value, list):
            for remap_index, remap in enumerate(value, start=1):
                remap_values = _metadata_remap_values(remap)
                if remap_values is None:
                    continue
                remap_type, old_value, new_value = remap_values
                out.append(
                    f"DATAPUMPSETTINGS_METADATAREMAPS-{remap_index}=type:{remap_type}, oldValue:{old_value}, newValue:{new_value}"
                )
            continue

        if key == "additional" and isinstance(value, dict):
            for additional_key, additional_value in value.items():
                if additional_value is None:
                    continue
                additional_value_s = normalize_rsp_value(additional_value).strip()
                if additional_value_s == "":
                    continue
                out.append(f"{additional_key}={additional_value_s}")
            continue

        value_s = normalize_rsp_value(value).strip()
        if value_s == "":
            continue
        out.append(f"{key}={value_s}")

    return out


def _validate_response_file_values(profile: MigrationProfile, values: Mapping[str, Any]) -> None:
    _reject_newline_values(values)

    if not response_file_supported(profile.method):
        raise ValueError(f"{profile.method} response files are not supported yet")

    migration_method = normalize_method(values.get("MIGRATION_METHOD"))
    if not migration_method:
        raise ValueError("MIGRATION_METHOD is required")
    if migration_method != profile.method:
        raise ValueError(f"MIGRATION_METHOD must be {profile.method}")

    medium = normalize_method(values.get("DATA_TRANSFER_MEDIUM"))
    if not medium:
        raise ValueError("DATA_TRANSFER_MEDIUM is required")
    if medium not in profile.medium_keys():
        raise ValueError(f"Unsupported DATA_TRANSFER_MEDIUM for {profile.method}: {medium}")

    allowed = set(profile.all_response_field_keys(medium, context=values))
    allowed.update({"project", "filename"})

    for key in values.keys():
        if key not in allowed:
            raise ValueError(f"Unsupported response file parameter for {profile.method}: {key}")

    _validate_additional_parameters(profile, medium, values.get("additional"), values)

    validation_errors = profile.response_validation_errors(values)
    if validation_errors:
        raise ValueError("; ".join(validation_errors))


def _validate_additional_parameters(
    profile: MigrationProfile,
    medium: str,
    additional: Any,
    values: Mapping[str, Any],
) -> None:
    if additional in (None, ""):
        return
    if not isinstance(additional, Mapping):
        raise ValueError("additional must be an object")

    managed_keys = {
        str(key).upper()
        for key in profile.all_response_field_keys(medium, context=values)
        if key not in {"additional", "project", "filename"}
    }
    for key in additional.keys():
        key_s = str(key).strip()
        if not ADDITIONAL_PARAMETER_RE.fullmatch(key_s):
            raise ValueError(f"Invalid additional response file parameter: {key_s}")
        base_key = key_s.split("-", 1)[0].upper()
        if key_s.upper() in managed_keys or base_key in managed_keys:
            raise ValueError(
                f"Additional response file parameter duplicates managed response file parameter: {key_s}"
            )


def _reject_newline_values(value: Any, path: str = "values") -> None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            key_s = str(key)
            if "\n" in key_s or "\r" in key_s:
                raise ValueError(f"Response file parameter {path} must not contain newline characters")
            _reject_newline_values(child, f"{path}.{key_s}")
        return

    if isinstance(value, list):
        for index, child in enumerate(value):
            _reject_newline_values(child, f"{path}[{index}]")
        return

    if isinstance(value, str) and ("\n" in value or "\r" in value):
        raise ValueError(f"Response file parameter {path} must not contain newline characters")


def _profile_from_values(values: Mapping[str, Any]) -> MigrationProfile:
    migration_method = normalize_method(values.get("MIGRATION_METHOD"))
    if not migration_method:
        raise ValueError("MIGRATION_METHOD is required")
    return get_profile(migration_method)


def _metadata_remap_values(remap: Any) -> Optional[Tuple[Any, Any, Any]]:
    remap_type = old_value = new_value = None
    if isinstance(remap, dict):
        remap_type = remap.get("type")
        old_value = remap.get("oldValue")
        new_value = remap.get("newValue")
    elif isinstance(remap, (list, tuple)) and len(remap) == 3:
        remap_type, old_value, new_value = remap

    if remap_type is None or old_value is None or new_value is None:
        return None
    return remap_type, old_value, new_value
