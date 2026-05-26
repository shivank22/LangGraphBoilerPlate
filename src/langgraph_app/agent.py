"""Single assembly point for the LangGraph agent.

`build_agent()` is the only place where the model, tools, middleware, and
checkpointer are wired together. Importing from this module is the
recommended entry point for the rest of the application (UI, scripts,
tests).
"""

from __future__ import annotations

import logging

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .checkpointer import get_sqlite_checkpointer
from .config import settings
from .middleware import GuardrailMiddleware, LoggingMiddleware, build_hitl_middleware
from .tools import ALL_TOOLS


def _configure_logging() -> None:
    """Configure root logging once, idempotently."""
    root = logging.getLogger()
    if getattr(_configure_logging, "_configured", False):
        return
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    root.setLevel(settings.log_level.upper())
    _configure_logging._configured = True  # type: ignore[attr-defined]


def _build_model() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.temperature,
    )


def build_agent():
    """Build and return the compiled LangGraph agent.

    Middleware order (outer wraps inner):
      1. GuardrailMiddleware  - cheap deterministic input/iteration checks
      2. LoggingMiddleware    - traces model calls
      3. HumanInTheLoop       - pauses on sensitive tool calls
    """
    _configure_logging()

    model = _build_model()
    checkpointer = get_sqlite_checkpointer(settings.db_path)

    return create_agent(
        model=model,
        tools=ALL_TOOLS,
        system_prompt=settings.system_prompt,
        middleware=[
            GuardrailMiddleware(
                max_iterations=settings.max_iterations,
                max_input_chars=settings.max_input_chars,
                blocklist=settings.guardrail_blocklist,
            ),
            LoggingMiddleware(),
            build_hitl_middleware(),
        ],
        checkpointer=checkpointer,
    )
