"""Skill execution progress stepper for the chat UI."""

from __future__ import annotations

from typing import Any

import streamlit as st

from langgraph_app.skill_progress import (
    STATUS_COMPLETED,
    STATUS_IN_PROGRESS,
    STATUS_PENDING,
    STATUS_WAITING,
)


_STATUS_ICONS = {
    STATUS_COMPLETED: "\u2713",
    STATUS_IN_PROGRESS: "\u25b6",
    STATUS_WAITING: "\u23f8",
    STATUS_PENDING: "\u25cb",
}


def _has_started(progress: dict[str, Any]) -> bool:
    phases = progress.get("phases") or {}
    return any(
        (phase or {}).get("status") != STATUS_PENDING
        for phase in phases.values()
    )


def render_skill_progress(progress: dict[str, Any], phases: list[dict[str, str]]) -> None:
    """Render a vertical step list for the active skill run."""
    if not progress or not progress.get("skill") or not phases:
        return
    if not _has_started(progress):
        return

    skill_name = progress.get("skill", "skill")
    phase_states: dict[str, Any] = progress.get("phases") or {}

    with st.container(border=True):
        st.markdown(f"**Skill progress:** `{skill_name}`")
        for phase in phases:
            phase_id = phase["id"]
            label = phase.get("label", phase_id)
            state = phase_states.get(phase_id, {})
            status = state.get("status", STATUS_PENDING)
            detail = state.get("detail")
            icon = _STATUS_ICONS.get(status, _STATUS_ICONS[STATUS_PENDING])

            if status == STATUS_COMPLETED:
                style = "color: #6b9e7a;"
            elif status == STATUS_IN_PROGRESS:
                style = "color: #4c8bf5; font-weight: 600;"
            elif status == STATUS_WAITING:
                style = "color: #d4a017; font-weight: 600;"
            else:
                style = "color: #888;"

            line = f"{icon} {label}"
            if detail:
                line += f" — {detail}"
            st.markdown(f'<div style="{style} margin: 4px 0;">{line}</div>', unsafe_allow_html=True)
