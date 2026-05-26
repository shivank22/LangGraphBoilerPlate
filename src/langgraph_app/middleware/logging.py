"""Logging middleware.

Emits one log line before each model call and one after, including model
latency and (when the provider returns it) token usage. Uses the standard
library `logging` module so the consumer can route output anywhere
(stdout, files, structured aggregators, etc.).
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import AIMessage, HumanMessage


logger = logging.getLogger("langgraph_app.middleware.logging")


def _preview(text: str, limit: int = 120) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


class LoggingMiddleware(AgentMiddleware):
    """Trace before/after the model call."""

    name = "LoggingMiddleware"

    def __init__(self, logger_name: str | None = None) -> None:
        super().__init__()
        self._logger = logging.getLogger(logger_name) if logger_name else logger
        self._call_started_at: float | None = None

    def before_model(self, state, runtime) -> dict[str, Any] | None:  # type: ignore[override]
        messages = state.get("messages", []) if isinstance(state, dict) else []
        last_human = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)),
            None,
        )
        preview = _preview(getattr(last_human, "content", "") or "") if last_human else "<none>"

        self._logger.info(
            "model_call:start messages=%d last_user=%r",
            len(messages),
            preview,
        )
        self._call_started_at = time.perf_counter()
        return None

    def after_model(self, state, runtime) -> dict[str, Any] | None:  # type: ignore[override]
        elapsed_ms = (
            (time.perf_counter() - self._call_started_at) * 1000
            if self._call_started_at is not None
            else None
        )
        self._call_started_at = None

        messages = state.get("messages", []) if isinstance(state, dict) else []
        last_ai = next(
            (m for m in reversed(messages) if isinstance(m, AIMessage)),
            None,
        )

        usage = getattr(last_ai, "usage_metadata", None) if last_ai else None
        tool_calls = getattr(last_ai, "tool_calls", None) if last_ai else None

        self._logger.info(
            "model_call:end elapsed_ms=%s tokens=%s tool_calls=%d preview=%r",
            f"{elapsed_ms:.0f}" if elapsed_ms is not None else "?",
            usage,
            len(tool_calls or []),
            _preview(getattr(last_ai, "content", "") or "") if last_ai else "<none>",
        )
        return None
