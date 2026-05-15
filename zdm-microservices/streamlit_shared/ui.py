from __future__ import annotations

from typing import Any
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
