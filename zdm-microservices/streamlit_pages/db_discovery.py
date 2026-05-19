from __future__ import annotations

import html
import json
from typing import Any, Dict, List, Mapping

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, api_request_required, validate_payload_or_stop
from streamlit_shared.api_payload import (
    validate_database_discovery_response,
    validate_projects_response,
)
from streamlit_shared.console_layout import page_header_actions, page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import render_diagnostics


STATUS_LABELS = {
    "informational": "Information",
    "passed": "Passed",
    "difference": "Difference",
    "source_only": "Only in source",
    "target_only": "Only in target",
    "readiness_issue": "Migration readiness issue",
    "not_applicable": "Not applicable",
    "not_returned": "Not returned",
}

PROFILE_DDL_DETAIL_TITLES = {
    "source": "Source profile DDL",
    "target": "Target profile DDL",
}


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    _render_discovery_styles()

    projects_resp = validate_payload_or_stop(
        api_request_required("get", "/projects", api_base, auth),
        validate_projects_response,
    )
    project_names = list(projects_resp.keys())
    if not project_names:
        render_page_header(
            "Design Migration",
            "Database Discovery",
            "Review project source and target discovery snapshots, differences, and migration readiness items.",
        )
        render_workflow_back_button()
        st.info("Create a project before running Database Discovery.")
        return

    project_options = [""] + project_names
    with page_header_actions(
        "Design Migration",
        "Database Discovery",
        "Review project source and target discovery snapshots, differences, and migration readiness items.",
        key="database-discovery-header-actions",
    ):
        selector_col, refresh_col = st.columns([0.68, 0.32], vertical_alignment="bottom")
        with selector_col:
            selected_project = st.selectbox(
                "Project",
                options=project_options,
                index=0,
                format_func=lambda value: value or "",
                key="database_discovery_project",
                label_visibility="collapsed",
            )
        with refresh_col:
            refresh_clicked = st.button("Refresh", type="primary", width="stretch", disabled=not selected_project)
    render_workflow_back_button()

    if not selected_project:
        st.info("Select a project to review Database Discovery.")
        return

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
        _render_snapshot_card("Source", snapshots["source"])
    with snap_cols[1]:
        _render_snapshot_card("Target", snapshots["target"])

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
            _render_rows(readiness_rows, key="readiness")
        else:
            st.success("No migration readiness issues were returned for the latest snapshots.")

    for index, section in enumerate(visible_sections, start=1):
        with tabs[index]:
            _render_rows(
                section.get("rows", []),
                key=f"section_{section.get('key')}",
                compact_table=section.get("key") == "directories",
            )

    with tabs[-1]:
        render_diagnostics(discovery)


def _render_snapshot_card(side: str, snapshot: Mapping[str, Any]) -> None:
    connection_name = str(snapshot.get("connection_name") or "Not selected")
    if side == "Source":
        panel_title = f"Source: {connection_name}"
    else:
        panel_title = f"Target: {connection_name}"
    with page_panel(panel_title):
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

        captured_at = snapshot.get("captured_at") or "Not captured"
        st.caption(f"Captured: {captured_at}")
        if status != "available":
            st.caption("Refresh discovery to capture the latest snapshot for this connection.")

        summary = snapshot.get("summary") if isinstance(snapshot.get("summary"), Mapping) else {}
        chips = []
        for label, key in (
            ("DB unique name", "database_unique_name"),
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


def _render_rows(rows: List[Mapping[str, Any]], *, key: str, compact_table: bool = False) -> None:
    if not rows:
        st.caption("No comparison rows were returned.")
        return
    display_rows = [_row_to_display(row) for row in rows]
    selected_index = _render_discovery_dataframe(
        display_rows,
        key=key,
        compact_table=compact_table,
        informational_table=_all_rows_informational(rows),
    )
    if selected_index is not None and 0 <= selected_index < len(rows):
        _render_row_details(rows[selected_index])


def _all_rows_informational(rows: List[Mapping[str, Any]]) -> bool:
    return bool(rows) and all(row.get("status") == "informational" for row in rows)


def _render_discovery_styles() -> None:
    st.markdown(
        """
        <style>
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

        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_discovery_dataframe(
    rows: List[Mapping[str, Any]],
    *,
    key: str,
    compact_table: bool = False,
    informational_table: bool = False,
) -> int | None:
    if informational_table:
        columns = ["Check", "Source", "Target"]
    elif compact_table:
        columns = ["Check", "Status", "Details", "Severity", "Message", "Guidance"]
    else:
        columns = ["Check", "Source", "Target", "Status", "Details", "Severity", "Message", "Guidance"]
    df = pd.DataFrame(rows).reindex(columns=columns)
    styled_df = df.style.apply(_discovery_row_style, axis=1)
    state = st.dataframe(
        styled_df,
        hide_index=True,
        width="stretch",
        key=f"database_discovery_{key}",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Check": st.column_config.TextColumn("Check", pinned=True),
            "Status": st.column_config.TextColumn("Status"),
            "Details": st.column_config.TextColumn("Details"),
            "Severity": st.column_config.TextColumn("Severity"),
        },
    )
    selected_rows = _selected_dataframe_rows(state)
    if not selected_rows:
        return None
    selected = selected_rows[0]
    return selected if isinstance(selected, int) else None


def _selected_dataframe_rows(state: Any) -> list[Any]:
    selection = getattr(state, "selection", None)
    if selection is not None:
        rows = getattr(selection, "rows", None)
        if isinstance(rows, list):
            return rows
    if isinstance(state, Mapping):
        selection = state.get("selection")
        if isinstance(selection, Mapping) and isinstance(selection.get("rows"), list):
            return selection["rows"]
    return []


def _render_row_details(row: Mapping[str, Any]) -> None:
    details = row.get("details")
    if not isinstance(details, list) or not details:
        return
    source_details = [detail for detail in details if isinstance(detail, Mapping) and detail.get("side") == "source"]
    target_details = [detail for detail in details if isinstance(detail, Mapping) and detail.get("side") == "target"]
    detail_cols = st.columns(2)
    with detail_cols[0]:
        _render_detail_side(source_details, side_label="Source")
    with detail_cols[1]:
        _render_detail_side(target_details, side_label="Target")


def _render_detail_side(details: List[Mapping[str, Any]], *, side_label: str) -> None:
    if not details:
        return
    for detail in details:
        title = _detail_title(detail, side_label)
        st.markdown(f"**{title}**")
        value = detail.get("value")
        if str(detail.get("format") or "") == "json":
            st.code(json.dumps(value, indent=2, default=str), language="json", wrap_lines=True)
        else:
            language = "sql" if str(detail.get("format") or "") == "sql" else None
            st.code(str(value or ""), language=language, wrap_lines=True)


def _detail_title(detail: Mapping[str, Any], side_label: str) -> str:
    label = str(detail.get("label") or "Detail")
    if label.lower() == "profile ddl":
        return PROFILE_DDL_DETAIL_TITLES.get(side_label.lower(), f"{side_label} profile DDL")
    return f"{side_label} {label[:1].lower()}{label[1:]}"


def _discovery_row_style(row: pd.Series) -> list[str]:
    status = str(row.get("Status") or "")
    severity = str(row.get("Severity") or "").lower()
    if status == "Migration readiness issue":
        background = "#FEF2F2"
        color = "#7F1D1D"
    elif severity in {"critical", "high"}:
        background = "#FFFBEB"
        color = "#78350F"
    else:
        background = ""
        color = ""
    if not background:
        return [""] * len(row)
    return [f"background-color: {background}; color: {color};"] * len(row)


def _row_to_display(row: Mapping[str, Any]) -> Dict[str, Any]:
    source = row.get("source") if isinstance(row.get("source"), Mapping) else {}
    target = row.get("target") if isinstance(row.get("target"), Mapping) else {}
    return {
        "Check": row.get("label", ""),
        "Source": _display_side_value(source),
        "Target": _display_side_value(target),
        "Status": STATUS_LABELS.get(str(row.get("status") or ""), str(row.get("status") or "")),
        "Details": "Available" if row.get("details") else "",
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
