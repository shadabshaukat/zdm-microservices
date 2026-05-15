from __future__ import annotations

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_dbconnections_response,
    validate_project_create_response,
    validate_project_delete_response,
    validate_projects_response,
)
from streamlit_shared.context import AppContext
from streamlit_shared.db_types import db_connection_names_for_role

def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    st.subheader("Projects")
    st.caption("A Project groups source & target connections; its name is also used as the response filename.")

    connections_cache = validate_payload_or_stop(
        api_request_required("get", "/dbconnections", api_base, auth),
        validate_dbconnections_response,
    )
    projects_resp = validate_payload_or_stop(
        api_request_required("get", "/projects", api_base, auth),
        validate_projects_response,
    )
    source_conn_names = ["-- Select connection --"] + list(
        db_connection_names_for_role(connections_cache, "source")
    )
    target_conn_names = ["-- Select connection --"] + list(
        db_connection_names_for_role(connections_cache, "target")
    )

    with st.form("create_project"):
        project_name = st.text_input(
            "Project name",
            help="Lowercase letters + numbers + dash/underscore only. Used as response file name.",
        )
        source_conn = st.selectbox("Source connection", source_conn_names)
        target_conn = st.selectbox("Target connection", target_conn_names, key="target_conn_select")
        project_clicked = st.form_submit_button("Create project", type="primary")

    def valid_project(name: str) -> bool:
        return bool(name) and name.islower() and all(c.isalnum() or c in "-_" for c in name)

    if project_clicked:
        if not valid_project(project_name):
            st.error("Project name must be lowercase and contain only a-z, 0-9, dash or underscore.")
        elif source_conn == "-- Select connection --" or target_conn == "-- Select connection --":
            st.error("Source and target connection are required.")
        elif project_name in projects_resp:
            st.error("Project already exists. Delete it before creating it again.")
        else:
            payload = {"name": project_name, "source_connection": source_conn, "target_connection": target_conn}
            data = api_request("post", "/projects", api_base, auth, payload=payload)
            if data:
                validated = validate_payload_or_stop(
                    data,
                    validate_project_create_response,
                    expected_project=project_name,
                )
                st.success(validated["message"])
                st.json(validated)

    st.markdown("### Existing projects")
    if not projects_resp:
        st.info("No projects created yet.")
        return

    rows = []
    for name, project in projects_resp.items():
        project_info = project
        rows.append(
            {
                "Name": name,
                "Source": project_info.get("source_connection", ""),
                "Target": project_info.get("target_connection", ""),
                "Response File": project_info.get("rsp", ""),
                "Migration Method": project_info.get("migration_method", ""),
                "Delete?": False,
            }
        )

    edited = st.data_editor(
        pd.DataFrame(rows),
        hide_index=True,
        width='stretch',
        column_config={
            "Name": st.column_config.TextColumn(disabled=True),
            "Source": st.column_config.TextColumn(disabled=True),
            "Target": st.column_config.TextColumn(disabled=True),
            "Response File": st.column_config.TextColumn(disabled=True),
            "Migration Method": st.column_config.TextColumn(disabled=True),
            "Delete?": st.column_config.CheckboxColumn(),
        },
        key="project_editor",
    )

    to_delete = [row["Name"] for _, row in edited.iterrows() if row.get("Delete?", False)]
    confirm_delete = False
    if to_delete:
        st.warning("Project deletion removes response files, generated scripts, and saved job definitions.")
        confirm_delete = st.checkbox(
            "Confirm deletion",
            key="project_delete_confirm",
        )

    if st.button("Delete checked projects", type="secondary", disabled=bool(to_delete) and not confirm_delete):
        if not to_delete:
            st.info("No projects selected for deletion.")
        else:
            deleted = 0
            for name in to_delete:
                resp = api_request("delete", f"/projects/{name}", api_base, auth)
                if resp:
                    validate_payload_or_stop(resp, validate_project_delete_response)
                    deleted += 1
            st.success(f"Deleted {deleted} project{'s' if deleted != 1 else ''}.")
            st.session_state.pop("project_delete_confirm", None)
            st.rerun()

    # -----------------------------
