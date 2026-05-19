from __future__ import annotations

import html
from typing import Dict, List, Optional

import altair as alt
import pandas as pd
import streamlit as st

from streamlit_shared.api_client import api_request, validate_payload_or_stop
from streamlit_shared.api_payload import validate_jobs_dashboard_response
from streamlit_shared.console_layout import page_panel, render_page_header
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


def _render_dashboard_styles() -> None:
    st.markdown(
        """
        <style>
        .zeus-dashboard-tabs {
            height: 0;
        }

        div[data-testid="stTabs"] [role="tablist"] {
            gap: 0.42rem;
            padding: 0.25rem 0 0.55rem 0;
            border-bottom: 1px solid var(--zeus-border);
        }

        div[data-testid="stTabs"] button[role="tab"] {
            min-height: 34px;
            padding: 0.46rem 0.78rem;
            border: 1px solid transparent;
            border-radius: 8px 8px 0 0;
            color: var(--zeus-text-muted);
            font-size: 0.82rem;
            font-weight: 650;
            letter-spacing: 0;
        }

        div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
            border-color: var(--zeus-border);
            border-bottom-color: #FFFFFF;
            background: #FFFFFF;
            color: var(--zeus-primary-dark);
            box-shadow: 0 -1px 0 rgba(15, 23, 42, 0.02);
        }

        div[data-testid="stTabs"] button[role="tab"] p {
            margin: 0;
            font-size: inherit;
            line-height: 1.2;
        }

        .zeus-dashboard-section-title {
            margin: 0 0 0.8rem 0;
            color: var(--zeus-text);
            font-size: 1.08rem;
            font-weight: 800;
            line-height: 1.2;
        }

        .zeus-job-summary-card {
            display: grid;
            gap: 0.9rem;
            min-height: 178px;
            padding: 1rem 1rem 0.95rem 1rem;
            border: 1px solid var(--zeus-border);
            border-left: 4px solid var(--summary-accent, var(--zeus-primary));
            border-radius: 8px;
            background: #FFFFFF;
            box-shadow: var(--zeus-shadow-subtle);
        }

        .zeus-job-summary-card__header {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 1rem;
        }

        .zeus-job-summary-card__title {
            margin: 0;
            color: var(--zeus-text);
            font-size: 1.05rem;
            font-weight: 820;
            line-height: 1.2;
        }

        .zeus-job-summary-card__subtitle {
            margin: 0.18rem 0 0 0;
            color: var(--zeus-text-muted);
            font-size: 0.78rem;
            font-weight: 620;
            line-height: 1.3;
        }

        .zeus-job-summary-card__total {
            display: grid;
            justify-items: end;
            gap: 0.08rem;
            min-width: 72px;
        }

        .zeus-job-summary-card__total-value {
            color: var(--zeus-text);
            font-size: 2rem;
            font-weight: 780;
            line-height: 1;
        }

        .zeus-job-summary-card__total-label {
            color: var(--zeus-text-muted);
            font-size: 0.68rem;
            font-weight: 700;
            line-height: 1.2;
            text-transform: uppercase;
        }

        .zeus-job-summary-card__metrics {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 0.45rem;
        }

        .zeus-status-metric {
            min-width: 0;
            padding: 0.58rem 0.62rem;
            border: 1px solid var(--zeus-border);
            border-radius: 7px;
            background: var(--metric-bg, #F8FAFC);
        }

        .zeus-status-metric__label {
            display: block;
            overflow: hidden;
            color: var(--zeus-text-muted);
            font-size: 0.66rem;
            font-weight: 720;
            line-height: 1.15;
            text-overflow: ellipsis;
            text-transform: uppercase;
            white-space: nowrap;
        }

        .zeus-status-metric__value {
            display: block;
            margin-top: 0.22rem;
            color: var(--metric-color, var(--zeus-text));
            font-size: 1.28rem;
            font-weight: 780;
            line-height: 1;
        }

        .zeus-status-metric--succeeded {
            --metric-bg: #ECFDF5;
            --metric-color: #047857;
        }

        .zeus-status-metric--failed {
            --metric-bg: #FEF2F2;
            --metric-color: #B91C1C;
        }

        .zeus-status-metric--running {
            --metric-bg: #FFFBEB;
            --metric-color: #B45309;
        }

        .zeus-status-metric--paused,
        .zeus-status-metric--suspended {
            --metric-bg: #F8FAFC;
            --metric-color: #475569;
        }

        @media (max-width: 900px) {
            .zeus-job-summary-card__metrics {
                grid-template-columns: repeat(2, minmax(0, 1fr));
            }
        }
        </style>
        <div class="zeus-dashboard-tabs"></div>
        """,
        unsafe_allow_html=True,
    )


def _chart_colors(columns) -> List[str]:
    return [
        CHART_STATUS_COLORS.get(str(column), CHART_FALLBACK_COLORS[index % len(CHART_FALLBACK_COLORS)])
        for index, column in enumerate(columns)
    ]


def _status_metric_class(label: str) -> str:
    normalized = str(label or "").strip().lower().replace(" ", "-")
    return f"zeus-status-metric zeus-status-metric--{html.escape(normalized)}"


def _job_type_summary_markup(title: str, subtitle: str, counts: Dict[str, int], accent: str) -> str:
    metric_html = "".join(
        (
            f'<div class="{_status_metric_class(label)}">'
            f'<span class="zeus-status-metric__label">{html.escape(label)}</span>'
            f'<span class="zeus-status-metric__value">{int(counts.get(label, 0))}</span>'
            "</div>"
        )
        for label in [column for column in KPI_COLUMNS if column != "Total Jobs"]
    )
    return (
        f'<section class="zeus-job-summary-card" style="--summary-accent: {html.escape(accent)};">'
        '<div class="zeus-job-summary-card__header">'
        "<div>"
        f'<h3 class="zeus-job-summary-card__title">{html.escape(title)}</h3>'
        f'<p class="zeus-job-summary-card__subtitle">{html.escape(subtitle)}</p>'
        "</div>"
        '<div class="zeus-job-summary-card__total">'
        f'<span class="zeus-job-summary-card__total-value">{int(counts.get("Total Jobs", 0))}</span>'
        '<span class="zeus-job-summary-card__total-label">Total jobs</span>'
        "</div>"
        "</div>"
        f'<div class="zeus-job-summary-card__metrics">{metric_html}</div>'
        "</section>"
    )


def _job_type_summary_panel(title: str, subtitle: str, counts: Dict[str, int], accent: str) -> None:
    st.html(_job_type_summary_markup(title, subtitle, counts, accent))


def render(ctx: AppContext) -> None:
    api_base = ctx.api_base
    auth = ctx.auth

    _render_dashboard_styles()

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

    def _bar_chart(
        df: pd.DataFrame,
        index_col: str,
        group_col: str,
        title: str,
        missing_label: Optional[str] = None,
        height: int = 270,
    ) -> None:
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
        counts[index_col] = counts[index_col].astype(str)
        counts[group_col] = counts[group_col].astype(str)
        color_domain = list(dict.fromkeys(counts[group_col].tolist()))
        chart = (
            alt.Chart(counts)
            .mark_bar(cornerRadiusTopLeft=2, cornerRadiusTopRight=2)
            .encode(
                x=alt.X(
                    f"{index_col}:N",
                    title=None,
                    axis=alt.Axis(labelAngle=0, labelLimit=140, labelPadding=8),
                    sort=None,
                ),
                y=alt.Y("Count:Q", title="Jobs", stack="zero", axis=alt.Axis(grid=True, tickMinStep=1)),
                color=alt.Color(
                    f"{group_col}:N",
                    scale=alt.Scale(domain=color_domain, range=_chart_colors(color_domain)),
                    legend=alt.Legend(title=None, orient="bottom", direction="horizontal"),
                ),
                tooltip=[
                    alt.Tooltip(f"{index_col}:N", title=index_col),
                    alt.Tooltip(f"{group_col}:N", title=group_col),
                    alt.Tooltip("Count:Q", title="Jobs"),
                ],
            )
            .properties(height=height, title=title)
            .configure_title(anchor="start", fontSize=15, fontWeight=700, color="#1E293B", offset=12)
            .configure_axis(labelColor="#64748B", titleColor="#475569", gridColor="#E2E8F0")
            .configure_legend(labelColor="#64748B", labelFontSize=12, symbolSize=80)
            .configure_view(strokeWidth=0)
        )
        st.altair_chart(chart, use_container_width=True)

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
        st.markdown('<div class="zeus-dashboard-section-title">Job summary</div>', unsafe_allow_html=True)
        eval_lane, migrate_lane = st.columns(2)
        with eval_lane:
            _job_type_summary_panel("Eval", "Evaluation readiness", eval_kpis, "#7C3AED")
        with migrate_lane:
            _job_type_summary_panel("Migrate", "Migration execution", migrate_kpis, "#0891B2")

        with page_panel("Jobs By Project"):
            _bar_chart(jobs_df, "Project", "Status Category", "Jobs By Project", missing_label="Outside ZEUS", height=300)
        chart_cols = st.columns(2)
        with chart_cols[0]:
            with page_panel("Jobs By Source Database"):
                _bar_chart(
                    jobs_df,
                    "Source Database",
                    "Status Category",
                    "Jobs By Source Database",
                    missing_label="Unknown Source DB",
                )
        with chart_cols[1]:
            with page_panel("Jobs By Source Node"):
                _bar_chart(
                    jobs_df,
                    "Source Node",
                    "Status Category",
                    "Jobs By Source Node",
                    missing_label="Unknown Source Node",
                )
        with page_panel("Current Fleet State"):
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
        with page_panel("Failed Jobs By Stage"):
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
