from typing import Any


def normalize_rsp_value(value: Any) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, str):
        if value.lower() == "true":
            return "TRUE"
        if value.lower() == "false":
            return "FALSE"
        return value
    return str(value)


def nonblank(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str) and not value.strip():
        return False
    return True
