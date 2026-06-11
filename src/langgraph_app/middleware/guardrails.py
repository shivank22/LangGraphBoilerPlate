"""Guardrail middleware.

Two layers of cheap, deterministic control that run independently of the
LLM provider:

- `before_agent`: validates fresh user input (length + blocklist). On
  violation, append a refusal `AIMessage` and short-circuit with
  `jump_to="end"`.
- `before_model`: caps the number of model calls **in the current user turn**
  (since the latest human message) to prevent runaway loops. On the cap,
  append an explanatory `AIMessage` and short-circuit with `jump_to="end"`.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage


logger = logging.getLogger("langgraph_app.middleware.guardrails")


def _ai_messages_in_current_turn(messages: list[Any]) -> int:
    """Count assistant messages since the latest human message in this turn."""
    last_human_idx = -1
    for idx in range(len(messages) - 1, -1, -1):
        if isinstance(messages[idx], HumanMessage):
            last_human_idx = idx
            break
    turn_messages = messages[last_human_idx + 1 :]
    return sum(1 for message in turn_messages if isinstance(message, AIMessage))


class GuardrailMiddleware(AgentMiddleware):
    """Basic, deterministic guardrails: input validation + iteration cap."""

    name = "GuardrailMiddleware"

    def __init__(
        self,
        *,
        max_iterations: int = 25,
        max_input_chars: int = 8000,
        blocklist: list[str] | None = None,
    ) -> None:
        super().__init__()
        self.max_iterations = max_iterations
        self.max_input_chars = max_input_chars
        self.blocklist = [term.lower() for term in (blocklist or []) if term]

    def before_agent(self, state, runtime) -> dict[str, Any] | None:  # type: ignore[override]
        messages = state.get("messages", []) if isinstance(state, dict) else []
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        if last_human is None:
            return None

        content = last_human.content if isinstance(last_human.content, str) else str(last_human.content)

        if len(content) > self.max_input_chars:
            logger.warning(
                "guardrail:input_too_long len=%d limit=%d",
                len(content),
                self.max_input_chars,
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"Your message is too long ({len(content)} chars). "
                            f"Please keep it under {self.max_input_chars} characters."
                        )
                    )
                ],
                "jump_to": "end",
            }

        lowered = content.lower()
        hit = next((term for term in self.blocklist if term in lowered), None)
        if hit is not None:
            logger.warning("guardrail:blocked term=%r", hit)
            return {
                "messages": [
                    AIMessage(
                        content="I can't help with that request. Please try a different question."
                    )
                ],
                "jump_to": "end",
            }

        return None

    def before_model(self, state, runtime) -> dict[str, Any] | None:  # type: ignore[override]
        messages = state.get("messages", []) if isinstance(state, dict) else []
        ai_calls = _ai_messages_in_current_turn(messages)

        if ai_calls >= self.max_iterations:
            logger.warning(
                "guardrail:iteration_cap reached=%d cap=%d",
                ai_calls,
                self.max_iterations,
            )
            return {
                "messages": [
                    AIMessage(
                        content=(
                            "I've reached the maximum number of reasoning steps for this turn. "
                            "Please refine your question or ask a follow-up."
                        )
                    )
                ],
                "jump_to": "end",
            }
        return None
