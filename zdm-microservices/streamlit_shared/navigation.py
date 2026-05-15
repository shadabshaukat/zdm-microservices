from __future__ import annotations

import streamlit as st

from streamlit_shared.ui import query_param


NAV_GROUPS = [
    (
        "Database Setup",
        [
            ("DB Connections", "connections"),
            ("DB Wallets & Credentials", "wallet"),
            ("DB Discovery", "discovery"),
        ],
    ),
    (
        "Migrations",
        [
            ("Projects", "projects"),
            ("ZDM Response Files", "response"),
            ("ZDM Job Definitions", "createjob"),
            ("ZDM Job Submission", "runjob"),
            ("ZDM Job Monitoring", "jobs"),
            ("Migration Dashboard", "fleet_dashboard"),
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


def select_section() -> str:
    requested_section = query_param("section")
    saved_section = st.session_state.get("_nav_section")
    if requested_section in NAV_SECTIONS:
        section = requested_section
    elif saved_section in NAV_SECTIONS:
        section = saved_section
    else:
        section = "connections"
    st.session_state["_nav_section"] = section
    return section


def render_navigation(section: str) -> None:
    with st.sidebar:
        st.subheader("Navigation")
        for group_label, items in NAV_GROUPS:
            st.markdown(f"**{group_label}**")
            for label, section_key in items:
                if st.button(
                    label,
                    key=f"nav_{section_key}",
                    use_container_width=True,
                    type="primary" if section == section_key else "secondary",
                ):
                    st.session_state["_nav_section"] = section_key
                    st.query_params["section"] = section_key
                    st.rerun()
        st.divider()
