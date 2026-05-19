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
                "title": "DB Wallets & Credentials",
                "description": "Create reusable database credential wallets for ZDM jobs and discovery tasks.",
                "action": "Create wallets & credentials",
                "section": "wallet",
            },
            {
                "number": "02",
                "title": "DB Connections",
                "description": "Create source and target database connection records and bind each to a credential wallet.",
                "action": "Create DB connections",
                "section": "connections",
            },
        ),
    },
    {
        "phase": "Design Migration",
        "steps": (
            {
                "number": "03",
                "title": "Projects",
                "description": "Create a migration project that ties source, target, and method together.",
                "action": "Create project",
                "section": "projects",
            },
            {
                "number": "04",
                "title": "Database Discovery",
                "description": "Refresh and review source and target discovery snapshots for a project.",
                "action": "Review discovery",
                "section": "discovery",
            },
            {
                "number": "05",
                "title": "ZDM Response Files",
                "description": "Create the ZDM response file for the selected migration project.",
                "action": "Create response file",
                "section": "response",
            },
            {
                "number": "06",
                "title": "ZDM Job Definitions",
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
                "title": "ZDM Job Submission",
                "description": "Run a saved job definition and capture the submitted ZDM job ID.",
                "action": "Run job",
                "section": "runjob",
            },
            {
                "number": "08",
                "title": "ZDM Job Monitoring",
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
            background: linear-gradient(180deg, #FFFFFF 0%, #F8FAFC 100%) !important;
            box-shadow: 0 1px 2px rgba(30, 41, 59, 0.035) !important;
        }

        .zeus-workflow-timeline {
            display: grid;
            gap: 0;
        }

        .zeus-workflow-step-row {
            position: relative;
            display: grid;
            grid-template-columns: 2.35rem minmax(0, 1fr);
            column-gap: 0.78rem;
            min-height: 132px;
            padding: 0.82rem 0.36rem 0.95rem 0.1rem;
            border-bottom: 1px solid #E2E8F0;
            border-radius: 8px;
            color: inherit;
            text-decoration: none;
            transition: background 120ms ease, transform 120ms ease;
        }

        .zeus-workflow-step-row,
        .zeus-workflow-step-row * {
            text-decoration: none !important;
        }

        .zeus-workflow-step-row::before {
            content: "";
            position: absolute;
            left: 1.17rem;
            top: 3.08rem;
            bottom: -0.4rem;
            width: 1px;
            background: #CBD5E1;
        }

        .zeus-workflow-step-row--last {
            border-bottom: 0;
        }

        .zeus-workflow-step-row--last::before {
            display: none;
        }

        .zeus-workflow-step-row:hover {
            background: #F8FBFF;
            transform: translateX(2px);
            text-decoration: none;
        }

        .zeus-workflow-step-row:focus-visible {
            outline: 3px solid rgba(37, 99, 235, 0.24);
            outline-offset: 2px;
        }

        .zeus-workflow-step-marker {
            position: relative;
            z-index: 1;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 2.35rem;
            height: 2.35rem;
            border: 1px solid #BFDBFE;
            border-radius: 999px;
            background: #EFF6FF;
            color: #1D4ED8;
            font-size: 0.78rem;
            font-weight: 800;
            line-height: 1;
            letter-spacing: 0;
        }

        .zeus-workflow-step-content {
            min-width: 0;
            padding-top: 0.08rem;
        }

        .zeus-workflow-step-title {
            display: block;
            margin: 0 0 0.46rem 0;
            color: #1E293B;
            font-size: 1.18rem;
            line-height: 1.22;
            font-weight: 800;
        }

        .zeus-workflow-step-description {
            display: block;
            margin: 0 0 0.72rem 0;
            color: #64748B;
            font-size: 0.95rem;
            line-height: 1.42;
        }

        .zeus-workflow-step-action {
            display: inline-flex;
            align-items: center;
            color: #2563EB;
            font-size: 0.92rem;
            line-height: 1.25;
            font-weight: 720;
        }

        @media (max-width: 700px) {
            .zeus-workflow-step-row {
                min-height: 0;
                padding-top: 0.88rem;
                padding-bottom: 1rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def _step_row_markup(step: WorkflowStep) -> str:
    href = section_href(step["section"], guided=True)
    return f"""
        <a class="zeus-workflow-step-row" href="{html.escape(href, quote=True)}" target="_self" role="listitem">
            <span class="zeus-workflow-step-marker">{html.escape(step["number"])}</span>
            <span class="zeus-workflow-step-content">
                <span class="zeus-workflow-step-title">{html.escape(step["title"])}</span>
                <span class="zeus-workflow-step-description">{html.escape(step["description"])}</span>
                <span class="zeus-workflow-step-action">{html.escape(step["action"])} -&gt;</span>
            </span>
        </a>
    """


def _render_step_timeline(steps: tuple[WorkflowStep, ...]) -> None:
    rows = []
    last_index = len(steps) - 1
    for index, step in enumerate(steps):
        row = _step_row_markup(step)
        if index == last_index:
            row = row.replace("zeus-workflow-step-row", "zeus-workflow-step-row zeus-workflow-step-row--last", 1)
        rows.append(row)
    st.markdown(
        f"""
        <div class="zeus-workflow-timeline" role="list">
            {''.join(rows)}
        </div>
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
                _render_step_timeline(group["steps"])  # type: ignore[arg-type]
