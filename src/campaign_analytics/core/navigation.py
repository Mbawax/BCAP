"""Sidebar navigation for platform and manifest-discovered modules."""

from html import escape

import streamlit as st

from campaign_analytics.core.contracts import ModuleManifest
from campaign_analytics.core.registry import group_modules


def render_sidebar(registry: list[ModuleManifest]) -> str:
    """Render platform navigation and return the selected route identifier."""
    with st.sidebar:
        st.markdown('<div class="brand-mark">✚</div>', unsafe_allow_html=True)
        st.markdown(
            '<div class="brand-name">Campaign Analytics</div>',
            unsafe_allow_html=True,
        )
        st.caption("Campaign operations platform")
        st.markdown('<div class="nav-section">Workspace</div>', unsafe_allow_html=True)
        options: dict[str, str] = {
            "Dashboard": "▦  Overview",
            "Data workspace": "↥  Data workspace",
        }
        for group, modules in group_modules(registry).items():
            st.markdown(
                f'<div class="nav-section">{escape(group)}</div>',
                unsafe_allow_html=True,
            )
            for module in modules:
                suffix = "" if module.is_available else " · Soon"
                options[module.identifier] = f"{module.icon}  {module.name}{suffix}"
        route_ids = list(options)
        selected = st.radio(
            "Navigation",
            route_ids,
            index=_selected_index(route_ids),
            format_func=options.get,
            label_visibility="collapsed",
            key="platform_navigation",
        )
        st.session_state.active_page = selected
        st.markdown(
            '<div class="sidebar-footer">Foundation release</div>',
            unsafe_allow_html=True,
        )
    return selected


def _selected_index(route_ids: list[str]) -> int:
    active_page = st.session_state.active_page
    return route_ids.index(active_page) if active_page in route_ids else 0

