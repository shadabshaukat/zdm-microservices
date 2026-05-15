from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

T = TypeVar("T")


def api_request(
    method: str,
    path: str,
    base_url: str,
    auth: HTTPBasicAuth,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    quiet: bool = False,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            params=params,
            auth=auth,
            timeout=timeout,
        )
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = None
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text if exc.response is not None else "HTTP error"
        if not quiet:
            st.error(f"API error ({exc.response.status_code if exc.response else 'HTTP'}): {detail}")
        return None
    except requests.RequestException as exc:
        if not quiet:
            st.error(f"Request failed: {exc}")
        return None

    try:
        return response.json()
    except ValueError:
        if not quiet:
            st.error("Invalid API response: expected JSON from backend.")
        return None


def api_upload_file(
    path: str,
    base_url: str,
    auth: HTTPBasicAuth,
    field_name: str,
    uploaded_file: Any,
    quiet: bool = False,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url}{path}"
    files = {field_name: (uploaded_file.name, uploaded_file.getvalue())}
    try:
        response = requests.post(url, files=files, auth=auth, timeout=timeout)
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = None
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text if exc.response is not None else "HTTP error"
        if not quiet:
            st.error(f"API error ({exc.response.status_code if exc.response else 'HTTP'}): {detail}")
        return None
    except requests.RequestException as exc:
        if not quiet:
            st.error(f"Request failed: {exc}")
        return None

    try:
        return response.json()
    except ValueError:
        if not quiet:
            st.error("Invalid API response: expected JSON from backend.")
        return None


def api_request_required(
    method: str,
    path: str,
    base_url: str,
    auth: HTTPBasicAuth,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    timeout: int = 30,
) -> Dict[str, Any]:
    data = api_request(
        method,
        path,
        base_url,
        auth,
        payload=payload,
        params=params,
        timeout=timeout,
    )
    if data is None:
        st.stop()
    return data


def api_request_optional_404(
    method: str,
    path: str,
    base_url: str,
    auth: HTTPBasicAuth,
    payload: Optional[Dict[str, Any]] = None,
    params: Optional[Dict[str, Any]] = None,
    *,
    allowed_detail: str,
    timeout: int = 30,
) -> Optional[Dict[str, Any]]:
    url = f"{base_url}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            json=payload,
            params=params,
            auth=auth,
            timeout=timeout,
        )
        if response.status_code == 404:
            detail = None
            try:
                detail_payload = response.json()
                detail = detail_payload.get("detail") if isinstance(detail_payload, dict) else None
            except ValueError:
                detail = response.text
            if allowed_detail and detail == allowed_detail:
                return None
            st.error(f"API error (404): {detail or 'Not found'}")
            st.stop()
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = None
        try:
            detail = exc.response.json()
        except Exception:
            detail = exc.response.text if exc.response is not None else "HTTP error"
        st.error(f"API error ({exc.response.status_code if exc.response else 'HTTP'}): {detail}")
        st.stop()
    except requests.RequestException as exc:
        st.error(f"Request failed: {exc}")
        st.stop()

    try:
        return response.json()
    except ValueError:
        st.error("Invalid API response: expected JSON from backend.")
        st.stop()


def validate_payload_or_stop(
    payload: Any,
    validator: Callable[..., T],
    *args: Any,
    **kwargs: Any,
) -> T:
    try:
        return validator(payload, *args, **kwargs)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()


def ping_backend(api_base: str, auth: HTTPBasicAuth) -> Tuple[bool, str, Optional[Dict[str, Any]], Optional[str]]:
    """Try health/version endpoints and return success plus last error detail."""
    last_error: Optional[str] = None
    for ep in ["/health", "/version"]:
        url = f"{api_base}{ep}"
        try:
            resp = requests.get(url, auth=auth, timeout=8)
            resp.raise_for_status()
            try:
                return True, ep, resp.json(), None
            except ValueError:
                return True, ep, {"raw": resp.text}, None
        except requests.RequestException as exc:
            last_error = str(exc)
            continue
    return False, "", None, last_error
