"""Shared helpers for API router and streaming endpoints."""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from ..config import settings
from ..run_scope import count_human_messages, derive_run_hash
from ..skill_progress import load_phases, read_progress, reconcile_run_progress
from .schemas import ChatResponse, MessageOut


def thread_config(
    thread_id: str,
    run_hash: str | None = None,
    *,
    bearer_token: str | None = None,
    gitlab_token: str | None = None,
) -> dict[str, Any]:
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "bearer_token": bearer_token if bearer_token is not None else settings.api_bearer_token,
        "gitlab_token": gitlab_token if gitlab_token is not None else settings.gitlab_token,
    }
    if run_hash is not None:
        configurable["run_hash"] = run_hash
    return {"configurable": configurable}


def run_config_for_new_turn(
    agent,
    thread_id: str,
    bearer_token: str | None = None,
    gitlab_token: str | None = None,
) -> dict[str, Any]:
    state = agent.get_state(thread_config(thread_id, bearer_token=bearer_token, gitlab_token=gitlab_token))
    messages = state.values.get("messages", []) if state and state.values else []
    turn_index = count_human_messages(messages)
    return thread_config(
        thread_id,
        derive_run_hash(thread_id, turn_index),
        bearer_token=bearer_token,
        gitlab_token=gitlab_token,
    )


def run_config_for_resume(
    agent,
    thread_id: str,
    bearer_token: str | None = None,
    gitlab_token: str | None = None,
) -> dict[str, Any]:
    state = agent.get_state(thread_config(thread_id, bearer_token=bearer_token, gitlab_token=gitlab_token))
    messages = state.values.get("messages", []) if state and state.values else []
    turn_index = max(count_human_messages(messages) - 1, 0)
    return thread_config(
        thread_id,
        derive_run_hash(thread_id, turn_index),
        bearer_token=bearer_token,
        gitlab_token=gitlab_token,
    )


def extract_interrupt(result: Any) -> Any | None:
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    return getattr(first, "value", first)


def extract_interrupt_from_state(agent, config: dict[str, Any]) -> Any | None:
    state = agent.get_state(config)
    if state and getattr(state, "interrupts", None):
        first = state.interrupts[0]
        return getattr(first, "value", first)
    return None


def msg_to_out(msg: Any) -> MessageOut | None:
    if isinstance(msg, HumanMessage):
        content = msg.content if isinstance(msg.content, str) else str(msg.content)
        return MessageOut(role="user", content=content)
    if isinstance(msg, AIMessage):
        content = msg.content if isinstance(msg.content, str) else ""
        tool_calls = getattr(msg, "tool_calls", None) or None
        return MessageOut(role="assistant", content=content, tool_calls=tool_calls)
    if isinstance(msg, ToolMessage):
        content = str(msg.content) if msg.content is not None else ""
        name = getattr(msg, "name", None)
        call_id = getattr(msg, "tool_call_id", None)
        return MessageOut(
            role="tool",
            content=content,
            tool_name=name,
            tool_call_id=str(call_id) if call_id else None,
        )
    return None


def build_chat_response(agent, thread_id: str, config: dict[str, Any]) -> ChatResponse:
    interrupt_payload = extract_interrupt_from_state(agent, config)
    interrupted = interrupt_payload is not None
    state = agent.get_state(config)
    all_messages = state.values.get("messages", []) if state and state.values else []
    out_messages = [m for m in (msg_to_out(m) for m in all_messages) if m is not None]
    last_ai = next(
        (m for m in reversed(out_messages) if m.role == "assistant" and m.content),
        None,
    )
    reply = last_ai.content if last_ai else ""
    if interrupted and not reply:
        reply = "Waiting for your approval before calling the tool."
    run_hash = config.get("configurable", {}).get("run_hash")
    return ChatResponse(
        thread_id=thread_id,
        run_hash=run_hash,
        reply=reply,
        messages=out_messages,
        interrupted=interrupted,
        interrupt_payload=interrupt_payload,
    )


def progress_payload(thread_id: str, run_hash: str) -> dict[str, Any] | None:
    reconcile_run_progress(thread_id, run_hash)
    progress = read_progress(thread_id, run_hash)
    if not progress:
        return None
    skill = str(progress.get("skill", ""))
    return {
        "progress": progress,
        "phases": load_phases(skill) if skill else [],
    }


def messages_payload(agent, config: dict[str, Any]) -> list[dict[str, Any]]:
    state = agent.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    out = [msg_to_out(m) for m in messages]
    return [m.model_dump() for m in out if m is not None]


def done_payload(agent, thread_id: str, config: dict[str, Any], run_hash: str) -> dict[str, Any]:
    interrupt = extract_interrupt_from_state(agent, config)
    interrupted = interrupt is not None
    messages = messages_payload(agent, config)
    last_ai = next(
        (m for m in reversed(messages) if m.get("role") == "assistant" and m.get("content")),
        None,
    )
    reply = (last_ai or {}).get("content", "")
    if interrupted and not reply:
        reply = "Waiting for your approval before calling the tool."
    progress_data = progress_payload(thread_id, run_hash)
    return {
        "thread_id": thread_id,
        "run_hash": run_hash,
        "reply": reply,
        "messages": messages,
        "interrupted": interrupted,
        "interrupt_payload": interrupt,
        "progress": progress_data.get("progress") if progress_data else None,
        "phases": progress_data.get("phases") if progress_data else [],
    }
