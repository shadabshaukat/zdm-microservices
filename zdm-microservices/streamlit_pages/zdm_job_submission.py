from __future__ import annotations

from typing import Any, Mapping, MutableMapping

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import validate_job_query_response, validate_run_job_response
from streamlit_shared.context import AppContext
from streamlit_shared.job_progress import (
    query_result_should_auto_refresh,
    render_job_progress,
    should_auto_refresh_status,
)
from streamlit_shared.job_payload import (
    job_payload_from_saved_job,
    validate_saved_job_delete_response,
    validate_saved_jobs_response,
)

RUNJOB_SUBMISSION_RESULT_KEY = "runjob_last_submission_result"
RUNJOB_SUBMISSION_NAME_KEY = "runjob_last_submission_name"
RUNJOB_PROGRESS_KEYS = (
    "runjob_show_current_progress",
    RUNJOB_SUBMISSION_RESULT_KEY,
    RUNJOB_SUBMISSION_NAME_KEY,
    "runjob_current_job_autorefresh",
    "runjob_current_job_should_refresh",
    "runjob_current_job_query_status",
    "runjob_current_job_query_job_id",
)


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    if ctx.entering("runjob"):
        clear_current_job_progress(st.session_state)

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
                clear_current_job_progress(st.session_state)
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
                        _stop_on_saved_job_error(exc)
                    data = api_request("post", "/jobs", api_base, auth, payload=payload)
                    if data:
                        validated = validate_payload_or_stop(data, validate_run_job_response)
                        job_id = validated.get("job_id")
                        script_path = validated.get("script_path")
                        st.session_state["runjob_show_current_progress"] = True
                        if job_id:
                            st.success(f"Submitted saved job '{saved_sel}' as ZDM job {job_id}.")
                            st.session_state["last_job_id"] = job_id
                            st.session_state["runjob_current_job_autorefresh"] = True
                            st.session_state["runjob_current_job_should_refresh"] = True
                            st.session_state.pop("runjob_current_job_query_status", None)
                            st.session_state.pop("runjob_current_job_query_job_id", None)
                        else:
                            st.warning(
                                "The saved job was submitted, but ZEUS could not read the ZDM job ID "
                                "from the submission output."
                            )
                        if script_path:
                            st.caption(f"Run script: {script_path}")
                        st.session_state[RUNJOB_SUBMISSION_RESULT_KEY] = validated
                        st.session_state[RUNJOB_SUBMISSION_NAME_KEY] = saved_sel
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
        _render_saved_job_definition(view_job_name, vjob)
        # Get live command preview via dry_run
        try:
            payload_preview = job_payload_from_saved_job(vjob, dry_run=True)
        except ValueError as exc:
            _stop_on_saved_job_error(exc)
        cmd_resp = api_request("post", "/jobs", api_base, auth, payload=payload_preview)
        if cmd_resp:
            validated_preview = validate_payload_or_stop(cmd_resp, validate_run_job_response, dry_run=True)
            cmd_lines = validated_preview.get("command")
            if cmd_lines:
                st.caption("ZDM CLI command (preview):")
                st.code("\n".join(cmd_lines) if isinstance(cmd_lines, list) else str(cmd_lines), language="bash")
            else:
                st.info("No command returned for this saved job.")

    render_current_job_progress(api_base, auth)


def render_current_job_progress(api_base: str, auth: Any) -> None:
    progress_slot = st.empty()
    last_submission_result = st.session_state.get(RUNJOB_SUBMISSION_RESULT_KEY)
    if not should_show_current_job_progress(st.session_state):
        progress_slot.empty()
        return

    with progress_slot.container():
        st.markdown("### Current job progress")
        validated_submission = validate_payload_or_stop(last_submission_result, validate_run_job_response)
        submitted_job_id = (validated_submission.get("job_id") or "").strip()
        submitted_name = st.session_state.get(RUNJOB_SUBMISSION_NAME_KEY) or "saved job"
        script_path = validated_submission.get("script_path")
        if not submitted_job_id:
            st.warning("No ZDM job ID is available for the latest submission.")
            output = validated_submission.get("output") or ""
            if output:
                with st.expander("Submission output", expanded=False):
                    st.text_area(
                        "Submission output",
                        value=str(output),
                        height=220,
                        disabled=True,
                        label_visibility="collapsed",
                    )
            return

        st.caption(f"Tracking saved job '{submitted_name}' as ZDM job {submitted_job_id}.")
        if script_path:
            st.caption(f"Run script: {script_path}")

        auto_refresh = st.toggle(
            "Auto-refresh (every 5 seconds)",
            value=True,
            key="runjob_current_job_autorefresh",
        )

        def _poll_current_job() -> None:
            data = api_request_required("get", f"/jobs/{submitted_job_id}", api_base, auth)
            st.session_state["runjob_current_job_query_status"] = validate_payload_or_stop(
                data,
                validate_job_query_response,
            )
            st.session_state["runjob_current_job_query_job_id"] = submitted_job_id

        def _render_current_job(should_poll: bool) -> None:
            cached_job_id = st.session_state.get("runjob_current_job_query_job_id")
            cached_status = st.session_state.get("runjob_current_job_query_status")
            if should_poll and cached_job_id == submitted_job_id and isinstance(cached_status, dict):
                should_poll = query_result_should_auto_refresh(cached_status)

            if should_poll or cached_job_id != submitted_job_id:
                _poll_current_job()

            query_status = validate_payload_or_stop(
                st.session_state.get("runjob_current_job_query_status"),
                validate_job_query_response,
            )
            parsed = render_job_progress(submitted_job_id, query_status)
            st.session_state["runjob_current_job_should_refresh"] = should_auto_refresh_status(
                parsed.get("zdm_status") or ""
            )

        auto_refresh_active = (
            auto_refresh
            and submitted_job_id
            and st.session_state.get("runjob_current_job_should_refresh", True)
        )
        if auto_refresh_active and hasattr(st, "fragment"):
            @st.fragment(run_every=5)
            def _current_job_fragment():
                _render_current_job(should_poll=True)
            _current_job_fragment()
        else:
            if auto_refresh_active and not hasattr(st, "fragment"):
                st.caption("Auto-refresh requires a newer Streamlit version (st.fragment).")
            _render_current_job(should_poll=False)


def should_show_current_job_progress(session_state: Mapping[str, Any]) -> bool:
    return bool(
        session_state.get("runjob_show_current_progress")
        and session_state.get(RUNJOB_SUBMISSION_RESULT_KEY)
    )


def clear_current_job_progress(session_state: MutableMapping[str, Any]) -> None:
    for key in RUNJOB_PROGRESS_KEYS:
        session_state.pop(key, None)


def _render_saved_job_definition(name: str, job: Mapping[str, Any]) -> None:
    st.markdown("#### Saved job definition")
    with st.container(border=True):
        st.markdown(f"**{name}**")
        cols = st.columns(3)
        with cols[0]:
            st.caption("Project")
            st.write(job.get("project") or "-")
        with cols[1]:
            st.caption("Run type")
            st.write(job.get("run_type") or "-")
        with cols[2]:
            st.caption("Response file")
            st.write(job.get("rsp") or "-")

        _render_definition_lines(
            "ZDM CLI arguments",
            [
                (f"-{key}", value)
                for key, value in (job.get("job_parameters") or {}).items()
                if value not in (None, "", [])
            ],
            expanded=True,
        )
        _render_definition_lines(
            "Run controls",
            [
                (key, job.get(key))
                for key in [
                    "advisor_mode",
                    "flow_control",
                    "flow_phase",
                    "genfixup",
                    "ignore",
                    "schedule",
                    "listphases",
                    "custom_args",
                ]
                if job.get(key) not in (None, "", [])
            ],
            expanded=False,
        )


def _render_definition_lines(title: str, rows: list[tuple[str, Any]], *, expanded: bool) -> None:
    with st.expander(title, expanded=expanded):
        if not rows:
            st.caption("None")
            return
        for label, value in rows:
            st.text(f"{label}: {_display_value(value)}")


def _display_value(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value)
    return str(value)


def _stop_on_saved_job_error(exc: ValueError) -> None:
    st.error("ZEUS could not use this saved job definition. Recreate the job definition, then try again.")
    with st.expander("Technical details", expanded=False):
        st.code(str(exc))
    st.stop()
