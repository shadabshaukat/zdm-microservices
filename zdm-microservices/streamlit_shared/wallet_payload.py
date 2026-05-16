from __future__ import annotations

from typing import Any, Dict, Mapping


def _raise_contract_error(endpoint: str, detail: str) -> None:
    raise ValueError(f"{endpoint} API contract error: {detail}")


def _contract_exact_keys(payload: Mapping[str, Any], endpoint: str, expected_keys: set[str]) -> None:
    keys = {str(key) for key in payload.keys()}
    if keys == expected_keys:
        return
    parts: list[str] = []
    missing = sorted(expected_keys - keys)
    extra = sorted(keys - expected_keys)
    if missing:
        parts.append("missing " + ", ".join(missing))
    if extra:
        parts.append("unexpected " + ", ".join(extra))
    _raise_contract_error(endpoint, "; ".join(parts))


def validate_credential_wallets_response(payload: Any) -> Dict[str, str]:
    endpoint = "GET /credential-wallets"
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, "expected JSON object")
    _contract_exact_keys(payload, endpoint, {"wallets"})
    wallets = payload.get("wallets")
    if not isinstance(wallets, list):
        _raise_contract_error(endpoint, "wallets must be a list")

    wallet_map: Dict[str, str] = {}
    for index, wallet in enumerate(wallets, start=1):
        if not isinstance(wallet, Mapping):
            _raise_contract_error(endpoint, f"wallets[{index}] must be an object")
        _contract_exact_keys(wallet, endpoint, {"name", "path", "credential_username"})
        name = wallet.get("name")
        path = wallet.get("path")
        credential_username = wallet.get("credential_username")
        if not isinstance(name, str) or not name:
            _raise_contract_error(endpoint, f"wallets[{index}].name must be a non-empty string")
        if not isinstance(path, str) or not path:
            _raise_contract_error(endpoint, f"wallets[{index}].path must be a non-empty string")
        if credential_username is not None and not isinstance(credential_username, str):
            _raise_contract_error(endpoint, f"wallets[{index}].credential_username must be a string or null")
        wallet_map[name] = path
    return wallet_map


def validate_credential_wallet_rows(payload: Any) -> list[Dict[str, Any]]:
    validate_credential_wallets_response(payload)
    return [dict(wallet) for wallet in payload["wallets"]]


def validate_credential_wallet_delete_response(payload: Any) -> Dict[str, Any]:
    endpoint = "DELETE /credential-wallets/{name}"
    if not isinstance(payload, Mapping):
        _raise_contract_error(endpoint, "expected JSON object")
    _contract_exact_keys(payload, endpoint, {"status", "message", "name"})
    if payload.get("status") != "success":
        _raise_contract_error(endpoint, "expected status success")
    message = payload.get("message")
    name = payload.get("name")
    if not isinstance(message, str) or not message:
        _raise_contract_error(endpoint, "message must be a non-empty string")
    if not isinstance(name, str) or not name:
        _raise_contract_error(endpoint, "name must be a non-empty string")
    return dict(payload)
