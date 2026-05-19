from __future__ import annotations

import html
from typing import Any, Dict, List, Mapping

import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_database_discovery_response,
    validate_projects_response,
)
from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import render_diagnostics


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

    _render_discovery_styles()

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
        st.markdown(f"`Method: {project_record.get('migration_method', '')}`")
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

    _render_comparison_heading(project_record)

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
            status_label = "Available"
        elif status == "failed":
            status_label = "Refresh failed"
        else:
            status_label = "Not captured"

        st.markdown(
            f"""
            <div class="zeus-snapshot-status zeus-snapshot-status--{html.escape(status or 'missing')}">
                {html.escape(status_label)}
            </div>
            """,
            unsafe_allow_html=True,
        )

        st.markdown(f"**{snapshot.get('connection_name', '')}**")
        captured_at = snapshot.get("captured_at") or "Not captured"
        st.caption(f"Captured: {captured_at}")
        if status != "available":
            st.caption("Refresh discovery to capture the latest snapshot for this connection.")

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
        st.caption("No comparison rows were returned.")
        return
    display_rows = [_row_to_display(row) for row in rows]
    _render_discovery_table(display_rows)


def _render_discovery_styles() -> None:
    st.markdown(
        """
        <style>
        .zeus-comparison-heading {
            display: flex;
            flex-wrap: wrap;
            gap: 0.55rem;
            align-items: center;
            margin: 0.85rem 0 0.55rem 0;
            color: var(--zeus-text-muted);
            font-size: 0.82rem;
            font-weight: 650;
        }

        .zeus-comparison-heading__item {
            display: inline-flex;
            gap: 0.35rem;
            align-items: center;
            padding: 0.34rem 0.52rem;
            border: 1px solid var(--zeus-border);
            border-radius: 7px;
            background: #FFFFFF;
        }

        .zeus-comparison-heading__label {
            color: var(--zeus-text-muted);
            font-weight: 720;
        }

        .zeus-comparison-heading__value {
            color: var(--zeus-text);
            font-family: var(--zeus-mono);
            font-size: 0.78rem;
            font-weight: 720;
        }

        .zeus-snapshot-status {
            display: inline-flex;
            width: fit-content;
            margin: 0 0 0.7rem 0;
            padding: 0.28rem 0.5rem;
            border-radius: 999px;
            background: #F8FAFC;
            color: #475569;
            font-size: 0.74rem;
            font-weight: 760;
            line-height: 1.2;
        }

        .zeus-snapshot-status--available {
            background: #ECFDF5;
            color: #047857;
        }

        .zeus-snapshot-status--failed {
            background: #FEF2F2;
            color: #B91C1C;
        }

        .zeus-discovery-table-wrap {
            width: 100%;
            overflow-x: auto;
            margin-top: 0.45rem;
            border: 1px solid var(--zeus-border);
            border-radius: 8px;
            background: #FFFFFF;
            box-shadow: var(--zeus-shadow-subtle);
        }

        .zeus-discovery-table {
            width: 100%;
            min-width: 920px;
            border-collapse: collapse;
            font-size: 0.82rem;
            line-height: 1.35;
        }

        .zeus-discovery-table th {
            padding: 0.62rem 0.7rem;
            border-bottom: 1px solid var(--zeus-border);
            background: #F8FAFC;
            color: var(--zeus-text);
            font-size: 0.74rem;
            font-weight: 780;
            text-align: left;
            white-space: nowrap;
        }

        .zeus-discovery-table td {
            padding: 0.66rem 0.7rem;
            border-bottom: 1px solid #E8EEF5;
            color: var(--zeus-text);
            vertical-align: top;
        }

        .zeus-discovery-table tr:nth-child(even) td {
            background: #FBFCFE;
        }

        .zeus-discovery-table tr:last-child td {
            border-bottom: 0;
        }

        .zeus-discovery-pill {
            display: inline-flex;
            padding: 0.18rem 0.44rem;
            border-radius: 999px;
            background: #F1F5F9;
            color: #475569;
            font-size: 0.72rem;
            font-weight: 760;
            white-space: nowrap;
        }

        .zeus-discovery-pill--passed {
            background: #ECFDF5;
            color: #047857;
        }

        .zeus-discovery-pill--difference,
        .zeus-discovery-pill--source-only,
        .zeus-discovery-pill--target-only,
        .zeus-discovery-pill--only-in-source,
        .zeus-discovery-pill--only-in-target {
            background: #EFF6FF;
            color: #1D4ED8;
        }

        .zeus-discovery-pill--readiness-issue,
        .zeus-discovery-pill--migration-readiness-issue {
            background: #FEF2F2;
            color: #B91C1C;
        }

        .zeus-discovery-pill--medium,
        .zeus-discovery-pill--high {
            background: #FFFBEB;
            color: #B45309;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_comparison_heading(project_record: Mapping[str, Any]) -> None:
    source = str(project_record.get("source_connection") or "")
    target = str(project_record.get("target_connection") or "")
    st.markdown(
        f"""
        <div class="zeus-comparison-heading">
            <span class="zeus-comparison-heading__item">
                <span class="zeus-comparison-heading__label">Source:</span>
                <span class="zeus-comparison-heading__value">{html.escape(source)}</span>
            </span>
            <span class="zeus-comparison-heading__item">
                <span class="zeus-comparison-heading__label">Target:</span>
                <span class="zeus-comparison-heading__value">{html.escape(target)}</span>
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _render_discovery_table(rows: List[Mapping[str, Any]]) -> None:
    columns = ["Check", "Source", "Target", "Status", "Severity", "Message", "Guidance"]
    header = "".join(f"<th>{html.escape(column)}</th>" for column in columns)
    body = []
    for row in rows:
        status_key = _pill_key(row.get("Status"))
        severity_key = _pill_key(row.get("Severity"))
        cells = [
            f"<td>{html.escape(str(row.get('Check', '')))}</td>",
            f"<td>{html.escape(str(row.get('Source', '')))}</td>",
            f"<td>{html.escape(str(row.get('Target', '')))}</td>",
            (
                f'<td><span class="zeus-discovery-pill zeus-discovery-pill--{status_key}">'
                f"{html.escape(str(row.get('Status', '')))}</span></td>"
            ),
            (
                f'<td><span class="zeus-discovery-pill zeus-discovery-pill--{severity_key}">'
                f"{html.escape(str(row.get('Severity', '')))}</span></td>"
            ),
            f"<td>{html.escape(str(row.get('Message', '')))}</td>",
            f"<td>{html.escape(str(row.get('Guidance', '')))}</td>",
        ]
        body.append(f"<tr>{''.join(cells)}</tr>")

    st.markdown(
        f"""
        <div class="zeus-discovery-table-wrap">
            <table class="zeus-discovery-table">
                <thead><tr>{header}</tr></thead>
                <tbody>{''.join(body)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _pill_key(value: Any) -> str:
    key = str(value or "").strip().lower().replace(" ", "-").replace("_", "-")
    return html.escape(key or "empty")


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
