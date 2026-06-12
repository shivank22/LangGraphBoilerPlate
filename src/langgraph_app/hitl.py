"""Human-in-the-loop interrupt helpers shared by Streamlit and API layers."""

from __future__ import annotations

from typing import Any


def is_hitl_interrupt(interrupt_payload: Any) -> bool:
    """True when the interrupt is a tool-approval request from HITL middleware."""
    return isinstance(interrupt_payload, dict) and bool(interrupt_payload.get("action_requests"))


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
