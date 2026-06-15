"""Human-in-the-loop interrupt helpers shared by Streamlit and API layers."""

from __future__ import annotations

from typing import Any


def is_hitl_interrupt(interrupt_payload: Any) -> bool:
    """True when the interrupt is a tool-approval request from HITL middleware."""
    return isinstance(interrupt_payload, dict) and bool(interrupt_payload.get("action_requests"))


def ui_mode_from_interrupt(interrupt_payload: Any | None) -> str:
    """UI mode derived from checkpoint interrupt payload."""
    if interrupt_payload is None:
        return "idle"
    if is_hitl_interrupt(interrupt_payload):
        return "hitl"
    return "user_input"


def ui_mode_from_state(interrupt_payload: Any | None, state: Any) -> str:
    """Canonical UI mode from checkpoint interrupt + graph state."""
    if interrupt_payload is not None:
        return ui_mode_from_interrupt(interrupt_payload)
    if state is not None:
        next_nodes = getattr(state, "next", None)
        if next_nodes:
            return "running"
    return "idle"


def build_hitl_resume_decision(
    decision: str,
    *,
    tool_name: str = "tool",
    edited_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a single HITL decision dict for ``Command(resume=...)``."""
    if decision == "edit":
        return {
            "type": "edit",
            "edited_action": {"name": tool_name, "args": edited_args or {}},
        }
    if decision == "reject":
        return {"type": "reject", "message": "User rejected this tool call."}
    return {"type": "approve"}
