from __future__ import annotations

import json
from typing import Any, Dict, List

import streamlit as st

from streamlit_shared.api_client import (
    api_request,
    api_request_optional_404,
    api_request_required,
    validate_payload_or_stop,
)
from streamlit_shared.api_payload import (
    validate_dbconnections_response,
    validate_projects_response,
)
from streamlit_shared.context import AppContext
from streamlit_shared.response_file_form import (
    SELECT_PROJECT,
    SELECT_WALLET,
    build_responsefile_payload,
    state_updates_from_rsp_content,
)
from streamlit_shared.response_file_payload import (
    validate_responsefile_preview_response,
    validate_responsefile_read_response,
    validate_responsefile_write_response,
)
from streamlit_shared.ui import render_diagnostics
from streamlit_shared.wallet_payload import validate_credential_wallet_paths_response
from streamlit_shared.response_file_sections import (
    render_responsefile_basics,
    render_responsefile_form_sections,
    render_responsefile_project_controls,
    responsefile_unavailable_message,
)


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    def clear_response_form_state(include_project: bool = False) -> None:
        keep_response_keys = set() if include_project else {"rf_project", "rf_active_project"}
        for key in list(st.session_state.keys()):
            if key.startswith("rf_") and key not in keep_response_keys:
                st.session_state.pop(key, None)
        st.session_state["rf_form_loaded_project"] = ""
        if include_project:
            st.session_state["rf_project"] = SELECT_PROJECT
            st.session_state["rf_active_project"] = ""

    if ctx.entering_response:
        clear_response_form_state(include_project=True)

    header_l, header_r = st.columns([4.5, 1.5], vertical_alignment="center")
    with header_l:
        st.markdown("## ZDM Response Files")
    with header_r:
        projects_resp = validate_payload_or_stop(
            api_request_required("get", "/projects", api_base, auth),
            validate_projects_response,
        )
        project_names = list(projects_resp.keys())
        project = st.selectbox(
            "Project",
            [SELECT_PROJECT] + project_names,
            key="rf_project",
            label_visibility="collapsed",
        )

    if project == SELECT_PROJECT:
        st.session_state["rf_active_project"] = ""
        st.info("Select a project to start.")
        st.stop()

    if st.session_state.get("rf_active_project") != project:
        st.session_state["rf_active_project"] = project
        st.session_state["rf_form_loaded_project"] = ""

    wallet_map = _load_wallet_map(api_base, auth)
    wallet_names = [SELECT_WALLET] + list(wallet_map.keys())
    connections_resp = validate_payload_or_stop(
        api_request_required("get", "/dbconnections", api_base, auth),
        validate_dbconnections_response,
    )

    if "rf_form_loaded_project" not in st.session_state:
        st.session_state["rf_form_loaded_project"] = ""

    if st.session_state.get("rf_form_loaded_project") != project:
        _apply_rsp_to_state(project, api_base, auth, wallet_map, clear_response_form_state)

    col_form, col_gap, col_preview = st.columns([1.22, 0.08, 1])
    with col_gap:
        st.write("")

    with col_form:
        expand_all = render_responsefile_project_controls(project)
        selection = render_responsefile_basics(
            project=project,
            projects_resp=projects_resp,
            connections_resp=connections_resp,
            api_base=api_base,
            auth=auth,
        )
        form_data = render_responsefile_form_sections(
            selection=selection,
            wallet_names=wallet_names,
            wallet_map=wallet_map,
            expand_all=expand_all,
        )
        environment_values = selection.derived_response_values
        effective_values = {**form_data.values, **environment_values}

        preview_payload = build_responsefile_payload(
            project=project,
            migration_type=selection.migration_type,
            migration_method=selection.selected_migration_method,
            medium=selection.medium,
            values=effective_values,
            remaps=form_data.remaps,
            additional=form_data.additional,
        )
        wallet_contract_errors = _unresolved_rsp_wallet_contract_errors(wallet_map, preview_payload)
        for error in wallet_contract_errors:
            st.error(error)

        st.divider()
        preview_request = {
            "project": project,
            "migration_method": selection.selected_migration_method,
            "values": preview_payload,
        }
        preview_lines = _compile_preview_lines(
            selection.response_method_supported,
            preview_request,
            api_base,
            auth,
        )

        existing_rsp = _load_existing_rsp(project, api_base, auth)
        has_existing_rsp = existing_rsp is not None
        submit_label = "Update response file" if has_existing_rsp else "Create response file"
        submit_clicked = st.button(
            submit_label,
            type="primary",
            key="rf_submit_btn",
            disabled=bool(wallet_contract_errors),
        )
        if submit_clicked and not selection.response_method_supported:
            st.error(responsefile_unavailable_message(selection.selected_migration_method))
            submit_clicked = False

    with col_preview:
        _render_responsefile_preview(
            existing_rsp=existing_rsp,
            preview_payload=preview_payload,
            preview_lines=preview_lines,
            response_method_supported=selection.response_method_supported,
            selected_migration_method=selection.selected_migration_method,
        )

    if submit_clicked:
        data = api_request("post", "/responsefiles", api_base, auth, payload=preview_request)
        if data is not None:
            validated = validate_payload_or_stop(
                data,
                validate_responsefile_write_response,
                expected_project=project,
                expected_method=selection.selected_migration_method,
            )
            st.success(validated["message"])
            render_diagnostics(validated)


def _load_wallet_map(api_base: str, auth: Any) -> Dict[str, str]:
    wallets_resp = api_request_required("get", "/credential-wallets/paths", api_base, auth)
    return validate_payload_or_stop(wallets_resp, validate_credential_wallet_paths_response)


def _load_existing_rsp(project_name: str, api_base: str, auth: Any) -> Dict[str, Any] | None:
    rsp_resp = api_request_optional_404(
        "get",
        f"/responsefiles/{project_name}",
        api_base,
        auth,
        allowed_detail="Response file not found",
    )
    if rsp_resp is None:
        return None
    return validate_payload_or_stop(
        rsp_resp,
        validate_responsefile_read_response,
        expected_project=project_name,
    )


def _apply_rsp_to_state(
    project_name: str,
    api_base: str,
    auth: Any,
    wallet_map: Dict[str, str],
    clear_response_form_state: Any,
) -> None:
    clear_response_form_state()
    rsp_resp = api_request_optional_404(
        "get",
        f"/responsefiles/{project_name}",
        api_base,
        auth,
        allowed_detail="Response file not found",
    )
    if rsp_resp is not None:
        validated = validate_payload_or_stop(
            rsp_resp,
            validate_responsefile_read_response,
            expected_project=project_name,
        )
        updates = state_updates_from_rsp_content(validated["content"], wallet_map)
        for key, value in updates.items():
            st.session_state[key] = value
    st.session_state["rf_form_loaded_project"] = project_name


def _unresolved_rsp_wallet_contract_errors(
    wallet_map: Dict[str, str],
    preview_payload: Dict[str, Any],
) -> List[str]:
    errors = st.session_state.get("rf_rsp_wallet_contract_errors") or []
    if not isinstance(errors, list):
        return []

    active_fields = set(preview_payload.keys())
    messages: List[str] = []
    for error in errors:
        if not isinstance(error, dict):
            continue
        field = str(error.get("field") or "Wallet")
        if field not in active_fields:
            continue
        state_key = str(error.get("state_key") or "")
        selected_wallet = st.session_state.get(state_key)
        if selected_wallet in wallet_map:
            continue
        path = str(error.get("path") or "")
        messages.append(
            f"{field} references `{path}`, but that path is not registered in DB Wallets & Credentials. "
            "Select a registered wallet before saving this response file."
        )
    return messages


def _compile_preview_lines(
    response_method_supported: bool,
    preview_request: Dict[str, Any],
    api_base: str,
    auth: Any,
) -> List[str]:
    if not response_method_supported:
        return []
    preview_compile = api_request(
        "post",
        "/responsefiles/preview",
        api_base,
        auth,
        payload=preview_request,
    )
    if preview_compile is None:
        return []
    return validate_payload_or_stop(
        preview_compile,
        validate_responsefile_preview_response,
        expected_project=str(preview_request.get("project") or ""),
        expected_method=str(preview_request.get("migration_method") or ""),
    )


def _render_responsefile_preview(
    *,
    existing_rsp: Any,
    preview_payload: Dict[str, Any],
    preview_lines: List[str],
    response_method_supported: bool,
    selected_migration_method: str,
) -> None:
    st.markdown("### Payload")
    tab_preview, tab_rsp = st.tabs(["Preview", "RSP view"])

    with tab_preview:
        st.code(json.dumps(preview_payload, indent=2), language="json")

    with tab_rsp:
        if preview_lines:
            st.caption("Would be written as:")
            st.code("\n".join(preview_lines), language="ini")
            if isinstance(existing_rsp, dict) and existing_rsp.get("status") == "success":
                with st.expander("Current saved response file", expanded=False):
                    st.code(existing_rsp.get("content", ""), language="ini")
        elif not response_method_supported:
            st.error(responsefile_unavailable_message(selected_migration_method))
        elif isinstance(existing_rsp, dict) and existing_rsp.get("status") == "success":
            st.caption("Current saved response file")
            st.code(existing_rsp.get("content", ""), language="ini")
        else:
            st.error("ZEUS could not build the response file preview. Check the required fields, then try again.")
