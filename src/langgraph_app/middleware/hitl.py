"""Human-in-the-loop middleware factory.

Pauses before each gated tool call individually so the user approves one tool
at a time. Tools not listed in ``settings.hitl_tools`` are auto-approved.

UI integration: on interrupt, the agent returns an ``__interrupt__`` payload with
a single entry in ``action_requests``. Resume with
``Command(resume={"decisions": [<decision>]})``.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from langchain.agents.middleware import HumanInTheLoopMiddleware
from langchain.agents.middleware.human_in_the_loop import HITLRequest
from langchain.agents.middleware.types import AgentState, ContextT, ResponseT
from langchain_core.messages import AIMessage, ToolCall, ToolMessage
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from ..config import settings


DEFAULT_ALLOWED_DECISIONS = ["approve", "edit", "reject"]


class SequentialHumanInTheLoopMiddleware(HumanInTheLoopMiddleware):
    """HITL middleware that interrupts once per gated tool call, in order."""

    def after_model(
        self, state: AgentState[Any], runtime: Runtime[ContextT]
    ) -> dict[str, Any] | None:
        messages = state["messages"]
        if not messages:
            return None

        last_ai_msg = next(
            (msg for msg in reversed(messages) if isinstance(msg, AIMessage)), None
        )
        if not last_ai_msg or not last_ai_msg.tool_calls:
            return None

        revised_tool_calls: list[ToolCall] = []
        artificial_tool_messages: list[ToolMessage] = []

        for tool_call in last_ai_msg.tool_calls:
            config = self.interrupt_on.get(tool_call["name"])
            if config is None:
                revised_tool_calls.append(tool_call)
                continue

            action_request, review_config = self._create_action_and_config(
                tool_call, config, state, runtime
            )
            hitl_request = HITLRequest(
                action_requests=[action_request],
                review_configs=[review_config],
            )
            decisions = interrupt(hitl_request)["decisions"]

            if len(decisions) != 1:
                msg = (
                    f"Expected exactly one human decision for tool "
                    f"'{tool_call['name']}', got {len(decisions)}."
                )
                raise ValueError(msg)

            revised_tool_call, tool_message = self._process_decision(
                decisions[0], tool_call, config
            )
            if revised_tool_call is not None:
                revised_tool_calls.append(revised_tool_call)
            if tool_message:
                artificial_tool_messages.append(tool_message)

        last_ai_msg.tool_calls = revised_tool_calls
        return {"messages": [last_ai_msg, *artificial_tool_messages]}


def build_hitl_middleware(
    tools: Iterable[str] | None = None,
    *,
    allowed_decisions: list[str] | None = None,
    description_prefix: str = "Tool execution requires approval",
) -> SequentialHumanInTheLoopMiddleware:
    """Return sequential HITL middleware configured from settings."""
    tool_names = list(tools) if tools is not None else list(settings.hitl_tools)
    decisions = allowed_decisions or DEFAULT_ALLOWED_DECISIONS

    interrupt_on = {name: {"allowed_decisions": decisions} for name in tool_names}

    return SequentialHumanInTheLoopMiddleware(
        interrupt_on=interrupt_on,
        description_prefix=description_prefix,
    )
