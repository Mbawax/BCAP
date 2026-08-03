"""Layout primitives that keep platform and module pages visually consistent."""

from html import escape

import streamlit as st


def page_header(
    title: str,
    description: str,
    eyebrow: str = "Campaign Analytics",
) -> None:
    """Render a consistent, product-style page heading."""
    st.markdown(
        f'<div class="platform-eyebrow">{escape(eyebrow)}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<h1 class="platform-title">{escape(title)}</h1>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="platform-subtitle">{escape(description)}</div>',
        unsafe_allow_html=True,
    )


def section_heading(title: str, description: str | None = None) -> None:
    """Render a compact heading for a page section."""
    st.markdown(
        f'<div class="section-heading">{escape(title)}</div>',
        unsafe_allow_html=True,
    )
    if description:
        st.caption(description)


def empty_state(title: str, message: str, icon: str = "○") -> None:
    """Render a consistent empty state inside a styled panel."""
    st.markdown(
        f'<div class="empty-state"><div class="empty-icon">{escape(icon)}</div>'
        f'<div><strong>{escape(title)}</strong><br>'
        f'<span>{escape(message)}</span></div></div>',
        unsafe_allow_html=True,
    )

