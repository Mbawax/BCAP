"""Top-level navigation and non-analytical application pages."""

import importlib
from html import escape

import streamlit as st

from campaign_analytics.components.charts import empty_chart
from campaign_analytics.components.layout import section_heading
from campaign_analytics.core.contracts import ModuleManifest
from campaign_analytics.core.navigation import render_sidebar
from campaign_analytics.ui.components import empty_state, kpi_card, page_header
from campaign_analytics.ui.styles import inject_global_styles
from campaign_analytics.ui.upload_workspace import render_upload_workspace


def render_app_shell(registry: list[ModuleManifest]) -> None:
    """Render navigation and route to a core page or an active future module."""
    inject_global_styles()
    selected = render_sidebar(registry)
    if selected == "Dashboard":
        _render_dashboard(registry)
    elif selected == "Data workspace":
        render_upload_workspace()
    else:
        module = next(item for item in registry if item.identifier == selected)
        _render_module(module)


def _render_dashboard(registry: list[ModuleManifest]) -> None:
    page_header(
        "Campaign operations, in one place.",
        "Bring campaign data, reporting performance, and coverage insights into a "
        "single operational workspace.",
        "Borno coverage analysis platform",
    )
    active_modules = [module for module in registry if module.is_available]
    st.markdown(
        "<div class='hero-panel'><h2>Ready for your next campaign run</h2>"
        "<p>Start by staging campaign files, then open a module to map, validate, "
        "analyse, and export operational results.</p></div>",
        unsafe_allow_html=True,
    )
    columns = st.columns(4)
    values = [
        ("Active modules", str(len(active_modules)), "Available for analysis"),
        ("Campaign datasets", "0", "Stage a source file to begin"),
        ("Coverage", "-", "Awaiting vaccination data"),
        ("Reporting rate", "-", "Awaiting team reports"),
    ]
    for column, (label, value, detail) in zip(columns, values, strict=True):
        with column:
            kpi_card(label, value, detail)
    overview_tab, modules_tab, help_tab = st.tabs(
        ["Campaign overview", "Available modules", "Getting started"]
    )
    with overview_tab:
        section_heading(
            "Campaign intelligence",
            "Published module summaries will appear here.",
        )
        st.plotly_chart(
            empty_chart(
                "No campaign results yet",
                "Process a module to populate this campaign-level view.",
            ),
            width='stretch',
            config={"displayModeBar": False},
        )
    with modules_tab:
        section_heading(
            "Analysis modules",
            "Modules are discovered automatically from the modules directory.",
        )
        if active_modules:
            cards = st.columns(min(3, len(active_modules)))
            for index, module in enumerate(active_modules):
                with cards[index % len(cards)]:
                    _render_module_card(module)
        else:
            empty_state(
                "No modules available",
                "Add an active module manifest to make it available here.",
                "+",
            )
    with help_tab:
        section_heading("A repeatable campaign workflow")
        st.markdown(
            "**1. Stage data**  →  **2. Map columns**  →  **3. Validate**  →  "
            "**4. Analyse**  →  **5. Export results**"
        )
        st.caption(
            "Each module follows this same workflow independently, so future "
            "campaign capabilities can be added without changing existing analysis."
        )


def _render_module_card(module: ModuleManifest) -> None:
    st.markdown(
        f"<div class='module-card'><div>{escape(module.icon)}</div>"
        f"<div class='module-card-title'>{escape(module.name)}</div>"
        "<div class='module-card-detail'>Upload, validate, analyse, and export "
        "campaign results.</div></div>",
        unsafe_allow_html=True,
    )


def _render_module(module: ModuleManifest) -> None:
    if not module.is_available:
        page_header(
            module.name,
            "This module has been registered but is not yet enabled.",
            "Future module",
        )
        empty_state(
            "Coming soon",
            "The platform discovered this module from its manifest. Add its entry "
            "point when implementation begins.",
            module.icon,
        )
        return
    module_path, function_name = module.entry_point.rsplit(":", maxsplit=1)
    renderer = getattr(importlib.import_module(module_path), function_name)
    renderer()

