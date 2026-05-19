from __future__ import annotations

from typing import Any, Dict, List, Mapping

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_database_discovery_response,
    validate_projects_response,
)
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import render_diagnostics, st_df_safe


STATUS_LABELS = {
    "passed": "Passed",
    "difference": "Difference",
    "source_only": "Only in source",
    "target_only": "Only in target",
    "readiness_issue": "Migration readiness issue",
    "not_applicable": "Not applicable",
    "not_returned": "Not returned",
}


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Design Migration",
        "Database Discovery",
        "Review project source and target discovery snapshots, differences, and migration readiness items.",
    )
    render_workflow_back_button()

    projects_resp = validate_payload_or_stop(
        api_request_required("get", "/projects", api_base, auth),
        validate_projects_response,
    )
    project_names = list(projects_resp.keys())
    if not project_names:
        st.info("Create a project before running Database Discovery.")
        return

    selected_project = st.selectbox("Project", project_names, key="database_discovery_project")
    project_record = projects_resp[selected_project]

    top_cols = st.columns([0.72, 0.28], vertical_alignment="bottom")
    with top_cols[0]:
        st.markdown(
            " ".join(
                [
                    f"`Method: {project_record.get('migration_method', '')}`",
                    f"`Source: {project_record.get('source_connection', '')}`",
                    f"`Target: {project_record.get('target_connection', '')}`",
                ]
            )
        )
    with top_cols[1]:
        refresh_clicked = st.button("Refresh source & target", type="primary", width="stretch")

    if refresh_clicked:
        discovery_raw = api_request(
            "post",
            f"/projects/{selected_project}/database-discovery/refresh",
            api_base,
            auth,
        )
    else:
        discovery_raw = api_request(
            "get",
            f"/projects/{selected_project}/database-discovery",
            api_base,
            auth,
            quiet=True,
        )

    if discovery_raw is None:
        st.error("Database Discovery is not available. Check the backend service and project configuration.")
        return

    discovery = validate_payload_or_stop(discovery_raw, validate_database_discovery_response)
    snapshots = discovery["snapshots"]
    summary = discovery["summary"]
    sections = discovery["sections"]

    snap_cols = st.columns(2)
    with snap_cols[0]:
        _render_snapshot_card("Source snapshot", snapshots["source"])
    with snap_cols[1]:
        _render_snapshot_card("Target snapshot", snapshots["target"])

    metric_cols = st.columns(4)
    metric_cols[0].metric("Readiness issues", summary["readiness_issues"])
    metric_cols[1].metric("Differences to review", summary["differences"])
    metric_cols[2].metric("Only in source", summary["source_only"])
    metric_cols[3].metric("Only in target", summary["target_only"])

    readiness_rows = [
        row
        for section in sections
        for row in section.get("rows", [])
        if row.get("status") == "readiness_issue"
    ]
    visible_sections = [
        section
        for section in sections
        if section.get("key") != "cloud_identity" or any(row.get("status") != "not_returned" for row in section.get("rows", []))
    ]

    tab_labels = ["Readiness"] + [str(section["label"]) for section in visible_sections] + ["Diagnostics"]
    tabs = st.tabs(tab_labels)

    with tabs[0]:
        if readiness_rows:
            _render_rows(readiness_rows)
        else:
            st.success("No migration readiness issues were returned for the latest snapshots.")

    for index, section in enumerate(visible_sections, start=1):
        with tabs[index]:
            _render_rows(section.get("rows", []))

    with tabs[-1]:
        render_diagnostics(discovery)


def _render_snapshot_card(title: str, snapshot: Mapping[str, Any]) -> None:
    with page_panel(title):
        status = str(snapshot.get("status") or "")
        if status == "available":
            st.success("Available")
        elif status == "failed":
            st.error("Refresh failed")
        else:
            st.warning("Not captured")

        st.markdown(f"**{snapshot.get('connection_name', '')}**")
        captured_at = snapshot.get("captured_at") or "Not captured"
        st.caption(f"Captured: {captured_at}")
        message = snapshot.get("message")
        if message:
            st.info(str(message))

        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), Mapping) else {}
        chips = []
        for label, key in (
            ("Platform", "platform_type"),
            ("Container", "container_label"),
            ("Role", "database_role"),
            ("Open", "open_mode"),
            ("RAC", "rac"),
        ):
            value = summary.get(key)
            if value not in (None, ""):
                chips.append(f"`{label}: {value}`")
        if chips:
            st.markdown(" ".join(chips))


def _render_rows(rows: List[Mapping[str, Any]]) -> None:
    if not rows:
        st.info("No comparison rows were returned.")
        return
    frame = pd.DataFrame([_row_to_display(row) for row in rows])
    st_df_safe(frame, hide_index=True, width="stretch")


def _row_to_display(row: Mapping[str, Any]) -> Dict[str, Any]:
    source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
    target = row.get("target") if isinstance(row.get("target"), Mapping) else {}
    return {
        "Check": row.get("label", ""),
        "Source": _display_side_value(source),
        "Target": _display_side_value(target),
        "Status": STATUS_LABELS.get(str(row.get("status") or ""), str(row.get("status") or "")),
        "Severity": str(row.get("severity") or "").title(),
        "Message": row.get("message", ""),
        "Guidance": row.get("guidance", ""),
    }


def _display_side_value(side: Mapping[str, Any]) -> str:
    if not side.get("present"):
        return "Not returned"
    value = side.get("value")
    if value in (None, ""):
        return "Not returned"
    if isinstance(value, (dict, list)):
        return str(value)
    return str(value)
