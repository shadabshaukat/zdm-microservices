from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, Iterable, List, Mapping, Optional

from zdm_rules.catalog import get_profile, load_profiles
from zdm_rules.environments import (
    CONNECTION_ENVIRONMENTS,
    project_environment_response_values,
    project_rule_group_values,
)


NAVIGATION_GROUPS = [
    {
        "label": "Database Setup",
        "items": [
            {"label": "DB Connections", "section": "connections", "path": "/connections"},
            {"label": "DB Wallets & Credentials", "section": "wallet", "path": "/wallets"},
            {"label": "DB Discovery", "section": "discovery", "path": "/discovery"},
        ],
    },
    {
        "label": "Migrations",
        "items": [
            {"label": "Projects", "section": "projects", "path": "/projects"},
            {"label": "ZDM Response Files", "section": "response", "path": "/response-files"},
            {"label": "ZDM Job Definitions", "section": "createjob", "path": "/job-definitions"},
            {"label": "ZDM Job Submission", "section": "runjob", "path": "/job-submission"},
            {"label": "ZDM Job Monitoring", "section": "jobs", "path": "/jobs"},
            {"label": "Migration Dashboard", "section": "fleet_dashboard", "path": "/dashboard"},
        ],
    },
    {
        "label": "Administration",
        "items": [
            {"label": "ZEUS Settings", "section": "settings", "path": "/settings"},
        ],
    },
]


def build_frontend_metadata(
    *,
    projects: Optional[Mapping[str, Any]] = None,
    connections: Optional[Mapping[str, Any]] = None,
    project: Optional[str] = None,
    migration_method: Optional[str] = None,
    medium: Optional[str] = None,
    run_type: Optional[str] = None,
) -> Dict[str, Any]:
    method = _normalize_method(migration_method)
    resolved_context = None
    if any(value not in (None, "") for value in (project, migration_method, medium, run_type)):
        resolved_context = build_resolved_context(
            projects=projects or {},
            connections=connections or {},
            project=project,
            migration_method=method,
            medium=medium,
            run_type=run_type,
        )

    return {
        "status": "success",
        "environments": _environment_metadata(),
        "migration_profiles": _profile_metadata(),
        "navigation": {"groups": deepcopy(NAVIGATION_GROUPS)},
        "resolved_context": resolved_context,
    }


def build_resolved_context(
    *,
    projects: Mapping[str, Any],
    connections: Mapping[str, Any],
    project: Optional[str],
    migration_method: str,
    medium: Optional[str],
    run_type: Optional[str],
) -> Dict[str, Any]:
    profile = _profile_or_error(migration_method)
    project_name = str(project or "").strip()
    if project_name:
        project_record = projects.get(project_name)
        if not isinstance(project_record, Mapping):
            raise KeyError("Project not found")
    else:
        project_record = {}

    decision_refs: Dict[str, Any] = {}
    decision_values: Dict[str, Any] = {}
    for name, config in profile.decision_input_controls.items():
        if "default" in config:
            decision_values[name] = config.get("default")
        if "from_rule_group" in config:
            decision_refs[name] = config.get("from_rule_group")
    if project_record and decision_refs:
        decision_values.update(project_rule_group_values(project_record, connections, decision_refs))

    derived_values = (
        project_environment_response_values(project_record, connections, profile.method)
        if project_record
        else {}
    )
    context = {
        **decision_values,
        **derived_values,
        "MIGRATION_METHOD": profile.method,
    }
    requested_medium = _normalize_method(medium)
    if requested_medium and requested_medium not in profile.medium_keys():
        raise ValueError("Unsupported data transfer medium")
    medium_value = requested_medium or profile.default_medium
    if medium_value:
        context["DATA_TRANSFER_MEDIUM"] = medium_value

    media_options = []
    for option in profile.medium_options(context):
        config = profile.medium(option.value)
        media_options.append(
            {
                "value": option.value,
                "label": str(config.get("label") or option.value),
                "enabled": bool(option.enabled),
                "disabled_reason": "" if option.enabled else str(config.get("unavailable_hint") or ""),
                "guidance": str(config.get("hint") or ""),
            }
        )

    response_sections = {
        section: {
            "label": profile.section_label(section),
            "fields": profile.section_field_keys(section, context),
        }
        for section in _profile_response_section_names(profile)
    }
    medium_sections = {
        section: {
            "label": profile.section_label(section),
            "fields": profile.medium_section_field_keys(medium_value, section, context=context),
        }
        for section in profile.medium_section_names(medium_value)
    }
    visible_response_fields = _unique(
        profile.common_response_field_keys(context)
        + profile.medium_field_keys(medium_value, context=context)
    )

    return {
        "project": project_name,
        "migration_method": profile.method,
        "medium": medium_value,
        "run_type": str(run_type or "").upper(),
        "decision_input_values": decision_values,
        "derived_response_values": derived_values,
        "media_options": media_options,
        "response_sections": response_sections,
        "medium_sections": medium_sections,
        "visible_response_fields": visible_response_fields,
        "required_response_fields": _required_response_fields(profile, context, medium_value),
        "additional_default_rows": profile.additional_default_rows(),
        "job_sections": {
            "source_database": {
                "fields": profile.job_section_field_keys("source_database"),
            },
            "target_database": {
                "fields": profile.job_section_field_keys("target_database"),
            },
        },
    }


def _environment_metadata() -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, config in CONNECTION_ENVIRONMENTS.items():
        out[str(name)] = {
            "display": deepcopy(config.get("display") or {}),
            "supports": deepcopy(config.get("supports") or {}),
            "notes": deepcopy(config.get("notes") or []),
        }
    return out


def _profile_metadata() -> Dict[str, Any]:
    profiles: Dict[str, Any] = {}
    for method, profile in load_profiles().items():
        response_file = profile.data.get("response_file") if isinstance(profile.data, Mapping) else {}
        response_file = response_file if isinstance(response_file, Mapping) else {}
        response_ui = response_file.get("ui") if isinstance(response_file.get("ui"), Mapping) else {}
        job_submission = profile.data.get("job_submission") if isinstance(profile.data, Mapping) else {}
        job_submission = job_submission if isinstance(job_submission, Mapping) else {}
        profiles[str(method)] = {
            "method": profile.method,
            "migration_type": profile.migration_type,
            "default_medium": profile.default_medium,
            "decision_inputs": {
                "controls": deepcopy(profile.decision_input_controls),
            },
            "response_file": {
                "layout": profile.response_layout(),
                "fields": deepcopy(profile.fields),
                "section_labels": deepcopy(response_ui.get("section_labels") or {}),
                "medium_fields_title": profile.medium_fields_title(),
                "media": _media_metadata(profile.media),
            },
            "job_submission": {
                "fields": list(profile.common_job_field_keys()),
                "sections": deepcopy(job_submission.get("sections") or {}),
                "run_controls": deepcopy(profile.job_run_controls),
            },
        }
    return profiles


def _media_metadata(media: Mapping[str, Mapping[str, Any]]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for name, config in media.items():
        out[str(name)] = {
            "label": str(config.get("label") or name),
            "hint": str(config.get("hint") or ""),
            "unavailable_hint": str(config.get("unavailable_hint") or ""),
            "fields": deepcopy(config.get("fields") or []),
            "advanced_fields": deepcopy(config.get("advanced_fields") or []),
            "sections": deepcopy(config.get("sections") or {}),
        }
    return out


def _profile_or_error(migration_method: str):
    if not migration_method:
        raise ValueError("Unsupported migration method")
    try:
        return get_profile(migration_method)
    except ValueError as exc:
        raise ValueError("Unsupported migration method") from exc


def _normalize_method(value: Optional[str]) -> str:
    return str(value or "").strip().upper().replace("-", "_").replace(" ", "_")


def _profile_response_section_names(profile: Any) -> List[str]:
    names: List[str] = []
    for item in profile.response_layout():
        item_type = str(item.get("type") or "")
        if item_type == "tabs":
            names.extend(str(section) for section in item.get("tabs") or [])
        elif item_type == "sections":
            names.extend(_layout_section_names(item.get("sections") or []))
        elif item_type == "section":
            section = str(item.get("section") or "")
            if section:
                names.append(section)
    return _unique(names)


def _layout_section_names(items: Iterable[Any]) -> List[str]:
    names: List[str] = []
    for item in items:
        if isinstance(item, Mapping):
            names.extend(_layout_section_names(item.get("sections") or []))
        else:
            name = str(item or "")
            if name:
                names.append(name)
    return names


def _required_response_fields(profile: Any, context: Mapping[str, Any], medium: str) -> List[str]:
    fields = profile.all_response_field_keys(
        medium,
        include_advanced=True,
        context=context,
    )
    return [field for field in fields if profile.field_required_hint(field, context)]


def _unique(values: Iterable[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
