from __future__ import annotations

from typing import Any, Dict

import streamlit as st


def render_job_result(payload: Dict[str, Any]):
    if not payload:
        return
    if not isinstance(payload, dict):
        st.text_area("Command output", value=str(payload), height=260, disabled=True)
        return

    st.markdown("#### API operation result")

    job_id = payload.get("job_id")
    script_path = payload.get("script_path")
    api_status = payload.get("status")
    if job_id:
        st.caption(f"Submitted ZDM job ID: {job_id}")
    if api_status:
        st.caption(f"API operation status: {api_status}")
    if script_path:
        st.caption(f"Script: {script_path}")

    cmd_lines = payload.get("command")
    if cmd_lines:
        st.markdown("##### ZDM CLI command")
        st.code("\n".join(cmd_lines) if isinstance(cmd_lines, list) else str(cmd_lines), language="bash")

    output = payload.get("output") or payload.get("message") or ""
    if output:
        st.markdown("##### Command output")
        st.text_area(
            "Command output",
            value=str(output),
            height=260,
            disabled=True,
            label_visibility="collapsed",
        )

    extra = {
        key: value
        for key, value in payload.items()
        if key not in {"status", "script_path", "output", "message", "command", "job_id"}
    }
    if extra:
        with st.expander("Additional API details", expanded=False):
            st.json(extra)
