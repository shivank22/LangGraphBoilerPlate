"""Human-in-the-loop middleware factory.

Wraps the built-in `HumanInTheLoopMiddleware` so the list of tools that
require approval is read from `settings.hitl_tools`. Any tool not in that
list is auto-approved.

UI integration: on interrupt, the agent returns an `__interrupt__` payload.
Resume with `Command(resume=[{"type": "approve|edit|reject", ...}])`.
"""

from __future__ import annotations

from collections.abc import Iterable

from langchain.agents.middleware import HumanInTheLoopMiddleware

from ..config import settings


DEFAULT_ALLOWED_DECISIONS = ["approve", "edit", "reject"]


def build_hitl_middleware(
    tools: Iterable[str] | None = None,
    *,
    allowed_decisions: list[str] | None = None,
    description_prefix: str = "Tool execution requires approval",
) -> HumanInTheLoopMiddleware:
    """Return a `HumanInTheLoopMiddleware` instance configured from settings."""
    tool_names = list(tools) if tools is not None else list(settings.hitl_tools)
    decisions = allowed_decisions or DEFAULT_ALLOWED_DECISIONS

    interrupt_on = {name: {"allowed_decisions": decisions} for name in tool_names}

    return HumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
        description_prefix=description_prefix,
    )
