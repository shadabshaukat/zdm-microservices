from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml

DISCOVERY_RULES_PATH = Path(__file__).resolve().parent / "definitions" / "discovery" / "comparison_rules.yaml"
VALID_STATUSES = {
    "passed",
    "difference",
    "source_only",
    "target_only",
    "readiness_issue",
    "not_applicable",
    "not_returned",
}
VALID_SEVERITIES = {"none", "low", "medium", "high", "critical"}


def load_discovery_comparison_rules(path: Path = DISCOVERY_RULES_PATH) -> dict[str, Any]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise RuntimeError(f"{path.name} must define a mapping")
    if raw.get("schema_version") != 1:
        raise RuntimeError(f"{path.name} schema_version must be 1")
    methods = raw.get("methods")
    if not isinstance(methods, dict) or not methods:
        raise RuntimeError(f"{path.name} must define methods")

    for method, config in methods.items():
        method_key = str(method or "").strip().upper()
        if not method_key:
            raise RuntimeError(f"{path.name} has an empty method key")
        if not isinstance(config, dict):
            raise RuntimeError(f"{method_key} must define a mapping")
        sections = config.get("sections")
        if not isinstance(sections, dict) or not sections:
            raise RuntimeError(f"{method_key} must define sections")
        for section_key, section in sections.items():
            _validate_section(path.name, method_key, str(section_key), section)
    return raw


def compare_discovery_snapshots(
    migration_method: Any,
    source_snapshot: Mapping[str, Any] | None,
    target_snapshot: Mapping[str, Any] | None,
    *,
    rules_path: Path = DISCOVERY_RULES_PATH,
) -> dict[str, Any]:
    method = str(migration_method or "").strip().upper()
    rules = load_discovery_comparison_rules(rules_path)
    method_config = (rules.get("methods") or {}).get(method)
    if not isinstance(method_config, dict):
        raise ValueError(f"No discovery comparison rules are defined for {method}")

    source = source_snapshot if isinstance(source_snapshot, Mapping) else {}
    target = target_snapshot if isinstance(target_snapshot, Mapping) else {}
    sections_out: list[dict[str, Any]] = []

    for section_key, section in method_config["sections"].items():
        rows: list[dict[str, Any]] = []
        for rule in section["rules"]:
            rows.extend(_evaluate_rule(str(rule["id"]), rule, source, target))
        if rows:
            sections_out.append(
                {
                    "key": str(section_key),
                    "label": str(section["label"]),
                    "rows": rows,
                }
            )

    return {
        "summary": _summarize_rows(sections_out),
        "sections": sections_out,
    }


def _validate_section(source_name: str, method: str, section_key: str, section: Any) -> None:
    if not isinstance(section, dict):
        raise RuntimeError(f"{method}.{section_key} must define a mapping")
    if not str(section.get("label") or "").strip():
        raise RuntimeError(f"{method}.{section_key}.label is required")
    rules = section.get("rules")
    if not isinstance(rules, list) or not rules:
        raise RuntimeError(f"{method}.{section_key}.rules must be a non-empty list")
    for rule in rules:
        _validate_rule(source_name, method, section_key, rule)


def _validate_rule(source_name: str, method: str, section_key: str, rule: Any) -> None:
    if not isinstance(rule, dict):
        raise RuntimeError(f"{method}.{section_key} rule must define a mapping")
    rule_id = str(rule.get("id") or "").strip()
    if not rule_id:
        raise RuntimeError(f"{method}.{section_key} rule id is required")
    if not str(rule.get("label") or "").strip():
        raise RuntimeError(f"{method}.{section_key}.{rule_id}.label is required")
    compare = rule.get("compare")
    if not isinstance(compare, dict):
        raise RuntimeError(f"{method}.{section_key}.{rule_id}.compare is required")
    operator = str(compare.get("operator") or "").strip()
    if operator not in {"equals", "set_difference", "required", "numeric_min", "numeric_max", "target_gte_source"}:
        raise RuntimeError(f"{source_name}: unsupported operator {operator} in {rule_id}")
    if operator != "required":
        if not str(compare.get("source_path") or "").strip() or not str(compare.get("target_path") or "").strip():
            raise RuntimeError(f"{method}.{section_key}.{rule_id} must define source_path and target_path")
    for outcome_key in ("on_fail", "on_source_only", "on_target_only", "on_missing"):
        outcome = rule.get(outcome_key)
        if outcome is None:
            continue
        _validate_outcome(method, section_key, rule_id, outcome_key, outcome)


def _validate_outcome(method: str, section_key: str, rule_id: str, outcome_key: str, outcome: Any) -> None:
    if not isinstance(outcome, dict):
        raise RuntimeError(f"{method}.{section_key}.{rule_id}.{outcome_key} must define a mapping")
    status = str(outcome.get("status") or "").strip()
    if status not in VALID_STATUSES:
        raise RuntimeError(f"{method}.{section_key}.{rule_id}.{outcome_key}.status is invalid")
    severity = str(outcome.get("severity") or "none").strip()
    if severity not in VALID_SEVERITIES:
        raise RuntimeError(f"{method}.{section_key}.{rule_id}.{outcome_key}.severity is invalid")
    for key in ("message", "guidance"):
        if key in outcome and not isinstance(outcome.get(key), str):
            raise RuntimeError(f"{method}.{section_key}.{rule_id}.{outcome_key}.{key} must be text")


def _evaluate_rule(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> list[dict[str, Any]]:
    compare = rule["compare"]
    operator = str(compare["operator"])
    if operator == "set_difference":
        return _evaluate_set_difference(rule_id, rule, source, target)
    if operator == "equals":
        return [_evaluate_equals(rule_id, rule, source, target)]
    if operator == "required":
        return [_evaluate_required(rule_id, rule, source, target)]
    if operator in {"numeric_min", "numeric_max"}:
        return [_evaluate_numeric(rule_id, rule, source, target)]
    if operator == "target_gte_source":
        return [_evaluate_target_gte_source(rule_id, rule, source, target)]
    raise ValueError(f"Unsupported discovery comparison operator: {operator}")


def _evaluate_equals(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    compare = rule["compare"]
    source_value = _extract_path(source, str(compare["source_path"]))
    target_value = _extract_path(target, str(compare["target_path"]))
    source_present = _present(source_value)
    target_present = _present(target_value)
    if not source_present and not target_present:
        return _row(rule_id, rule, source_value, target_value, "not_returned")
    if source_present and not target_present:
        outcome = rule.get("on_source_only") if isinstance(rule.get("on_source_only"), Mapping) else None
        return _row(rule_id, rule, source_value, target_value, str((outcome or {}).get("status") or "source_only"), outcome)
    if target_present and not source_present:
        outcome = rule.get("on_target_only") if isinstance(rule.get("on_target_only"), Mapping) else None
        return _row(rule_id, rule, source_value, target_value, str((outcome or {}).get("status") or "target_only"), outcome)
    if _normalize_scalar(source_value) == _normalize_scalar(target_value):
        return _row(rule_id, rule, source_value, target_value, "passed")
    outcome = rule.get("on_fail") if isinstance(rule.get("on_fail"), Mapping) else {}
    return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "difference"), outcome)


def _evaluate_set_difference(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> list[dict[str, Any]]:
    compare = rule["compare"]
    source_values = _as_sorted_set(_extract_path(source, str(compare["source_path"])))
    target_values = _as_sorted_set(_extract_path(target, str(compare["target_path"])))
    rows: list[dict[str, Any]] = []

    source_only = [value for value in source_values if value not in target_values]
    target_only = [value for value in target_values if value not in source_values]
    for value in source_only:
        outcome = rule.get("on_source_only") if isinstance(rule.get("on_source_only"), Mapping) else {}
        rows.append(
            _row(
                f"{rule_id}:{value}",
                rule,
                value,
                None,
                str(outcome.get("status") or "source_only"),
                outcome,
            )
        )
    for value in target_only:
        outcome = rule.get("on_target_only") if isinstance(rule.get("on_target_only"), Mapping) else {}
        rows.append(
            _row(
                f"{rule_id}:{value}",
                rule,
                None,
                value,
                str(outcome.get("status") or "target_only"),
                outcome,
            )
        )
    if not rows and (source_values or target_values):
        rows.append(_row(rule_id, rule, ", ".join(source_values), ", ".join(target_values), "passed"))
    if not rows:
        rows.append(_row(rule_id, rule, None, None, "not_returned"))
    return rows


def _evaluate_required(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    compare = rule["compare"]
    source_value = _extract_path(source, str(compare.get("source_path") or ""))
    target_value = _extract_path(target, str(compare.get("target_path") or ""))
    if _present(source_value) and _present(target_value):
        return _row(rule_id, rule, source_value, target_value, "passed")
    outcome = rule.get("on_missing") if isinstance(rule.get("on_missing"), Mapping) else {}
    return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "not_returned"), outcome)


def _evaluate_numeric(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    compare = rule["compare"]
    source_value = _extract_path(source, str(compare["source_path"]))
    target_value = _extract_path(target, str(compare["target_path"]))
    threshold = _to_float(compare.get("threshold"))
    source_num = _to_float(source_value)
    target_num = _to_float(target_value)
    if threshold is None or source_num is None or target_num is None:
        outcome = rule.get("on_missing") if isinstance(rule.get("on_missing"), Mapping) else {}
        return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "not_returned"), outcome)
    operator = str(compare["operator"])
    passed = (
        source_num >= threshold
        and target_num >= threshold
        if operator == "numeric_min"
        else source_num <= threshold and target_num <= threshold
    )
    if passed:
        return _row(rule_id, rule, source_value, target_value, "passed")
    outcome = rule.get("on_fail") if isinstance(rule.get("on_fail"), Mapping) else {}
    return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "difference"), outcome)


def _evaluate_target_gte_source(
    rule_id: str,
    rule: Mapping[str, Any],
    source: Mapping[str, Any],
    target: Mapping[str, Any],
) -> dict[str, Any]:
    compare = rule["compare"]
    source_value = _extract_path(source, str(compare["source_path"]))
    target_value = _extract_path(target, str(compare["target_path"]))
    source_num = _to_float(source_value)
    target_num = _to_float(target_value)
    if source_num is None or target_num is None:
        outcome = rule.get("on_missing") if isinstance(rule.get("on_missing"), Mapping) else {}
        return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "not_returned"), outcome)
    if target_num >= source_num:
        return _row(rule_id, rule, source_value, target_value, "passed")
    outcome = rule.get("on_fail") if isinstance(rule.get("on_fail"), Mapping) else {}
    return _row(rule_id, rule, source_value, target_value, str(outcome.get("status") or "difference"), outcome)


def _row(
    row_key: str,
    rule: Mapping[str, Any],
    source_value: Any,
    target_value: Any,
    status: str,
    outcome: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    status_value = status if status in VALID_STATUSES else "difference"
    details = outcome if isinstance(outcome, Mapping) else {}
    return {
        "key": row_key,
        "label": str(rule.get("label") or row_key),
        "source": {"present": _present(source_value), "value": _display_value(source_value)},
        "target": {"present": _present(target_value), "value": _display_value(target_value)},
        "status": status_value,
        "severity": str(details.get("severity") or ("none" if status_value == "passed" else "medium")),
        "message": str(details.get("message") or ""),
        "guidance": str(details.get("guidance") or ""),
    }


def _summarize_rows(sections: list[dict[str, Any]]) -> dict[str, int]:
    summary = {
        "readiness_issues": 0,
        "differences": 0,
        "source_only": 0,
        "target_only": 0,
    }
    for section in sections:
        for row in section.get("rows") or []:
            status = row.get("status")
            if status == "readiness_issue":
                summary["readiness_issues"] += 1
            elif status == "difference":
                summary["differences"] += 1
            elif status == "source_only":
                summary["source_only"] += 1
            elif status == "target_only":
                summary["target_only"] += 1
    return summary


def _extract_path(payload: Any, path: str) -> Any:
    if not path:
        return payload
    current = payload
    for part in path.split("."):
        current = _extract_part(current, part)
        if current is None:
            return None
    return current


def _extract_part(value: Any, part: str) -> Any:
    if isinstance(value, Mapping):
        if part in value:
            return value[part]
        part_upper = part.upper()
        for key, item in value.items():
            if str(key).upper() == part_upper:
                return item
        return None

    if isinstance(value, list):
        if not value:
            return []
        parameter_match = _extract_parameter_value(value, part)
        if parameter_match is not None:
            return parameter_match
        extracted = []
        part_upper = part.upper()
        for item in value:
            if not isinstance(item, Mapping):
                continue
            if part in item:
                extracted.append(item[part])
                continue
            for key, field_value in item.items():
                if str(key).upper() == part_upper:
                    extracted.append(field_value)
                    break
        return extracted

    return None


def _extract_parameter_value(rows: list[Any], parameter_name: str) -> Any:
    target = parameter_name.upper()
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        parameter = row.get("PARAMETER", row.get("parameter"))
        if str(parameter or "").upper() == target:
            return row.get("VALUE", row.get("value"))
    return None


def _present(value: Any) -> bool:
    return value not in (None, "", [])


def _normalize_scalar(value: Any) -> str:
    if isinstance(value, list):
        return "|".join(_as_sorted_set(value))
    if isinstance(value, Mapping):
        return "|".join(f"{key}={_normalize_scalar(item)}" for key, item in sorted(value.items()))
    return str(value or "").strip()


def _as_sorted_set(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    raw_values = value if isinstance(value, list) else [value]
    normalized = {
        str(item).strip()
        for item in raw_values
        if item not in (None, "") and str(item).strip()
    }
    return sorted(normalized)


def _display_value(value: Any) -> Any:
    if isinstance(value, list):
        return ", ".join(_as_sorted_set(value))
    if isinstance(value, Mapping):
        return dict(value)
    return value


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None
