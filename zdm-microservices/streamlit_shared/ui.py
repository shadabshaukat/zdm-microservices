from __future__ import annotations

import html
from typing import Any, Mapping, Sequence
from urllib.parse import quote

import pandas as pd
import streamlit as st


def st_df_safe(df: pd.DataFrame, **kwargs):
    """Render dataframes after coercing mixed object columns if Arrow rejects them."""
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    try:
        return st.dataframe(df, **kwargs)
    except Exception:
        df2 = df.copy()
        for col in df2.columns:
            if df2[col].dtype == object:
                df2[col] = df2[col].apply(
                    lambda v: v.decode() if isinstance(v, (bytes, bytearray)) else v
                ).astype(str)
        return st.dataframe(df2, **kwargs)


def render_diagnostics(payload: Any, label: str = "Diagnostics") -> None:
    with st.expander(label, expanded=False):
        st.json(payload, expanded=False)


def render_static_table(
    rows: Sequence[Mapping[str, Any]],
    columns: Sequence[str],
    *,
    empty_message: str = "No rows to display.",
) -> None:
    if not rows:
        st.caption(empty_message)
        return

    header = "".join(f"<th>{html.escape(str(column))}</th>" for column in columns)
    body_rows = []
    for row in rows:
        cells = "".join(
            f"<td>{html.escape(_table_cell(row.get(column)))}</td>"
            for column in columns
        )
        body_rows.append(f"<tr>{cells}</tr>")

    st.markdown(
        f"""
        <style>
        .zeus-static-table-wrap {{
            width: 100%;
            overflow-x: auto;
            margin: 0.35rem 0 0.8rem 0;
        }}
        .zeus-static-table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 0.86rem;
            line-height: 1.35;
        }}
        .zeus-static-table th {{
            padding: 0.55rem 0.65rem;
            border-bottom: 1px solid #CBD5E1;
            color: #475569;
            font-weight: 680;
            text-align: left;
            white-space: nowrap;
        }}
        .zeus-static-table td {{
            padding: 0.52rem 0.65rem;
            border-bottom: 1px solid #E2E8F0;
            color: #1E293B;
            vertical-align: top;
        }}
        .zeus-static-table tr:last-child td {{
            border-bottom: 0;
        }}
        </style>
        <div class="zeus-static-table-wrap">
            <table class="zeus-static-table">
                <thead><tr>{header}</tr></thead>
                <tbody>{''.join(body_rows)}</tbody>
            </table>
        </div>
        """,
        unsafe_allow_html=True,
    )


def _table_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def param_help(key: str, extra: str = "") -> str:
    """Tooltip helper for Streamlit `help=`."""
    if extra:
        return f"Param: {key} · {extra}"
    return f"Param: {key}"


def field_label(label: str, required: bool) -> str:
    return f"{label}{' *' if required else ''}"


def saved_job_name(project: str, run_type: str) -> str:
    return f"{project}_{str(run_type or '').strip().lower()}"


def query_param(name: str, default: str = "") -> str:
    try:
        value = st.query_params.get(name, default)
    except Exception:
        return default
    if isinstance(value, list):
        return str(value[0]) if value else default
    return str(value or default)


def monitor_job_url(job_id: Any, view: str = "details") -> str:
    job_id_text = str(job_id or "").strip()
    if not job_id_text:
        return ""
    view_text = "logs" if str(view).lower() == "logs" else "details"
    return f"?section=jobs&job_id={quote(job_id_text)}&view={view_text}"
