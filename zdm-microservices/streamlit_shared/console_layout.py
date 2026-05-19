from __future__ import annotations

import html
import base64
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import streamlit as st


SERVICE_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = SERVICE_ROOT / "assets"
ZEUS_LOGO = ASSET_DIR / "ZEUS-logo.png"


def render_console_shell_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --zeus-primary: #2563EB;
            --zeus-primary-mid: #3B82F6;
            --zeus-primary-dark: #1D4ED8;
            --zeus-primary-soft: #EFF6FF;
            --zeus-background: #F6F8FB;
            --zeus-surface: #FFFFFF;
            --zeus-surface-subtle: #F9FAFB;
            --zeus-border: #E2E8F0;
            --zeus-border-strong: #A7B6CA;
            --zeus-text: #1E293B;
            --zeus-text-muted: #64748B;
            --zeus-success: #10B981;
            --zeus-warning: #F59E0B;
            --zeus-error: #EF4444;
            --zeus-shadow-subtle: 0 1px 2px rgba(15, 23, 42, 0.05), 0 1px 3px rgba(15, 23, 42, 0.04);
            --zeus-shadow-medium: 0 8px 18px rgba(15, 23, 42, 0.07), 0 2px 6px rgba(15, 23, 42, 0.04);
            --zeus-radius: 8px;
            --zeus-mono: "Roboto Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace;
            --zeus-sans: "Roboto", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
            --zeus-main-pad-x: clamp(1rem, 3.4vw, 3rem);
            --zeus-main-pad-bottom: clamp(1.25rem, 3vh, 3rem);
            --zeus-panel-pad-y: clamp(1rem, 1.8vh, 1.2rem);
            --zeus-panel-pad-x: clamp(1rem, 2.1vw, 1.35rem);
            --zeus-panel-gap: clamp(0.42rem, 0.85vh, 0.58rem);
            --zeus-panel-heading-gap: clamp(0.82rem, 1.15vh, 1rem);
        }

        html,
        body,
        [data-testid="stAppViewContainer"] {
            background: var(--zeus-background);
            color: var(--zeus-text);
            font-family: var(--zeus-sans);
        }

        html,
        body,
        #root,
        [data-testid="stApp"],
        [data-testid="stAppViewContainer"] {
            min-height: 100vh;
            width: 100%;
        }

        [data-testid="stHeader"],
        [data-testid="stToolbar"],
        [data-testid="stToolbarActions"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stAppDeployButton"],
        [data-testid="stMainMenu"],
        [data-testid="stSidebarHeader"] {
            display: none !important;
            height: 0 !important;
        }

        [data-testid="stSidebar"] {
            background: var(--zeus-surface);
            border-right: 1px solid var(--zeus-border);
            box-shadow: var(--zeus-shadow-subtle);
        }

        [data-testid="stSidebarContent"] {
            padding-top: 0.25rem;
            min-height: 100vh;
        }

        [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {
            gap: clamp(0.48rem, 0.85vh, 0.72rem);
        }

        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] h3,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
        [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] strong {
            color: var(--zeus-text);
        }

        .zeus-nav-group-label {
            position: relative;
            display: flex;
            align-items: center;
            gap: 7px;
            margin: clamp(0.78rem, 1.15vh, 1.05rem) 0 0 0;
            padding: 0.08rem 0 0.46rem 0;
            border-bottom: 1px solid var(--zeus-border);
            color: var(--zeus-text-muted);
            font-family: var(--zeus-sans);
            font-size: 0.72rem;
            font-weight: 700;
            line-height: 1.2;
            letter-spacing: 0.04em;
            text-transform: uppercase;
        }

        .zeus-nav-group-label::before {
            width: 3px;
            height: 13px;
            border-radius: 999px;
            background: #CBD5E1;
            content: "";
        }

        .zeus-nav-group-label--active {
            border-bottom-color: #BFDBFE;
            color: var(--zeus-text);
        }

        .zeus-nav-group-label--active::before {
            background: var(--zeus-primary);
        }

        [data-testid="stSidebar"] [data-testid="stElementContainer"]:has(.zeus-nav-group-label) {
            margin-bottom: 0.34rem !important;
        }

        [data-testid="stMainBlockContainer"],
        [data-testid="stAppViewContainer"] .main .block-container {
            max-width: none;
            padding-top: 0 !important;
            padding-left: var(--zeus-main-pad-x) !important;
            padding-right: var(--zeus-main-pad-x) !important;
            padding-bottom: var(--zeus-main-pad-bottom) !important;
        }

        .zeus-sidebar-brand {
            display: flex;
            align-items: center;
            gap: 10px;
            margin: 0 0 0.8rem 0;
            padding: 10px 12px;
            border: 1px solid var(--zeus-border);
            border-radius: 12px;
            background: #FFFFFF;
            box-shadow: var(--zeus-shadow-subtle);
        }

        .zeus-sidebar-brand__logo {
            width: 40px;
            height: 40px;
            flex: 0 0 40px;
            object-fit: contain;
        }

        .zeus-sidebar-brand__title {
            margin: 0.1rem 0 0 0;
            color: var(--zeus-text);
            font-family: var(--zeus-sans);
            font-size: 1.03rem;
            font-weight: 800;
            line-height: 1.15;
            letter-spacing: 0;
        }

        .zeus-sidebar-brand__subtitle {
            margin: 0.18rem 0 0 0;
            color: var(--zeus-text-muted);
            font-size: 0.76rem;
            line-height: 1.25;
        }

        [data-testid="stSidebar"] [data-testid="stHeading"] {
            margin: 0.35rem 0 0.25rem 0;
        }

        [data-testid="stSidebar"] [data-testid="stHeading"] h3 {
            font-size: 1rem;
            line-height: 1.2;
        }

        .zeus-console-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 18px;
            min-height: clamp(40px, 5vh, 44px);
            margin: 0 0 clamp(0.75rem, 1.5vh, 1rem) 0;
            padding: 0 0 clamp(10px, 1.4vh, 12px) 0;
            border-bottom: 1px solid var(--zeus-border);
            background: transparent;
        }

        .zeus-console-header__brand {
            display: flex;
            align-items: baseline;
            gap: 10px;
            min-width: 0;
        }

        .zeus-console-header__brand strong {
            color: var(--zeus-text);
            font-family: var(--zeus-sans);
            font-size: 1.08rem;
            font-weight: 850;
            line-height: 1.2;
        }

        .zeus-console-header__brand span {
            color: var(--zeus-text-muted);
            font-size: 0.92rem;
            font-weight: 600;
            line-height: 1.2;
        }

        .zeus-product-identity {
            display: grid;
            gap: 0.34rem;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-settings-stack"] {
            max-width: min(100%, 860px);
            gap: clamp(0.78rem, 1.45vh, 1.05rem) !important;
        }

        .zeus-product-identity__name {
            margin: 0;
            color: var(--zeus-text);
            font-size: 1rem;
            font-weight: 720;
            line-height: 1.25;
        }

        .zeus-product-identity__description {
            margin: 0;
            color: var(--zeus-text-muted);
            font-size: 0.9rem;
            line-height: 1.42;
        }

        .zeus-console-header__meta {
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 8px;
            min-width: 0;
            color: var(--zeus-text-muted);
            font-size: 0.78rem;
            line-height: 1.2;
            white-space: nowrap;
        }

        .zeus-console-header__status {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            min-height: 30px;
            padding: 5px 12px;
            overflow: hidden;
            border: 1px solid #BBF7D0;
            border-radius: 999px;
            background: #DCFCE7;
            color: #166534;
            font-size: 0.82rem;
            font-weight: 800;
            text-overflow: ellipsis;
        }

        .zeus-console-header__status--warning {
            border-color: #FDE68A;
            background: #FEF3C7;
            color: #92400E;
        }

        .zeus-console-header__status-dot {
            width: 8px;
            height: 8px;
            border-radius: 999px;
            background: var(--zeus-success);
        }

        .zeus-console-header__status--warning .zeus-console-header__status-dot {
            background: var(--zeus-warning);
        }

        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]),
        [data-testid="stException"] {
            border: 1px solid #FDE68A !important;
            border-radius: var(--zeus-radius) !important;
            background: #FFFBEB !important;
            color: #92400E !important;
            box-shadow: none !important;
        }

        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) [data-testid="stAlertContentError"],
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) [data-testid="stMarkdownContainer"],
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) p,
        [data-testid="stAlertContainer"]:has([data-testid="stAlertContentError"]) svg,
        [data-testid="stException"] *,
        [data-testid="stException"] svg {
            color: #92400E !important;
            fill: #92400E !important;
        }

        [data-testid="stException"] pre,
        [data-testid="stException"] code {
            color: var(--zeus-text) !important;
            background: #FFFFFF !important;
        }

        .zeus-page-header {
            margin: 0 0 clamp(1rem, 2vh, 1.25rem) 0;
            padding-bottom: clamp(0.95rem, 1.8vh, 1.15rem);
            border-bottom: 1px solid var(--zeus-border);
        }

        .zeus-page-header__category {
            margin: 0 0 0.18rem 0;
            color: var(--zeus-primary-dark);
            font-family: var(--zeus-mono);
            font-size: 0.82rem !important;
            font-weight: 680;
            line-height: 1.25;
            letter-spacing: 0;
            text-transform: uppercase;
        }

        .zeus-page-header__title {
            margin: 0.15rem 0 0 0;
            color: var(--zeus-text);
            font-family: var(--zeus-sans);
            font-size: 2rem;
            font-weight: 660;
            line-height: 1.12;
            letter-spacing: 0;
        }

        .zeus-page-header__description {
            max-width: 760px;
            margin: 0.45rem 0 0 0;
            color: var(--zeus-text-muted);
            font-size: 0.96rem;
            line-height: 1.45;
        }

        .zeus-panel-heading {
            margin: 0 0 var(--zeus-panel-heading-gap) 0;
            color: var(--zeus-text);
            font-family: var(--zeus-sans);
            font-size: 1.32rem;
            font-weight: 680;
            line-height: 1.2;
            letter-spacing: 0;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"],
        div[data-testid="stVerticalBlockBorderWrapper"] {
            border-color: var(--zeus-border) !important;
            border-radius: 12px !important;
            background: var(--zeus-surface) !important;
            box-shadow: var(--zeus-shadow-medium);
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] {
            gap: var(--zeus-panel-gap) !important;
            padding: var(--zeus-panel-pad-y) var(--zeus-panel-pad-x) !important;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stVerticalBlock"] {
            gap: var(--zeus-panel-gap) !important;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stElementContainer"] {
            margin-bottom: 0 !important;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stElementContainer"]:has(.zeus-panel-heading) {
            margin-bottom: clamp(0.45rem, 1vh, 0.7rem) !important;
        }

        [data-testid="stForm"] {
            border: 0 !important;
            background: transparent !important;
            box-shadow: none !important;
            padding: 0 !important;
        }

        .stButton > button,
        .stFormSubmitButton > button,
        [data-testid="stBaseButton-primary"],
        [data-testid="stBaseButton-secondary"] {
            min-height: 42px;
            border-radius: var(--zeus-radius);
            font-weight: 700;
            letter-spacing: 0;
        }

        .stButton > button[kind="primary"],
        .stButton > button[data-testid="baseButton-primary"],
        .stFormSubmitButton > button[kind="primary"],
        .stFormSubmitButton > button[data-testid="baseButton-primary"],
        [data-testid="stBaseButton-primary"],
        [data-testid="baseButton-primary"] {
            border: 1px solid var(--zeus-primary) !important;
            background: var(--zeus-primary) !important;
            color: #FFFFFF !important;
        }

        .stButton > button[kind="primary"] *,
        .stButton > button[data-testid="baseButton-primary"] *,
        .stFormSubmitButton > button[kind="primary"] *,
        .stFormSubmitButton > button[data-testid="baseButton-primary"] *,
        [data-testid="stBaseButton-primary"] *,
        [data-testid="baseButton-primary"] * {
            color: #FFFFFF !important;
        }

        .stButton > button[kind="primary"]:hover,
        .stButton > button[data-testid="baseButton-primary"]:hover,
        .stFormSubmitButton > button[kind="primary"]:hover,
        .stFormSubmitButton > button[data-testid="baseButton-primary"]:hover,
        [data-testid="stBaseButton-primary"]:hover,
        [data-testid="baseButton-primary"]:hover {
            border-color: var(--zeus-primary-dark) !important;
            background: var(--zeus-primary-dark) !important;
            color: #FFFFFF !important;
        }

        .stButton > button[kind="secondary"],
        .stButton > button[data-testid="baseButton-secondary"],
        .stFormSubmitButton > button[kind="secondary"],
        .stFormSubmitButton > button[data-testid="baseButton-secondary"],
        [data-testid="stBaseButton-secondary"],
        [data-testid="baseButton-secondary"] {
            border: 1px solid var(--zeus-border-strong) !important;
            background: #FFFFFF !important;
            color: var(--zeus-primary-dark) !important;
        }

        .stButton > button[kind="secondary"] *,
        .stButton > button[data-testid="baseButton-secondary"] *,
        .stFormSubmitButton > button[kind="secondary"] *,
        .stFormSubmitButton > button[data-testid="baseButton-secondary"] *,
        [data-testid="stBaseButton-secondary"] *,
        [data-testid="baseButton-secondary"] * {
            color: var(--zeus-primary-dark) !important;
        }

        .stButton > button[kind="secondary"]:hover,
        .stButton > button[data-testid="baseButton-secondary"]:hover,
        .stFormSubmitButton > button[kind="secondary"]:hover,
        .stFormSubmitButton > button[data-testid="baseButton-secondary"]:hover,
        [data-testid="stBaseButton-secondary"]:hover,
        [data-testid="baseButton-secondary"]:hover {
            border-color: var(--zeus-primary) !important;
            background: var(--zeus-primary-soft) !important;
            color: var(--zeus-primary-dark) !important;
        }

        [data-baseweb="tag"] {
            border-color: var(--zeus-primary) !important;
            background-color: var(--zeus-primary) !important;
            color: #FFFFFF !important;
        }

        [data-baseweb="tag"] *,
        [data-baseweb="tag"] svg {
            color: #FFFFFF !important;
            fill: #FFFFFF !important;
        }

        [data-baseweb="radio"] [aria-checked="true"],
        [data-testid="stRadio"] [aria-checked="true"],
        [data-testid="stRadio"] label:has(input:checked) > div:first-child,
        label[data-baseweb="radio"]:has(input:checked) > div:first-child {
            border-color: var(--zeus-primary) !important;
            background-color: var(--zeus-primary) !important;
        }

        [data-baseweb="radio"] [aria-checked="true"] *,
        [data-testid="stRadio"] [aria-checked="true"] *,
        [data-testid="stRadio"] label:has(input:checked) > div:first-child *,
        label[data-baseweb="radio"]:has(input:checked) > div:first-child * {
            border-color: var(--zeus-primary) !important;
            background-color: var(--zeus-primary) !important;
        }

        [data-testid="stSidebar"] .stButton > button {
            align-items: center !important;
            justify-content: flex-start !important;
            min-height: 36px;
            padding: 6px 14px;
            border-radius: 8px;
            font-size: 0.88rem;
            font-weight: 580;
            line-height: 1.15;
            text-align: left !important;
        }

        [data-testid="stSidebar"] .stButton > button [data-testid="stMarkdownContainer"],
        [data-testid="stSidebar"] .stButton > button div,
        [data-testid="stSidebar"] .stButton > button p {
            display: block;
            flex: 1 1 auto;
            width: 100%;
            text-align: left !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"],
        [data-testid="stSidebar"] .stButton > button[data-testid="baseButton-secondary"] {
            color: var(--zeus-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"] *,
        [data-testid="stSidebar"] .stButton > button[data-testid="baseButton-secondary"] * {
            color: var(--zeus-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover,
        [data-testid="stSidebar"] .stButton > button[data-testid="baseButton-secondary"]:hover {
            color: var(--zeus-text) !important;
        }

        [data-testid="stSidebar"] .stButton > button[kind="secondary"]:hover *,
        [data-testid="stSidebar"] .stButton > button[data-testid="baseButton-secondary"]:hover * {
            color: var(--zeus-text) !important;
        }

        [data-testid="stDataFrame"],
        [data-testid="stDataEditor"] {
            overflow: hidden;
            border: 1px solid var(--zeus-border) !important;
            border-radius: 10px !important;
            background: #FFFFFF !important;
            box-shadow: none !important;
        }

        [data-testid="stDataFrame"] [role="grid"],
        [data-testid="stDataEditor"] [role="grid"] {
            border-color: var(--zeus-border) !important;
            background: #FFFFFF !important;
        }

        [data-testid="stDataFrame"] canvas,
        [data-testid="stDataEditor"] canvas {
            background: #FFFFFF !important;
        }

        div[data-baseweb="input"] > div,
        div[data-baseweb="select"] > div,
        [data-testid="stTextInputRootElement"],
        [data-testid="stNumberInputContainer"],
        textarea {
            min-height: 38px;
            border: 1px solid var(--zeus-border-strong) !important;
            border-color: var(--zeus-border-strong) !important;
            border-radius: var(--zeus-radius) !important;
            background-color: #FFFFFF !important;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stWidgetLabel"] {
            min-height: 1rem;
            margin-bottom: 0.18rem;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stWidgetLabel"] p,
        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stCaptionContainer"] p {
            font-size: 0.82rem;
            line-height: 1.28;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stWidgetLabel"] p {
            color: var(--zeus-text);
            font-weight: 640;
        }

        div[data-testid="stVerticalBlock"][class*="st-key-zeus-panel-"] [data-testid="stCaptionContainer"] {
            margin-top: -0.08rem;
        }

        div[data-baseweb="input"]:focus-within > div,
        div[data-baseweb="select"]:focus-within > div,
        [data-testid="stTextInputRootElement"]:focus-within,
        [data-testid="stNumberInputContainer"]:focus-within,
        textarea:focus {
            border-color: var(--zeus-primary) !important;
            box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.15) !important;
        }

        .stTabs [data-baseweb="tab-list"] {
            gap: 6px;
            border-bottom: 1px solid var(--zeus-border);
        }

        .stTabs [data-baseweb="tab"] {
            border-radius: 8px 8px 0 0;
            color: var(--zeus-text-muted);
            font-weight: 700;
        }

        .stTabs [aria-selected="true"] {
            color: var(--zeus-primary-dark) !important;
            background: rgba(239, 246, 255, 0.88);
        }

        .stTabs [data-baseweb="tab-highlight"] {
            background-color: var(--zeus-primary) !important;
        }

        .stTabs [data-baseweb="tab"][aria-selected="true"] {
            border-bottom-color: var(--zeus-primary) !important;
            box-shadow: inset 0 -2px 0 var(--zeus-primary) !important;
        }

        hr {
            border-color: var(--zeus-border);
        }

        @media (max-width: 760px) {
            [data-testid="stMainBlockContainer"],
            [data-testid="stAppViewContainer"] .main .block-container {
                padding-left: 1rem !important;
                padding-right: 1rem !important;
            }

            .zeus-console-header {
                align-items: flex-start;
                flex-direction: column;
                gap: 8px;
            }

            .zeus-console-header__brand {
                flex-direction: column;
                gap: 2px;
            }

            .zeus-console-header__meta {
                width: 100%;
                justify-content: flex-start;
                flex-wrap: wrap;
                white-space: normal;
            }

            .zeus-page-header__title {
                font-size: 1.55rem;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_brand() -> None:
    logo_html = ""
    if ZEUS_LOGO.exists():
        encoded_logo = base64.b64encode(ZEUS_LOGO.read_bytes()).decode("ascii")
        logo_html = (
            f'<img class="zeus-sidebar-brand__logo" '
            f'src="data:image/png;base64,{encoded_logo}" alt="ZEUS logo" />'
        )
    with st.sidebar:
        st.markdown(
            f"""
            <div class="zeus-sidebar-brand">
                {logo_html}
                <div>
                    <div class="zeus-sidebar-brand__title">ZEUS Console</div>
                    <div class="zeus-sidebar-brand__subtitle">Fleet migration operations</div>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )


def render_console_header(*, api_base: str, username: str) -> None:
    configured = bool(api_base and username)
    status_label = "Backend configured" if configured else "Backend not configured"
    status_class = "" if configured else " zeus-console-header__status--warning"
    st.markdown(
        f"""
        <header class="zeus-console-header">
            <div class="zeus-console-header__brand">
                <strong>ZEUS</strong>
                <span>ZDM migration control plane</span>
            </div>
            <div class="zeus-console-header__meta">
                <span class="zeus-console-header__status{status_class}">
                    <span class="zeus-console-header__status-dot" aria-hidden="true"></span>
                    {html.escape(status_label)}
                </span>
            </div>
        </header>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(category: str, title: str, description: str) -> None:
    st.markdown(
        f"""
        <section class="zeus-page-header">
            <p class="zeus-page-header__category">{html.escape(category)}</p>
            <div class="zeus-page-header__title" role="heading" aria-level="1">{html.escape(title)}</div>
            <p class="zeus-page-header__description">{html.escape(description)}</p>
        </section>
        """,
        unsafe_allow_html=True,
    )


def _panel_key(title: str | None) -> str | None:
    if not title:
        return None
    slug_chars = [char.lower() if char.isalnum() else "-" for char in title]
    slug = "-".join(part for part in "".join(slug_chars).split("-") if part)
    return f"zeus-panel-{slug or 'section'}"


@contextmanager
def page_panel(title: str | None = None, *, key: str | None = None) -> Iterator[None]:
    panel_key = key or _panel_key(title)
    with st.container(border=True, key=panel_key):
        if title:
            st.markdown(f'<div class="zeus-panel-heading">{html.escape(title)}</div>', unsafe_allow_html=True)
        yield
