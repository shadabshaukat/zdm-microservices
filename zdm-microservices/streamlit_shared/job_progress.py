from __future__ import annotations

import re
from typing import Any, Dict, List, Mapping, Tuple

import streamlit as st


AUTO_REFRESH_STATUSES = {"EXECUTING", "IN_PROGRESS", "PENDING", "RUNNING", "SCHEDULED", "STARTED"}


def parse_zdm_output(out: str) -> Dict[str, Any]:
    """Best-effort parsing of ZDM output text returned by the job query endpoint."""
    if not out:
        return {}
    parsed: Dict[str, Any] = {}

    match = re.search(r"\bJob ID\s*:\s*(\S+)", out)
    if match:
        parsed["job_id"] = match.group(1)

    match = re.search(r"\bJob Type\s*:\s*\"?([A-Za-z0-9_\-]+)\"?", out)
    if match:
        parsed["job_type"] = match.group(1)

    match = re.search(r"\bCurrent status\s*:\s*([A-Za-z0-9_\-]+)", out)
    if match:
        parsed["zdm_status"] = match.group(1).upper()

    match = re.search(r"\bResult file path\s*:\s*\"?([^\"\n]+)\"?", out)
    if match:
        parsed["result_file"] = match.group(1).strip()

    phases: List[Tuple[str, str]] = []
    for line in out.splitlines():
        phase_match = re.match(r"^(ZDM_[A-Z0-9_]+)\s+\.+\s+([A-Z]+)\s*$", line.strip())
        if phase_match:
            phases.append((phase_match.group(1), phase_match.group(2)))
    if phases:
        parsed["phases"] = phases

    return parsed


def status_badge(status: str) -> Tuple[str, str]:
    """Return (label, kind) where kind is a Streamlit callout style."""
    normalized = (status or "").upper()
    if normalized == "SUCCEEDED":
        return normalized, "success"
    if normalized in ("FAILED", "ERROR"):
        return normalized, "error"
    if normalized in {"EXECUTING", "IN_PROGRESS", "RUNNING", "STARTED"}:
        return normalized, "warning"
    if normalized in ("PENDING", "SCHEDULED", "PAUSED"):
        return normalized, "info"
    return (normalized or "-"), "info"


def should_auto_refresh_status(status: str) -> bool:
    return (status or "").upper() in AUTO_REFRESH_STATUSES


def query_result_should_auto_refresh(query_result: Mapping[str, Any]) -> bool:
    parsed = parse_zdm_output(str(query_result.get("output") or ""))
    return should_auto_refresh_status(parsed.get("zdm_status") or "")


def render_job_progress(job_id: str, query_result: Mapping[str, Any]) -> Dict[str, Any]:
    out_text = str(query_result.get("output") or "")
    parsed = parse_zdm_output(out_text)
    zdm_status = parsed.get("zdm_status") or "-"
    badge_label, badge_kind = status_badge(zdm_status)

    cols = st.columns([1.05, 0.85, 1.0])
    with cols[0]:
        st.metric("Job ID", parsed.get("job_id") or job_id)
    with cols[1]:
        st.metric("Job Type", parsed.get("job_type") or "-")
    with cols[2]:
        st.metric("ZDM Status", badge_label)

    if badge_kind == "error":
        st.error("ZDM job failed.")
    elif badge_kind == "success":
        st.success("ZDM job completed successfully.")
    elif badge_kind == "warning":
        st.warning("ZDM job is still running.")
    elif zdm_status in ("PENDING", "SCHEDULED"):
        st.info("ZDM job is waiting to start.")
    elif zdm_status == "PAUSED":
        st.info("ZDM job is paused.")
    else:
        st.info("ZDM job status is not available yet.")

    phases = parsed.get("phases") or []
    if phases:
        with st.expander("Phases", expanded=False):
            for name, state in phases:
                st.write(f"- **{name}**: {state}")

    with st.expander("ZDM query output", expanded=False):
        if out_text:
            st.text_area(
                "ZDM query output",
                value=out_text,
                height=260,
                disabled=True,
                label_visibility="collapsed",
            )
        else:
            st.info("No ZDM output text returned.")

    return parsed
