"""Server-Sent Events helpers for streaming agent runs."""

from __future__ import annotations

import json
from typing import Any, Iterator

from langchain_core.messages import HumanMessage
from langgraph.types import Command

from ..hitl import ui_mode_from_interrupt, ui_mode_from_state
from .helpers import (
    done_payload,
    extract_interrupt_from_state,
    messages_payload,
    progress_payload,
    run_config_for_new_turn,
    run_config_for_resume,
)


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def _checkpoint_message_count(agent, config: dict[str, Any]) -> int:
    state = agent.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    return len(messages)


def _interrupt_signature(interrupt: Any) -> str:
    if interrupt is None:
        return ""
    return json.dumps(interrupt, sort_keys=True, default=str)


def _is_stale_resume_interrupt(
    *,
    is_resume: bool,
    messages_before: int,
    messages_now: int,
    interrupt_before: str,
    interrupt_now: str,
) -> bool:
    """True when the interrupt predates the resume and the stream should keep going."""
    return (
        is_resume
        and interrupt_now
        and messages_now <= messages_before
        and interrupt_now == interrupt_before
    )


def stream_agent_run(
    agent,
    thread_id: str,
    payload: Any,
    *,
    bearer_token: str | None = None,
    gitlab_token: str | None = None,
    is_resume: bool = False,
) -> Iterator[str]:
    """Yield SSE events for an agent stream run."""
    if is_resume:
        config = run_config_for_resume(agent, thread_id, bearer_token, gitlab_token)
    else:
        config = run_config_for_new_turn(agent, thread_id, bearer_token, gitlab_token)

    run_hash = config["configurable"].get("run_hash", "")
    yield _sse_event("start", {"thread_id": thread_id, "run_hash": run_hash})

    messages_before = _checkpoint_message_count(agent, config)
    interrupt_before = _interrupt_signature(extract_interrupt_from_state(agent, config))
    interrupted = False

    for _chunk in agent.stream(payload, config=config, stream_mode="values"):
        progress_data = progress_payload(thread_id, run_hash)
        if progress_data:
            yield _sse_event("progress", progress_data)
        yield _sse_event("messages", {"messages": messages_payload(agent, config)})

        messages_now = _checkpoint_message_count(agent, config)
        interrupt = extract_interrupt_from_state(agent, config)
        interrupt_now = _interrupt_signature(interrupt)
        if interrupt is not None and not _is_stale_resume_interrupt(
            is_resume=is_resume,
            messages_before=messages_before,
            messages_now=messages_now,
            interrupt_before=interrupt_before,
            interrupt_now=interrupt_now,
        ):
            interrupted = True
            yield _sse_event(
                "interrupt",
                {
                    "interrupt_payload": interrupt,
                    "ui_mode": ui_mode_from_interrupt(interrupt),
                },
            )
            break

        messages_before = messages_now
        interrupt_before = interrupt_now

    if not interrupted:
        interrupt = extract_interrupt_from_state(agent, config)
        if interrupt is not None:
            yield _sse_event(
                "interrupt",
                {
                    "interrupt_payload": interrupt,
                    "ui_mode": ui_mode_from_interrupt(interrupt),
                },
            )

    yield _sse_event(
        "done",
        {
            **done_payload(agent, thread_id, config, run_hash),
        },
    )


def build_chat_payload(message: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(content=message)]}


def build_resume_payload(body: Any) -> Command:
    """Convert a ResumeRequest into a LangGraph Command."""
    if body.answer is not None:
        return Command(resume=body.answer)
    if body.decision == "approve":
        return Command(resume={"decisions": [{"type": "approve"}]})
    if body.decision == "edit":
        tool_name = body.tool_name or "tool"
        return Command(
            resume={
                "decisions": [
                    {
                        "type": "edit",
                        "edited_action": {
                            "name": tool_name,
                            "args": body.edited_args or {},
                        },
                    }
                ]
            }
        )
    if body.decision == "reject":
        return Command(
            resume={
                "decisions": [
                    {"type": "reject", "message": "User rejected this tool call."}
                ]
            }
        )
    raise ValueError("Invalid resume request")
