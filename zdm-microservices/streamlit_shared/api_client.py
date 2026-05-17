from __future__ import annotations

import json
from typing import Any, Callable, Dict, Optional, Tuple, TypeVar

import requests
import streamlit as st
from requests.auth import HTTPBasicAuth

T = TypeVar("T")


def _detail_text(detail: Any) -> str:
    if detail is None:
        return ""
    if isinstance(detail, str):
        return detail
    try:
        return json.dumps(detail, indent=2, sort_keys=True)
    except TypeError:
        return str(detail)


def _friendly_http_error_message(status_code: Optional[int], detail: Any) -> str:
    detail_text = _detail_text(detail)
    if "PRGT-1038" in detail_text or "ZDM service is not running" in detail_text:
        return "ZDM service is not running or cannot be reached. Start the ZDM service, then try again."
    if status_code == 404:
        return "ZEUS backend could not find the requested item."
    if status_code:
        return f"ZEUS backend could not complete the request (HTTP {status_code})."
    return "ZEUS backend could not complete the request."


def _show_backend_error(message: str, detail: Any = None) -> None:
    st.error(message)
    detail_text = _detail_text(detail)
    if detail_text and _has_streamlit_context():
        with st.expander("Technical details", expanded=False):
            st.code(detail_text)


def _has_streamlit_context() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx(suppress_warning=True) is not None
    except Exception:
        return True


def _response_error_detail(response: Any) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text if response is not None else "HTTP error"


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
        detail = _response_error_detail(exc.response)
        if not quiet:
            status_code = exc.response.status_code if exc.response is not None else None
            _show_backend_error(_friendly_http_error_message(status_code, detail), detail)
        return None
    except requests.RequestException as exc:
        if not quiet:
            _show_backend_error(
                "ZEUS backend is not reachable. Check ZEUS Settings and make sure the backend service is running.",
                str(exc),
            )
        return None

    try:
        return response.json()
    except ValueError:
        if not quiet:
            _show_backend_error("ZEUS backend returned a response this page cannot read. Expected JSON.")
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
        detail = _response_error_detail(exc.response)
        if not quiet:
            status_code = exc.response.status_code if exc.response is not None else None
            _show_backend_error(_friendly_http_error_message(status_code, detail), detail)
        return None
    except requests.RequestException as exc:
        if not quiet:
            _show_backend_error(
                "ZEUS backend is not reachable. Check ZEUS Settings and make sure the backend service is running.",
                str(exc),
            )
        return None

    try:
        return response.json()
    except ValueError:
        if not quiet:
            _show_backend_error("ZEUS backend returned a response this page cannot read. Expected JSON.")
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
            _show_backend_error(_friendly_http_error_message(404, detail or "Not found"), detail or "Not found")
            st.stop()
        response.raise_for_status()
    except requests.HTTPError as exc:
        detail = _response_error_detail(exc.response)
        status_code = exc.response.status_code if exc.response is not None else None
        _show_backend_error(_friendly_http_error_message(status_code, detail), detail)
        st.stop()
    except requests.RequestException as exc:
        _show_backend_error(
            "ZEUS backend is not reachable. Check ZEUS Settings and make sure the backend service is running.",
            str(exc),
        )
        st.stop()

    try:
        return response.json()
    except ValueError:
        _show_backend_error("ZEUS backend returned a response this page cannot read. Expected JSON.")
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
        _show_backend_error(
            "ZEUS received an unexpected response from the backend. Refresh the page or restart the backend if this continues.",
            str(exc),
        )
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
