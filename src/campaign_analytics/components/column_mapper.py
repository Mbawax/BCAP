"""Reusable source-column mapper for modules with canonical data fields."""

from collections.abc import Mapping

import streamlit as st

UNMAPPED = "Not mapped"


def render_column_mapper(
    fields: list[str],
    required_fields: set[str],
    source_columns: list[str],
    suggestions: Mapping[str, str | None],
    key_prefix: str,
) -> dict[str, str | None]:
    """Render a two-column mapper and return canonical-to-source mappings."""
    options = [UNMAPPED, *source_columns]
    result: dict[str, str | None] = {}
    left, right = st.columns(2)
    for index, field in enumerate(fields):
        label = field.replace("_", " ").title()
        if field in required_fields:
            label += " *"
        default = suggestions.get(field) or UNMAPPED
        with left if index % 2 == 0 else right:
            selected = st.selectbox(
                label,
                options,
                index=options.index(default),
                key=f"{key_prefix}_{field}",
            )
        result[field] = selected if selected != UNMAPPED else None
    return result

