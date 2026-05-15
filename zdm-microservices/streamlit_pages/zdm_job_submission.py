from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import validate_run_job_response
from streamlit_shared.context import AppContext
from streamlit_shared.job_result import render_job_result
from streamlit_shared.job_payload import (
    job_payload_from_saved_job,
    validate_saved_job_delete_response,
    validate_saved_jobs_response,
)
from streamlit_shared.ui import st_df_safe

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    st.subheader("ZDM Job Submission")
    st.caption("Pick a saved job definition, view it, preview the command, and run it.")

    saved_jobs_raw = api_request_required("get", "/saved-jobs", api_base, auth)
    saved_jobs_resp = validate_payload_or_stop(saved_jobs_raw, validate_saved_jobs_response)
    saved_job_names = ["-- Select saved job --"] + list(saved_jobs_resp.keys())

    saved_sel = st.selectbox("Saved job definitions", saved_job_names, key="runjob_saved_select")
    c2, c3, c4 = st.columns([0.34, 0.33, 0.33])
    with c2:
        if st.button("View", key="runjob_view_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                st.session_state["runjob_view_job"] = saved_sel
                st.rerun()
    with c3:
        if st.button("Run", key="runjob_run_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                job = saved_jobs_resp.get(saved_sel)
                if job:
                    try:
                        payload = job_payload_from_saved_job(job)
                    except ValueError as exc:
                        st.error(str(exc))
                        st.stop()
                    data = api_request("post", "/jobs", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(data, validate_run_job_response)
                        st.success(f"Ran saved job '{saved_sel}'")
                        st.session_state["last_job_submission_result"] = validated
                        if validated.get("job_id"):
                            st.session_state["last_job_id"] = validated["job_id"]
    with c4:
        if st.button("Delete", key="runjob_delete_saved_btn", width='stretch'):
            if saved_sel != "-- Select saved job --":
                resp = api_request("delete", f"/saved-jobs/{saved_sel}", api_base, auth)
                if resp:
                    validate_payload_or_stop(resp, validate_saved_job_delete_response)
                    st.success(f"Deleted saved job '{saved_sel}'")
                    st.rerun()

    view_job_name = st.session_state.pop("runjob_view_job", "")
    if view_job_name and view_job_name in saved_jobs_resp:
        vjob = saved_jobs_resp.get(view_job_name, {})
        df_view = pd.DataFrame(
            [
                {"Field": k, "Value": "" if v is None else v}
                for k, v in vjob.items()
            ]
        )
        st_df_safe(df_view, hide_index=True, width='stretch')
        # Get live command preview via dry_run
        try:
            payload_preview = job_payload_from_saved_job(vjob, dry_run=True)
        except ValueError as exc:
            st.error(str(exc))
            st.stop()
        cmd_resp = api_request("post", "/jobs", api_base, auth, payload=payload_preview)
        if cmd_resp:
            validated_preview = validate_payload_or_stop(cmd_resp, validate_run_job_response, dry_run=True)
            cmd_lines = validated_preview.get("command")
            if cmd_lines:
                st.caption("ZDM CLI command (preview):")
                st.code("\n".join(cmd_lines) if isinstance(cmd_lines, list) else str(cmd_lines), language="bash")
            else:
                st.info("No command returned for this saved job.")

    # -----------------------------
    # Last submission (full width)
    # -----------------------------
    st.markdown("### Last submission")
    last_submission_result = st.session_state.get("last_job_submission_result")
    if last_submission_result:
        validated_submission = validate_payload_or_stop(last_submission_result, validate_run_job_response)
        render_job_result(validated_submission)
    else:
        st.info("No job submitted yet.")
