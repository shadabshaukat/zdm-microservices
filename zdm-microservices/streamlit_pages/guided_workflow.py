from __future__ import annotations

import html
from typing import Dict, List

import streamlit as st

from streamlit_shared.console_layout import page_panel, render_page_header
from streamlit_shared.context import AppContext
from streamlit_shared.navigation import NAV_SECTIONS, section_href


WorkflowStep = Dict[str, str]
WorkflowGroup = Dict[str, object]

WORKFLOW_GROUPS = (
    {
        "phase": "Prepare Databases",
        "steps": (
            {
                "number": "01",
                "title": "DB Connections",
                "description": "Create source and target database connection records.",
                "action": "Create DB connections",
                "section": "connections",
            },
            {
                "number": "02",
                "title": "Wallets & Credentials",
                "description": "Create reusable database credential wallets for ZDM jobs and discovery tasks.",
                "action": "Create wallets & credentials",
                "section": "wallet",
            },
            {
                "number": "03",
                "title": "DB Discovery",
                "description": "Run source discovery to collect database details needed for ZDM configuration.",
                "action": "Run DB discovery",
                "section": "discovery",
            },
        ),
    },
    {
        "phase": "Design Migration",
        "steps": (
            {
                "number": "04",
                "title": "Projects",
                "description": "Create a migration project that ties source, target, and method together.",
                "action": "Create project",
                "section": "projects",
            },
            {
                "number": "05",
                "title": "Response Files",
                "description": "Create the ZDM response file for the selected migration project.",
                "action": "Create response file",
                "section": "response",
            },
            {
                "number": "06",
                "title": "Job Definitions",
                "description": "Create and save the reusable ZDM command definition to run later.",
                "action": "Create job definition",
                "section": "createjob",
            },
        ),
    },
    {
        "phase": "Execute & Observe",
        "steps": (
            {
                "number": "07",
                "title": "Job Submission",
                "description": "Run a saved job definition and capture the submitted ZDM job ID.",
                "action": "Run job",
                "section": "runjob",
            },
            {
                "number": "08",
                "title": "Job Monitoring",
                "description": "Monitor a job's progress, phases, result files, and logs.",
                "action": "Monitor jobs",
                "section": "jobs",
            },
            {
                "number": "09",
                "title": "Fleet Dashboard",
                "description": "Review fleet-level migration status across projects and ZDM jobs.",
                "action": "View fleet dashboard",
                "section": "fleet_dashboard",
            },
        ),
    },
)


def flatten_workflow_steps() -> tuple:
    steps: List[WorkflowStep] = []
    for group in WORKFLOW_GROUPS:
        steps.extend(group["steps"])  # type: ignore[arg-type]
    return tuple(steps)


def _invalid_target_sections() -> List[str]:
    return [step["section"] for step in flatten_workflow_steps() if step["section"] not in NAV_SECTIONS]


def _render_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stVerticalBlock"][class*="st-key-workflow-phase-"] {
            border-color: #E2E8F0 !important;
            box-shadow: 0 2px 4px rgba(30, 41, 59, 0.04), 0 1px 2px rgba(30, 41, 59, 0.04);
        }
        a.zeus-workflow-card {
            display: block;
            min-height: 128px;
            margin: 0 0 0.72rem 0;
            padding: 0.82rem 0.92rem;
            border: 1px solid #E2E8F0;
            border-radius: 8px;
            background: #FFFFFF;
            box-shadow: 0 1px 2px rgba(30, 41, 59, 0.04);
            color: inherit;
            text-decoration: none;
        }
        a.zeus-workflow-card:hover {
            border-color: #93C5FD;
            background: #F8FBFF;
            box-shadow: 0 3px 6px rgba(30, 41, 59, 0.07);
            text-decoration: none;
        }
        .zeus-workflow-step {
            font-size: 0.68rem;
            line-height: 1.1;
            font-weight: 640;
            color: #64748B;
            margin-bottom: 0.28rem;
        }
        .zeus-workflow-title {
            font-size: 1rem;
            line-height: 1.25;
            font-weight: 680;
            color: #1E293B;
            margin-bottom: 0.35rem;
        }
        .zeus-workflow-description {
            min-height: 2.8rem;
            font-size: 0.84rem;
            line-height: 1.35;
            color: #64748B;
            margin-bottom: 0.55rem;
        }
        .zeus-workflow-action {
            font-size: 0.82rem;
            line-height: 1.2;
            font-weight: 640;
            color: #2563EB;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _render_step_card(step: WorkflowStep) -> None:
    href = section_href(step["section"], guided=True)
    st.markdown(
        f"""
        <a class="zeus-workflow-card" href="{html.escape(href, quote=True)}" target="_self">
            <div class="zeus-workflow-step">Step {html.escape(step["number"])}</div>
            <div class="zeus-workflow-title">{html.escape(step["title"])}</div>
            <div class="zeus-workflow-description">{html.escape(step["description"])}</div>
            <div class="zeus-workflow-action">{html.escape(step["action"])} -&gt;</div>
        </a>
        """,
        unsafe_allow_html=True,
    )


def render(ctx: AppContext) -> None:
    render_page_header(
        "Start Here",
        "Guided Workflow",
        "Follow the ZEUS migration path from database preparation through job execution and fleet monitoring.",
    )

    invalid_sections = _invalid_target_sections()
    if invalid_sections:
        st.error(f"Guided Workflow contains unknown ZEUS sections: {', '.join(invalid_sections)}")
        st.stop()

    _render_styles()

    columns = st.columns(len(WORKFLOW_GROUPS))
    for index, (column, group) in enumerate(zip(columns, WORKFLOW_GROUPS), start=1):
        with column:
            with page_panel(str(group["phase"]), key=f"workflow-phase-{index}"):
                for step in group["steps"]:  # type: ignore[index]
                    _render_step_card(step)
