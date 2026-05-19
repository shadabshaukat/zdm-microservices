from __future__ import annotations

import html
from typing import List

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_job_ids_response,
    validate_job_query_response,
    validate_joblog_read_response,
    validate_joblogs_response,
)
from streamlit_shared.console_layout import render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.job_progress import (
    query_result_should_auto_refresh,
    render_job_progress,
    should_auto_refresh_status,
)
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import query_param


def render_log_line_html(line: str) -> str:
    escaped = html.escape(str(line))
    upper = str(line).upper()
    if "ORA-" in upper or "ERROR" in upper:
        return f"<span style='color:#ff5555;font-weight:600'>{escaped}</span>"
    if "WARN" in upper:
        return f"<span style='color:#f0a500'>{escaped}</span>"
    return escaped


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Execute & Observe",
        "ZDM Job Monitoring",
        "Monitor ZDM job status, phases, result files, and generated logs.",
    )
    render_workflow_back_button()

    deep_link_job_id = query_param("job_id").strip()
    deep_link_view = "Logs" if query_param("view").lower() == "logs" else "Latest result"
    if deep_link_job_id:
        deep_link_key = f"{deep_link_job_id}:{deep_link_view}"
        if st.session_state.get("jobs_deep_link_key") != deep_link_key:
            st.session_state["jobs_manual_id"] = deep_link_job_id
            st.session_state["last_job_id"] = deep_link_job_id
            st.session_state["jobs_view"] = deep_link_view
            if deep_link_view == "Logs":
                st.session_state["jobs_auto_open_log"] = True
            data = api_request_required("get", f"/jobs/{deep_link_job_id}", api_base, auth)
            st.session_state["last_job_query_status"] = validate_payload_or_stop(data, validate_job_query_response)
            st.session_state["jobs_autorefresh_should_poll"] = True
            st.session_state["jobs_deep_link_key"] = deep_link_key

    # -----------------------------
    # Query + Results/Logs (stacked)
    # -----------------------------
    with st.container(border=True):
        st.markdown("#### Query job")
        st.caption("Enter a Job ID, or pick one you ran recently.")

        def _apply_saved_jobid():
            val = (st.session_state.get("jobs_saved_pick") or "").strip()
            if val:
                st.session_state["jobs_manual_id"] = val
            st.session_state["jobs_saved_pick"] = ""

        job_ids_resp = api_request("get", "/jobs/ids", api_base, auth, quiet=True)
        job_ids_list = (
            validate_payload_or_stop(job_ids_resp, validate_job_ids_response)
            if job_ids_resp is not None
            else []
        )

        row = st.columns([0.55, 0.25, 0.20], vertical_alignment="bottom")
        with row[0]:
            job_id = st.text_input("Job ID", key="jobs_manual_id", placeholder="e.g. 26")
        with row[1]:
            if job_ids_list:
                with st.popover("Pick saved"):
                    st.selectbox(
                        "Saved job IDs",
                        [""] + job_ids_list,
                        key="jobs_saved_pick",
                        on_change=_apply_saved_jobid,
                    )
            else:
                if job_ids_resp is None:
                    st.caption("Recent Job IDs unavailable")
                else:
                    st.caption("No recent Job IDs")
        with row[2]:
            query_clicked = st.button("Query", type="primary", width='stretch')

        if query_clicked:
            job_id_clean = (job_id or "").strip()
            if not job_id_clean:
                st.error("Please enter a Job ID.")
            else:
                data = api_request_required("get", f"/jobs/{job_id_clean}", api_base, auth)
                st.session_state["last_job_id"] = job_id_clean
                st.session_state["last_job_query_status"] = validate_payload_or_stop(data, validate_job_query_response)
                st.session_state["jobs_autorefresh_should_poll"] = True
                st.session_state["jobs_view"] = "Latest result"

    # -----------------------------
    # Latest result / Logs (tabs below query)
    # -----------------------------
    if "jobs_view" not in st.session_state:
        st.session_state["jobs_view"] = "Latest result"
    jobs_view = st.radio("View", ["Latest result", "Logs"], horizontal=True, key="jobs_view")

    last_job_id = (st.session_state.get("last_job_id") or "").strip()

    def _poll_latest(job_id: str) -> None:
        if not job_id:
            return
        data = api_request_required("get", f"/jobs/{job_id}", api_base, auth)
        st.session_state["last_job_query_status"] = validate_payload_or_stop(data, validate_job_query_response)

    if jobs_view == "Latest result":
        st.markdown("#### Latest result")
        auto_refresh = st.toggle("Auto-refresh (every 5 seconds)", value=False, key="jobs_autorefresh_latest")

        def _render_latest(should_poll: bool):
            if not last_job_id:
                st.info("No job queried yet.")
                return

            cached_status = st.session_state.get("last_job_query_status")
            if should_poll and isinstance(cached_status, dict):
                should_poll = query_result_should_auto_refresh(cached_status)

            if should_poll or "last_job_query_status" not in st.session_state:
                _poll_latest(last_job_id)

            last_status = validate_payload_or_stop(
                st.session_state.get("last_job_query_status"),
                validate_job_query_response,
            )
            parsed = render_job_progress(last_job_id, last_status)
            st.session_state["jobs_autorefresh_should_poll"] = should_auto_refresh_status(
                parsed.get("zdm_status") or ""
            )
            result_file = parsed.get("result_file")
            if result_file:
                preferred_name = str(result_file).rstrip("/").rsplit("/", 1)[-1]
                st.session_state["jobs_preferred_log_file"] = preferred_name
                st.session_state["log_select"] = preferred_name
                st.session_state["jobs_auto_open_log"] = True

        auto_refresh_active = (
            auto_refresh
            and last_job_id
            and st.session_state.get("jobs_autorefresh_should_poll", True)
        )
        if auto_refresh_active and hasattr(st, "fragment"):
            @st.fragment(run_every=5)
            def _latest_fragment():
                _render_latest(should_poll=True)
            _latest_fragment()
        else:
            if auto_refresh_active and not hasattr(st, "fragment"):
                st.caption("Auto-refresh requires a newer Streamlit version (st.fragment).")
            _render_latest(should_poll=False)

    else:
        st.markdown("#### Job logs")

        job_id_logs = str(st.session_state.get("last_job_id", "") or "").strip()
        log_files: List[str] = []
        if job_id_logs:
            logs = validate_payload_or_stop(
                api_request_required("get", "/joblogs", api_base, auth, params={"job_id": job_id_logs}),
                validate_joblogs_response,
                expected_job_id=job_id_logs,
            )
            for entry in logs:
                log_files.append(entry["name"])
            if not log_files:
                st.warning(f"No log files found for job {job_id_logs}.")
        else:
            st.info("Query a Job ID above to load its logs.")

        if not log_files:
            st.stop()

        preferred = (st.session_state.get("jobs_preferred_log_file") or "").strip()
        if preferred and preferred in log_files:
            if st.session_state.get("log_select") != preferred:
                st.session_state["log_select"] = preferred

        top_l, top_r = st.columns([0.72, 0.28], vertical_alignment="bottom")
        with top_l:
            selected_log = st.selectbox("Select log file", log_files, key="log_select")
        with top_r:
            tail_on = st.toggle("Tail (5s, last 400 lines)", value=False, key="jobs_tail_on")

        def _render_log(content: str) -> None:
            colored = "<br>".join(render_log_line_html(l) for l in content.splitlines())
            st.markdown(
                "<div style='background:#0b0e14;color:#e8e8e8;padding:12px 14px;"
                "border-radius:8px;overflow:auto;max-height:520px;font-family:SFMono-Regular,Consolas,Menlo,monospace;"
                "font-size:12px;line-height:1.4;border:1px solid #1f2430;'>"
                f"{colored}</div>",
                unsafe_allow_html=True,
            )

        def _fetch_and_show_log() -> None:
            resp = api_request_required(
                "post",
                "/joblogs/read",
                api_base,
                auth,
                payload={"job_id": job_id_logs, "name": selected_log},
            )
            validated = validate_payload_or_stop(
                resp,
                validate_joblog_read_response,
                expected_job_id=job_id_logs,
                expected_name=selected_log,
            )
            content = validated.get("content", "") or ""
            if tail_on and content:
                lines = content.splitlines()[-400:]
                content = "\n".join(lines)
            _render_log(content)
            st.download_button("Download as text", data=content, file_name=selected_log, key="dl-log")

        auto_open = bool(st.session_state.get("jobs_auto_open_log"))
        if auto_open:
            st.session_state["jobs_auto_open_log"] = False

        if tail_on and hasattr(st, "fragment"):
            @st.fragment(run_every=5)
            def _tail_fragment():
                _fetch_and_show_log()
            _tail_fragment()
        else:
            if auto_open or st.button("View selected log", type="primary"):
                _fetch_and_show_log()
