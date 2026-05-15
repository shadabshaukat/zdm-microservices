from __future__ import annotations

from typing import Any, Dict, List

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_dbconnections_response,
    validate_projects_response,
    validate_run_job_response,
)
from streamlit_shared.context import AppContext
from streamlit_shared.db_types import is_adb_database_type
from streamlit_shared.job_form import (
    SELECT_WALLET,
    JobFieldSpec,
    collect_job_parameters,
    job_form_state_keys,
    profile_job_field_specs,
    profile_job_section_field_specs,
    wallet_name_for_path,
)
from streamlit_shared.job_payload import (
    compact_job_payload,
    validate_saved_job_copy_response,
    validate_saved_job_save_response,
    validate_saved_jobs_response,
)
from streamlit_shared.ui import saved_job_name
from streamlit_shared.wallet_payload import validate_credential_wallets_response

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    st.subheader("ZDM Job Definitions")
    st.caption("Define a job submission. Job name is fixed per project + run type; saved job definitions are listed on the ZDM Job Submission page.")

    projects_resp = validate_payload_or_stop(
        api_request_required("get", "/projects", api_base, auth),
        validate_projects_response,
    )
    connections_resp = validate_payload_or_stop(
        api_request_required("get", "/dbconnections", api_base, auth),
        validate_dbconnections_response,
    )
    project_names = list(projects_resp.keys())
    # saved jobs (for auto-load matching project+run_type)
    saved_jobs_raw = api_request_required("get", "/saved-jobs", api_base, auth)
    saved_jobs_resp = validate_payload_or_stop(saved_jobs_raw, validate_saved_jobs_response)
    # wallets for -sourcesyswallet dropdown
    cred_wallets_resp = api_request_required("get", "/credential-wallets", api_base, auth)
    wallet_map_runjob = validate_payload_or_stop(cred_wallets_resp, validate_credential_wallets_response)
    wallet_options_runjob = [SELECT_WALLET] + list(wallet_map_runjob.keys())

    sel_l, sel_r = st.columns([1, 1], vertical_alignment="top")

    with sel_l:
        project = st.selectbox(
            "Project",
            ["-- Select project --"] + project_names,
            key="runjob_project",
        )
    with sel_r:
        run_type = st.selectbox(
            "Run type",
            ["EVAL", "MIGRATE"],
            index=0,
            key="runjob_run_type",
        )

    # Pending load from ZDM Job Submission page (explicit load button)
    pending_load = st.session_state.pop("runjob_load_pending", "")

    if project == "-- Select project --":
        st.info("Select a project to start.")
        st.stop()

    def _blank(v: Any) -> bool:
        return v is None or (isinstance(v, str) and not v.strip())

    proj_obj = projects_resp.get(project)
    if not isinstance(proj_obj, dict):
        st.error(f"GET /projects API contract error: selected project '{project}' is missing.")
        st.stop()
    project_migration_method = str(proj_obj.get("migration_method") or "").strip().upper()
    if not project_migration_method:
        st.error("Project migration_method is required in projects.json before creating a job.")
        st.stop()
    if project_migration_method != "OFFLINE_LOGICAL":
        st.error(f"ZDM Job Definitions currently supports OFFLINE_LOGICAL only. Project migration_method is {project_migration_method}.")
        st.stop()
    migration_type = project_migration_method

    auto_job_key = f"{project}:{run_type}".lower()
    auto_load_state_key = "runjob_auto_loaded_key"
    form_state_missing = not any(key in st.session_state for key in job_form_state_keys(project_migration_method))
    should_auto_load = bool(pending_load) or st.session_state.get(auto_load_state_key) != auto_job_key or form_state_missing
    for name, job in saved_jobs_resp.items():
        is_auto_match = str(job.get("project")) == project and (job.get("run_type") or "").upper() == run_type
        if (pending_load == name) or (should_auto_load and is_auto_match):
            st.session_state["runjob_rsp"] = job.get("rsp") or f"{project}.rsp"
            job_parameters = job["job_parameters"]
            for spec in profile_job_field_specs(project_migration_method):
                value = job_parameters.get(spec.key) or ""
                if spec.control == "wallet":
                    value = wallet_name_for_path(value, wallet_map_runjob)
                st.session_state[spec.state_key] = value
            st.session_state["runjob_advisor_mode"] = job.get("advisor_mode") or "NONE"
            st.session_state["runjob_flow_control"] = job.get("flow_control") or "NONE"
            st.session_state["runjob_flow_phase"] = job.get("flow_phase") or ""
            st.session_state["runjob_genfixup"] = job.get("genfixup") or ""
            st.session_state["runjob_ignore"] = job.get("ignore") or []
            st.session_state["runjob_schedule_now"] = True if (job.get("schedule") or "").upper() == "NOW" else False
            st.session_state["runjob_schedule_text"] = "" if st.session_state.get("runjob_schedule_now") else (job.get("schedule") or "")
            st.session_state["runjob_listphases"] = bool(job.get("listphases"))
            st.session_state["runjob_custom_args"] = "\n".join(job.get("custom_args") or [])
            st.session_state[auto_load_state_key] = auto_job_key
            break

    job_copy_candidates: List[str] = []
    for candidate_project in project_names:
        if candidate_project == project:
            continue
        candidate_record = projects_resp.get(candidate_project)
        candidate_method = str(candidate_record.get("migration_method") or "").strip().upper()
        candidate_job = saved_jobs_resp.get(saved_job_name(candidate_project, run_type))
        if (
            candidate_method == project_migration_method
            and candidate_job is not None
            and str(candidate_job.get("project") or "") == candidate_project
            and str(candidate_job.get("run_type") or "").strip().upper() == run_type
        ):
            job_copy_candidates.append(candidate_project)

    target_conn_name = proj_obj.get("target_connection") or proj_obj.get("target") or ""
    target_db_type = ""
    if target_conn_name:
        target_conn = connections_resp.get(target_conn_name)
        if not isinstance(target_conn, dict):
            st.error(f"GET /dbconnections API contract error: project target connection '{target_conn_name}' is missing.")
            st.stop()
        target_db_type = target_conn.get("db_type", "") or ""

    rsp_value = proj_obj.get("rsp")
    default_rsp_name = rsp_value.strip() if isinstance(rsp_value, str) and rsp_value.strip() else f"{project}.rsp"
    if _blank(st.session_state.get("runjob_rsp")):
        st.session_state["runjob_rsp"] = default_rsp_name

    auto_base = saved_job_name(project, run_type)
    job_key = "runjob_job_name"
    st.session_state[job_key] = auto_base

    # Always keep RSP/job name in sync, no user edits
    st.session_state["runjob_rsp"] = default_rsp_name
    st.session_state[job_key] = auto_base

    col_top_a, col_top_b = st.columns(2)
    with col_top_a:
        st.text_input(
            "Response file name",
            key="runjob_rsp",
            help="Auto-derived from project",
            disabled=True,
        )
    with col_top_b:
        st.text_input(
            "Job name",
            key=job_key,
            help="Fixed: <project>_<eval|migrate>",
            disabled=True,
        )

    # Layout single column for create/run
    left_col = st.container()

    with left_col:
        st.markdown(f"Migration method (derived from project/response): `{migration_type}`")

        if job_copy_candidates:
            copy_source_options = ["-- Select project --"] + job_copy_candidates
            if st.session_state.get("runjob_copy_source_project") not in copy_source_options:
                st.session_state["runjob_copy_source_project"] = copy_source_options[0]

            copy_col_source, copy_col_action = st.columns([3, 1], vertical_alignment="bottom")
            with copy_col_source:
                copy_source_project = st.selectbox(
                    "Copy from project",
                    copy_source_options,
                    key="runjob_copy_source_project",
                )
            with copy_col_action:
                copy_job_clicked = st.button(
                    "Copy definition",
                    key="runjob_copy_definition_btn",
                    disabled=copy_source_project == "-- Select project --",
                    width='stretch',
                )

            if copy_job_clicked:
                copy_payload = {
                    "source_project": copy_source_project,
                    "target_project": project,
                    "migration_method": project_migration_method,
                    "run_type": run_type,
                }
                copy_resp = api_request("post", "/saved-jobs/copy", api_base, auth, payload=copy_payload)
                if copy_resp is not None:
                    expected_job_name = saved_job_name(project, run_type)
                    validate_payload_or_stop(
                        copy_resp,
                        validate_saved_job_copy_response,
                        expected_source_project=copy_source_project,
                        expected_target_project=project,
                        expected_method=project_migration_method,
                        expected_run_type=run_type,
                        expected_name=expected_job_name,
                    )
                    st.session_state["runjob_load_pending"] = expected_job_name
                    st.rerun()
        else:
            st.caption("No same-method same-run-type job definitions available.")

        if migration_type == "OFFLINE_LOGICAL":
            with st.expander("ZDM CLI args (Logical Offline)", expanded=True):
                source_specs = profile_job_section_field_specs(project_migration_method, "source_database")
                target_specs = profile_job_section_field_specs(project_migration_method, "target_database")
                col_opt_a, col_opt_b = st.columns(2)
                with col_opt_a:
                    st.markdown("##### Source")
                    _render_job_fields(source_specs, wallet_options_runjob, wallet_map_runjob)
                with col_opt_b:
                    st.markdown("##### Target")
                    if not is_adb_database_type(target_db_type):
                        _render_job_fields(target_specs, wallet_options_runjob, wallet_map_runjob)
                    else:
                        st.caption("Target SSH arguments are not needed for Autonomous Database targets.")

                st.divider()
                advisor_mode = st.selectbox("Advisor mode", ["NONE", "ADVISOR", "IGNORE_ADVISOR", "SKIP_ADVISOR"], key="runjob_advisor_mode")
                flow_control = st.selectbox("Flow control", ["NONE", "PAUSE_AFTER", "STOP_AFTER"], key="runjob_flow_control")
                flow_phase = st.text_input("Phase (for pause/stop)", key="runjob_flow_phase", help="Required when flow control is pause/stop")
                genfixup = st.selectbox("Genfixup", ["", "YES", "NO"], key="runjob_genfixup")
                ignore_opts = ["ALL","WARNING","PATCH_CHECK","NLS_CHECK","NLS_NCHAR_CHECK","ENDIAN_CHECK","VAULT_CHECK","DB_NK_CACHE_SIZE_CHECK"]
                ignore_sel = st.multiselect("Ignore checks", ignore_opts, key="runjob_ignore")
                schedule_now = st.checkbox("Schedule NOW", value=st.session_state.get("runjob_schedule_now", False), key="runjob_schedule_now")
                schedule_val = ""
                if schedule_now:
                    schedule_val = "NOW"
                else:
                    schedule_val = st.text_input("Schedule (ISO-8601)", key="runjob_schedule_text", help="YYYY-MM-DDTHH:MM:SS±HH")
                listphases = st.checkbox("List phases (-listphases)", value=False, key="runjob_listphases")
                custom_args_text = st.text_area("Custom args (one per line, full token e.g. '-myflag value')", key="runjob_custom_args")

        else:
            st.info(f"Migration type {migration_type} not yet wired; UI placeholder only.")
            advisor_mode = st.session_state.get("runjob_advisor_mode", "NONE")
            flow_control = st.session_state.get("runjob_flow_control", "NONE")
            flow_phase = st.session_state.get("runjob_flow_phase", "")
            genfixup = st.session_state.get("runjob_genfixup", "")
            ignore_sel = st.session_state.get("runjob_ignore", [])
            schedule_now = False
            schedule_val = st.session_state.get("runjob_schedule_text", "")
            listphases = st.session_state.get("runjob_listphases", False)
            custom_args_text = st.session_state.get("runjob_custom_args", "")

        action_col1, action_col2 = st.columns([0.4, 0.6])
        with action_col1:
            save_and_run = st.button("Save & Run", type="primary")
        with action_col2:
            save_only = st.button("Save only", type="secondary", width='stretch')
        run_clicked = False

    if save_only or save_and_run:
        payload_save = {
            "name": st.session_state.get(job_key),
            "project": project,
            "rsp": (st.session_state.get("runjob_rsp") or "").strip() or None,
            "run_type": st.session_state.get("runjob_run_type"),
            "job_parameters": collect_job_parameters(project_migration_method, st.session_state, wallet_map_runjob),
            "advisor_mode": advisor_mode,
            "flow_control": flow_control,
            "flow_phase": flow_phase,
            "genfixup": genfixup or None,
            "ignore": ignore_sel or None,
            "schedule": schedule_val or None,
            "listphases": listphases,
            "custom_args": [ln.strip() for ln in (custom_args_text or "").splitlines() if ln.strip()],
        }
        payload_save = compact_job_payload(payload_save)
        resp_save = api_request("post", "/saved-jobs", api_base, auth, payload=payload_save)
        if resp_save:
            try:
                validate_saved_job_save_response(resp_save, payload_save["name"])
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
            st.success(f"Saved job '{payload_save['name']}'.")
            if save_only and not save_and_run:
                st.rerun()
            else:
                run_clicked = True

    if run_clicked:
        rsp_name = (st.session_state.get("runjob_rsp") or "").strip()
        if not rsp_name:
            st.error("Response file name is required.")
        else:
            payload = {
                "project": project,
                "run_type": run_type,
                "rsp": rsp_name,
                "job_parameters": collect_job_parameters(project_migration_method, st.session_state, wallet_map_runjob),
                "advisor_mode": advisor_mode,
                "flow_control": flow_control,
                "flow_phase": flow_phase or None,
                "genfixup": genfixup or None,
                "ignore": ignore_sel or None,
                "schedule": schedule_val or None,
                "listphases": listphases,
                "custom_args": [ln.strip() for ln in (custom_args_text or "").splitlines() if ln.strip()],
            }
            payload = compact_job_payload(payload)

            data = api_request("post", "/jobs", api_base, auth, payload=payload)
            if data:
                validated = validate_payload_or_stop(data, validate_run_job_response)
                st.success("Job submitted.")
                st.session_state["last_job_submission_result"] = validated
                if validated.get("job_id"):
                    st.session_state["last_job_id"] = validated["job_id"]

    # -----------------------------
    # ZDM Job Submission page (saved definitions only)
    # -----------------------------


def _render_job_fields(
    specs: List[JobFieldSpec],
    wallet_options: List[str],
    wallet_map: Dict[str, str],
) -> None:
    for spec in specs:
        if spec.control == "wallet":
            current = st.session_state.get(spec.state_key)
            if current not in wallet_options:
                st.session_state[spec.state_key] = wallet_name_for_path(current, wallet_map)
            st.selectbox(spec.label, wallet_options, key=spec.state_key)
        else:
            st.text_input(spec.label, key=spec.state_key)
