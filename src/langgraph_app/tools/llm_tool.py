"""Custom LLM call tool.

Makes a standalone one-shot chat completion (system + user messages) using
the app's configured OpenAI credentials. Intended for skills that define a
dedicated system prompt and delegate specialized generation/analysis to a
separate LLM call.
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool

from ..config import settings


@tool
def call_custom_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Run a one-shot LLM completion with a custom system prompt and user prompt.

    Use this tool when a skill instructs you to delegate a specialized analysis
    or generation task to a dedicated LLM call. Pass the skill's system prompt
    verbatim as ``system_prompt``.

    Args:
        system_prompt: The system message that sets the LLM's role and behavior.
            When a skill provides this, copy it exactly without paraphrasing.
        user_prompt: The user message containing the task, context, and any
            data the LLM should process.
        temperature: Optional sampling temperature. Defaults to the app's
            configured temperature when omitted.

    Returns:
        A dict with ``content`` (assistant text) and ``model`` (model name used),
        or an ``error`` key describing what went wrong.
    """
    from langchain_openai import ChatOpenAI  # local import — keep module-level lean

    if not settings.openai_api_key:
        return {"error": "OpenAI API key not configured. Set OPENAI_API_KEY in .env."}

    if not system_prompt.strip():
        return {"error": "system_prompt must not be empty."}

    if not user_prompt.strip():
        return {"error": "user_prompt must not be empty."}

    temp = settings.temperature if temperature is None else temperature

    try:
        llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=temp,
        )
        response = llm.invoke(
            [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt),
            ]
        )
        content = response.content
        if not isinstance(content, str):
            content = str(content)

        return {
            "content": content,
            "model": settings.model_name,
        }
    except Exception as exc:
        return {"error": f"LLM call failed: {exc!s}"}
