from __future__ import annotations

import html
from urllib.parse import quote

import streamlit as st

from streamlit_shared.ui import query_param


WORKFLOW_SECTION = "workflow"
WORKFLOW_TARGET_STEPS = (
    ("connections", "DB Connections"),
    ("wallet", "Wallets & Credentials"),
    ("discovery", "DB Discovery"),
    ("projects", "Projects"),
    ("response", "Response Files"),
    ("createjob", "Job Definitions"),
    ("runjob", "Job Submission"),
    ("jobs", "Job Monitoring"),
    ("fleet_dashboard", "Fleet Dashboard"),
)
WORKFLOW_TARGET_SECTIONS = tuple(section for section, _ in WORKFLOW_TARGET_STEPS)

NAV_GROUPS = [
    (
        "Start Here",
        [
            ("Guided Workflow", WORKFLOW_SECTION),
        ],
    ),
    (
        "Database Setup",
        [
            ("DB Connections", "connections"),
            ("DB Wallets & Credentials", "wallet"),
            ("DB Discovery", "discovery"),
        ],
    ),
    (
        "Design Migration",
        [
            ("Projects", "projects"),
            ("ZDM Response Files", "response"),
            ("ZDM Job Definitions", "createjob"),
        ],
    ),
    (
        "Execute & Observe",
        [
            ("ZDM Job Submission", "runjob"),
            ("ZDM Job Monitoring", "jobs"),
            ("Fleet Dashboard", "fleet_dashboard"),
        ],
    ),
    (
        "Administration",
        [
            ("ZEUS Settings", "settings"),
        ],
    ),
]
NAV_OPTIONS = {label: section_key for _, items in NAV_GROUPS for label, section_key in items}
NAV_SECTIONS = set(NAV_OPTIONS.values())


def section_href(section_key: str, *, guided: bool = False) -> str:
    if section_key not in NAV_SECTIONS:
        raise ValueError(f"Unknown ZEUS section: {section_key}")
    href = f"?section={quote(section_key)}"
    if guided and section_key in WORKFLOW_TARGET_SECTIONS:
        href = f"{href}&guided=1"
    return href


def go_to_section(section_key: str, *, guided: bool = False) -> None:
    if section_key not in NAV_SECTIONS:
        st.error(f"Unknown ZEUS section: {section_key}")
        st.stop()
    st.session_state["_nav_section"] = section_key
    st.query_params.clear()
    st.query_params["section"] = section_key
    if guided and section_key in WORKFLOW_TARGET_SECTIONS:
        st.query_params["guided"] = "1"
    st.rerun()


def select_section() -> str:
    requested_section = query_param("section")
    saved_section = st.session_state.get("_nav_section")
    if requested_section in NAV_SECTIONS:
        section = requested_section
    elif saved_section in NAV_SECTIONS:
        section = saved_section
    else:
        section = WORKFLOW_SECTION
    st.session_state["_nav_section"] = section
    return section


def render_navigation(section: str) -> None:
    with st.sidebar:
        st.subheader("Navigation")
        for group_label, items in NAV_GROUPS:
            st.markdown(
                f'<div class="zeus-nav-group-label">{html.escape(group_label)}</div>',
                unsafe_allow_html=True,
            )
            for label, section_key in items:
                if st.button(
                    label,
                    key=f"nav_{section_key}",
                    use_container_width=True,
                    type="primary" if section == section_key else "secondary",
                ):
                    go_to_section(section_key)
        st.divider()


def workflow_navigation_context(section_key: str):
    for index, (step_section, step_label) in enumerate(WORKFLOW_TARGET_STEPS):
        if step_section != section_key:
            continue

        def step_payload(step_index: int) -> dict:
            section, label = WORKFLOW_TARGET_STEPS[step_index]
            return {
                "section": section,
                "label": label,
                "number": f"{step_index + 1:02d}",
                "href": section_href(section, guided=True),
            }

        return {
            "previous": step_payload(index - 1) if index > 0 else None,
            "current": step_payload(index),
            "next": step_payload(index + 1) if index < len(WORKFLOW_TARGET_STEPS) - 1 else None,
            "total": f"{len(WORKFLOW_TARGET_STEPS):02d}",
        }
    return None


def is_guided_mode(section_key: str | None = None) -> bool:
    active_section = section_key or query_param("section") or st.session_state.get("_nav_section", "")
    return query_param("guided") == "1" and active_section in WORKFLOW_TARGET_SECTIONS


def _render_workflow_toolbar_styles() -> None:
    st.markdown(
        """
        <style>
        [data-testid="stElementContainer"]:has(.zeus-guided-toolbar) {
            margin-top: clamp(-1.05rem, -1.8vh, -0.85rem) !important;
        }
        .zeus-guided-toolbar {
            display: grid;
            grid-template-columns: minmax(180px, max-content) 1fr minmax(180px, max-content);
            align-items: center;
            gap: 12px;
            width: 100%;
            min-height: 50px;
            margin: 0 0 clamp(0.8rem, 1.45vh, 1rem) 0;
            padding: 8px 10px;
            border: 1px solid #DBEAFE;
            border-radius: 10px;
            background: #FFFFFF;
            box-shadow: 0 1px 3px rgba(30, 41, 59, 0.06), 0 1px 2px rgba(30, 41, 59, 0.04);
        }
        .zeus-guided-toolbar__link {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            min-height: 34px;
            padding: 7px 14px;
            border: 1px solid #3B82F6;
            border-radius: 8px;
            background: #FFFFFF;
            color: #2563EB;
            font-size: 0.86rem;
            font-weight: 640;
            line-height: 1.2;
            text-decoration: none !important;
            white-space: nowrap;
        }
        .zeus-guided-toolbar__link:hover {
            background: #EFF6FF;
            color: #1D4ED8;
            text-decoration: none !important;
        }
        .zeus-guided-toolbar__link *,
        .zeus-guided-toolbar__link:visited {
            color: #2563EB;
            text-decoration: none !important;
        }
        .zeus-guided-toolbar__link--right {
            justify-self: end;
        }
        .zeus-guided-toolbar__status {
            justify-self: center;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-height: 30px;
            padding: 5px 11px;
            border: 1px solid #DBEAFE;
            border-radius: 999px;
            background: #F0F4FF;
            color: #334155;
            font-size: 0.8rem;
            font-weight: 600;
            line-height: 1.2;
            white-space: nowrap;
        }
        .zeus-guided-toolbar__status strong {
            color: #2563EB;
            font-weight: 700;
        }
        .zeus-guided-toolbar__dot {
            width: 4px;
            height: 4px;
            border-radius: 999px;
            background: #93C5FD;
        }
        @media (max-width: 760px) {
            .zeus-guided-toolbar {
                grid-template-columns: 1fr;
                gap: 10px;
            }
            .zeus-guided-toolbar__link,
            .zeus-guided-toolbar__link--right,
            .zeus-guided-toolbar__status {
                width: 100%;
                justify-self: stretch;
            }
            .zeus-guided-toolbar__status {
                justify-content: center;
                text-align: center;
                white-space: normal;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def workflow_toolbar_html(context: dict | None) -> str:
    if context is None:
        return ""

    current = context["current"]
    previous_step = context["previous"]
    next_step = context["next"]

    if previous_step:
        left_label = f"← {previous_step['label']}"
        left_href = previous_step["href"]
    else:
        left_label = "← Guided Workflow"
        left_href = section_href(WORKFLOW_SECTION)

    if next_step:
        right_label = f"{next_step['label']} →"
        right_href = next_step["href"]
    else:
        right_label = "Guided Workflow →"
        right_href = section_href(WORKFLOW_SECTION)

    status_step = f"Step {current['number']} / {context['total']}"
    return f"""
    <nav class="zeus-guided-toolbar" aria-label="Guided workflow navigation">
        <a class="zeus-guided-toolbar__link" href="{html.escape(left_href, quote=True)}" target="_self">
            {html.escape(left_label)}
        </a>
        <div class="zeus-guided-toolbar__status">
            <strong>{html.escape(status_step)}</strong>
            <span class="zeus-guided-toolbar__dot" aria-hidden="true"></span>
            <span>{html.escape(current['label'])}</span>
        </div>
        <a class="zeus-guided-toolbar__link zeus-guided-toolbar__link--right" href="{html.escape(right_href, quote=True)}" target="_self">
            {html.escape(right_label)}
        </a>
    </nav>
    """


def render_workflow_back_button() -> None:
    section_key = query_param("section") or st.session_state.get("_nav_section", "")
    if not is_guided_mode(section_key):
        return

    context = workflow_navigation_context(section_key)
    if context is None:
        return

    _render_workflow_toolbar_styles()
    st.markdown(workflow_toolbar_html(context), unsafe_allow_html=True)
