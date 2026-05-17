from __future__ import annotations

from typing import Any, Mapping


def condition_matches(condition: Any, context: Mapping[str, Any]) -> bool:
    if condition in (None, "", "always"):
        return True
    if isinstance(condition, str):
        return condition.strip().lower() == "always"
    if not isinstance(condition, Mapping):
        return False

    if "all" in condition:
        return all(condition_matches(item, context) for item in condition.get("all") or [])
    if "any" in condition:
        return any(condition_matches(item, context) for item in condition.get("any") or [])
    if "not" in condition:
        return not condition_matches(condition.get("not"), context)

    if "field_equals" in condition:
        return _matches_field_equals(condition.get("field_equals"), context)
    if "field_in" in condition:
        return _matches_field_in(condition.get("field_in"), context)

    # Human-friendly shorthand for simple boolean/value checks.
    return all(_value_equal(_context_value(context, key), expected) for key, expected in condition.items())


def _matches_field_equals(spec: Any, context: Mapping[str, Any]) -> bool:
    if not isinstance(spec, Mapping):
        return False
    return all(_value_equal(_context_value(context, key), expected) for key, expected in spec.items())


def _matches_field_in(spec: Any, context: Mapping[str, Any]) -> bool:
    if not isinstance(spec, Mapping):
        return False
    for key, options in spec.items():
        if not isinstance(options, (list, tuple, set)):
            return False
        value = _context_value(context, key)
        if not any(_value_equal(value, option) for option in options):
            return False
    return True


def _context_value(context: Mapping[str, Any], key: Any) -> Any:
    key_s = str(key)
    if key_s in context:
        return context[key_s]
    lowered = key_s.lower()
    for existing_key, value in context.items():
        if str(existing_key).lower() == lowered:
            return value
    return None


def _value_equal(left: Any, right: Any) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        left_bool = _bool_value(left)
        right_bool = _bool_value(right)
        return left_bool is not None and right_bool is not None and left_bool == right_bool
    return str(left or "").strip().upper() == str(right or "").strip().upper()


def _bool_value(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    text = str(value or "").strip().upper()
    if text in {"TRUE", "YES", "Y", "1"}:
        return True
    if text in {"FALSE", "NO", "N", "0"}:
        return False
    return None
