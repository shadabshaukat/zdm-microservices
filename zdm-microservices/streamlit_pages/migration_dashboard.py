from __future__ import annotations

from typing import Dict, List, Optional

import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, validate_payload_or_stop
from streamlit_shared.api_payload import validate_jobs_dashboard_response
from streamlit_shared.console_layout import render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.job_data import (
    KPI_COLUMNS,
    zdm_fleet_dataframe,
    zdm_job_kpis,
    zdm_job_records_to_dataframe,
)
from streamlit_shared.navigation import render_workflow_back_button
from streamlit_shared.ui import (
    monitor_job_url,
    render_diagnostics,
    st_df_safe,
)


CHART_STATUS_COLORS = {
    "Failed": "#DC2626",
    "Succeeded": "#059669",
    "Running": "#D97706",
    "Paused": "#7C3AED",
    "Suspended": "#6B7280",
    "Waiting": "#0891B2",
    "EVAL": "#7C3AED",
    "MIGRATE": "#0891B2",
}
CHART_FALLBACK_COLORS = ["#2563EB", "#14B8A6", "#F59E0B", "#8B5CF6", "#64748B"]


def _chart_colors(columns) -> List[str]:
    return [
        CHART_STATUS_COLORS.get(str(column), CHART_FALLBACK_COLORS[index % len(CHART_FALLBACK_COLORS)])
        for index, column in enumerate(columns)
    ]


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    render_page_header(
        "Execute & Observe",
        "Fleet Dashboard",
        "Review fleet-level migration status across projects, databases, and ZDM jobs.",
    )
    render_workflow_back_button()

    refresh_col, meta_col = st.columns([0.18, 0.82], vertical_alignment="center")
    with refresh_col:
        refresh_jobs = st.button("Refresh Jobs", type="primary", width='stretch')

    if refresh_jobs or "fleet_jobs_payload" not in st.session_state:
        payload = api_request(
            "get",
            "/jobs",
            api_base,
            auth,
            params={"refresh": "true"} if refresh_jobs else None,
            timeout=180 if refresh_jobs else 30,
            quiet=True,
        )
        if payload is None:
            st.error("ZEUS backend is not reachable. Fleet job snapshot cannot be loaded.")
            return
        st.session_state["fleet_jobs_payload"] = validate_payload_or_stop(
            payload,
            validate_jobs_dashboard_response,
        )

    payload_raw = st.session_state.get("fleet_jobs_payload")
    if not payload_raw:
        st.info("No job snapshot available.")
        st.stop()
    payload = validate_payload_or_stop(payload_raw, validate_jobs_dashboard_response)

    with meta_col:
        details = []
        if payload.get("source"):
            details.append(f"Source: {payload.get('source')}")
        if payload.get("last_refreshed"):
            details.append(f"Last refreshed: {payload.get('last_refreshed')}")
        st.caption(" · ".join(details) if details else "Snapshot metadata unavailable")

    warnings = payload.get("warnings") or []
    if warnings:
        with st.expander("Snapshot warnings", expanded=False):
            for warning in warnings:
                st.warning(str(warning))

    try:
        jobs_df_all = zdm_job_records_to_dataframe(payload.get("jobs") or [])
    except ValueError as exc:
        st.error("ZEUS received unexpected job data. Restart the backend, then refresh jobs from this page.")
        with st.expander("Technical details", expanded=False):
            st.code(str(exc))
        render_diagnostics(payload)
        st.stop()

    if jobs_df_all.empty:
        st.info("No jobs returned.")
        render_diagnostics(payload)
        st.stop()

    def _filter_options(df: pd.DataFrame, column: str) -> List[str]:
        if column not in df.columns:
            return []
        return sorted([str(value) for value in df[column].dropna().unique() if str(value).strip()])

    def _multiselect_filter(df: pd.DataFrame, column: str, key: str) -> pd.DataFrame:
        options = _filter_options(df, column)
        selected = st.multiselect(column, options, key=key)
        if selected:
            return df[df[column].isin(selected)]
        return df

    with st.expander("Filters", expanded=False):
        filter_cols = st.columns(3)
        jobs_df = jobs_df_all.copy()
        filter_fields = [
            "Project",
            "Migration Method",
            "Job Type",
            "Status",
            "Source Node",
            "Source Database",
            "Target Node",
            "Target Database",
            "Current Stage",
        ]
        for idx, field in enumerate(filter_fields):
            with filter_cols[idx % len(filter_cols)]:
                jobs_df = _multiselect_filter(jobs_df, field, f"fleet_filter_{field}")

    eval_jobs_df = jobs_df[jobs_df["Job Type"] == "EVAL"] if not jobs_df.empty else jobs_df
    migrate_jobs_df = jobs_df[jobs_df["Job Type"] == "MIGRATE"] if not jobs_df.empty else jobs_df
    eval_fleet_df = zdm_fleet_dataframe(eval_jobs_df)
    migrate_fleet_df = zdm_fleet_dataframe(migrate_jobs_df)

    def _render_kpis(title: str, counts: Dict[str, int]) -> None:
        st.markdown(f"### {title}")
        cols = st.columns(len(KPI_COLUMNS))
        for col, label in zip(cols, KPI_COLUMNS):
            with col:
                st.metric(label, counts.get(label, 0))

    def _bar_chart(
        df: pd.DataFrame,
        index_col: str,
        group_col: str,
        title: str,
        missing_label: Optional[str] = None,
    ) -> None:
        st.markdown(f"### {title}")
        if df.empty or index_col not in df.columns or group_col not in df.columns:
            st.info("No data available.")
            return
        chart_source = df.copy()
        if missing_label:
            chart_source[index_col] = chart_source[index_col].apply(
                lambda value: str(value).strip() if pd.notna(value) and str(value).strip() else missing_label
            )
        counts = chart_source.groupby([index_col, group_col]).size().reset_index(name="Count")
        if counts.empty:
            st.info("No data available.")
            return
        chart_df = counts.pivot(index=index_col, columns=group_col, values="Count").fillna(0)
        st.bar_chart(chart_df, color=_chart_colors(chart_df.columns))

    def _job_type_lane(title: str, kpis: Dict[str, int]) -> None:
        st.markdown(f"## {title}")
        _render_kpis(f"{title} Jobs", kpis)

    def _column_picker(df: pd.DataFrame, defaults: List[str], key: str) -> List[str]:
        available = [column for column in defaults if column in df.columns]
        extras = [column for column in df.columns if column not in available]
        selected = st.multiselect(
            "Columns to show",
            available + extras,
            default=available,
            key=key,
        )
        return selected or available

    def _sort_dashboard_rows(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        sorted_df = df.copy()
        for column in ("Project", "Job Type", "Job ID"):
            if column not in sorted_df.columns:
                sorted_df[column] = ""
        sorted_df["_job_sort"] = pd.to_numeric(sorted_df["Job ID"], errors="coerce").fillna(-1)
        sorted_df["_project_sort"] = sorted_df["Project"].astype(str).str.lower()
        sorted_df["_type_sort"] = sorted_df["Job Type"].astype(str).str.lower()
        sorted_df = sorted_df.sort_values(
            ["_project_sort", "_type_sort", "_job_sort"],
            kind="stable",
        )
        return sorted_df.drop(columns=["_project_sort", "_type_sort", "_job_sort"])

    def _with_job_links(df: pd.DataFrame, view: str) -> pd.DataFrame:
        if df.empty or "Job ID" not in df.columns:
            return df
        linked = df.copy()
        linked["Job ID"] = linked["Job ID"].apply(lambda value: monitor_job_url(value, view))
        return linked

    def _fleet_status_display_df(df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        display_df = df.copy()
        display_df["Job Type"] = display_df.get("Current Job Type", "")
        display_df["Job ID"] = ""
        display_df["Status"] = ""
        eval_rows = display_df["Job Type"] == "EVAL"
        migrate_rows = display_df["Job Type"] == "MIGRATE"
        if "Latest Eval Job" in display_df.columns:
            display_df.loc[eval_rows, "Job ID"] = display_df.loc[eval_rows, "Latest Eval Job"]
        if "Latest Eval Status" in display_df.columns:
            display_df.loc[eval_rows, "Status"] = display_df.loc[eval_rows, "Latest Eval Status"]
        if "Latest Migrate Job" in display_df.columns:
            display_df.loc[migrate_rows, "Job ID"] = display_df.loc[migrate_rows, "Latest Migrate Job"]
        if "Latest Migrate Status" in display_df.columns:
            display_df.loc[migrate_rows, "Status"] = display_df.loc[migrate_rows, "Latest Migrate Status"]
        if "Last Start" in display_df.columns:
            display_df["Started"] = display_df["Last Start"]
        if "Last End" in display_df.columns:
            display_df["Ended"] = display_df["Last End"]
        return display_df

    table_column_labels = {"Result File": "Log File"}

    def _table_section(
        title: str,
        df: pd.DataFrame,
        defaults: List[str],
        key: str,
        empty_message: str,
        link_view: Optional[str] = None,
    ) -> None:
        st.markdown(f"### {title}")
        if df.empty:
            st.info(empty_message)
            return
        table_df = _sort_dashboard_rows(df)
        if link_view:
            table_df = _with_job_links(table_df, link_view)
        display_df = table_df.rename(columns=table_column_labels)
        display_defaults = [table_column_labels.get(column, column) for column in defaults]
        columns = _column_picker(display_df, display_defaults, key)
        column_config = {}
        if link_view and "Job ID" in columns:
            column_config["Job ID"] = st.column_config.LinkColumn(
                "Job ID",
                display_text=r"job_id=([^&]+)",
                help="Open in ZDM Job Monitoring",
            )
        st_df_safe(display_df[columns], hide_index=True, width='stretch', column_config=column_config)

    tabs = st.tabs(["Overview", "Fleet Status", "Job Details", "Failures", "Diagnostics"])
    eval_kpis = zdm_job_kpis(jobs_df, "EVAL")
    migrate_kpis = zdm_job_kpis(jobs_df, "MIGRATE")
    fleet_status_df = pd.concat(
        [_fleet_status_display_df(eval_fleet_df), _fleet_status_display_df(migrate_fleet_df)],
        ignore_index=True,
    )

    with tabs[0]:
        eval_lane, migrate_lane = st.columns(2)
        with eval_lane:
            _job_type_lane("Eval", eval_kpis)
        with migrate_lane:
            _job_type_lane("Migrate", migrate_kpis)
        st.divider()
        _bar_chart(jobs_df, "Project", "Status Category", "Jobs By Project", missing_label="Outside ZEUS")
        chart_cols = st.columns(2)
        with chart_cols[0]:
            _bar_chart(
                jobs_df,
                "Source Database",
                "Status Category",
                "Jobs By Source Database",
                missing_label="Unknown Source DB",
            )
        with chart_cols[1]:
            _bar_chart(
                jobs_df,
                "Source Node",
                "Status Category",
                "Jobs By Source Node",
                missing_label="Unknown Source Node",
            )
        _bar_chart(fleet_status_df, "Fleet State", "Job Type", "Current Fleet State")

    with tabs[1]:
        default_fleet_columns = [
            "Project",
            "Job Type",
            "Job ID",
            "Status",
            "Current Stage",
            "Migration Method",
            "Source Database",
            "Target Database",
            "Source Node",
            "Target Node",
            "Started",
            "Ended",
        ]
        _table_section(
            "Fleet Status",
            fleet_status_df,
            default_fleet_columns,
            "fleet_status_columns",
            "No fleet rows match the selected filters.",
            link_view="details",
        )

    with tabs[2]:
        default_job_columns = [
            "Project",
            "Job Type",
            "Job ID",
            "Status",
            "Current Stage",
            "Migration Method",
            "Source Node",
            "Source Database",
            "Target Node",
            "Target Database",
            "Started",
            "Ended",
            "Result File",
        ]
        _table_section(
            "Job Details",
            jobs_df,
            default_job_columns,
            "job_detail_columns",
            "No jobs match the selected filters.",
            link_view="details",
        )

    with tabs[3]:
        failure_columns = [
            "Project",
            "Job Type",
            "Job ID",
            "Status",
            "Current Stage",
            "Migration Method",
            "Source Database",
            "Target Database",
            "Result File",
            "Started",
            "Ended",
        ]
        failed_jobs_df = jobs_df[jobs_df["Status Category"] == "Failed"] if not jobs_df.empty else jobs_df
        _bar_chart(failed_jobs_df, "Current Stage", "Job Type", "Failed Jobs By Stage")
        _table_section(
            "Failures",
            failed_jobs_df,
            failure_columns,
            "failure_columns",
            "No failed jobs match the selected filters.",
            link_view="logs",
        )

    with tabs[4]:
        render_diagnostics(payload)
