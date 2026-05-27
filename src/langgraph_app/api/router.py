"""FastAPI router — all agent-facing HTTP endpoints.

Endpoints
---------
GET  /health
POST /chat/{thread_id}              invoke agent, get reply
POST /chat/{thread_id}/resume       resume after a HITL interrupt
GET  /chat/{thread_id}/history      full message history from SQLite
DELETE /chat/{thread_id}            wipe a thread's checkpoints

The agent instance is read from `request.app.state.agent`, built once on
startup in the lifespan context inside `__init__.py`.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from .schemas import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    HistoryResponse,
    MessageOut,
    ResumeRequest,
)


logger = logging.getLogger("langgraph_app.api.router")
router = APIRouter()


# --- helpers -----------------------------------------------------------------


def _thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _extract_interrupt(result: Any) -> Any | None:
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    return getattr(first, "value", first)


def _msg_to_out(msg: Any) -> MessageOut | None:
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
        return MessageOut(role="tool", content=content, tool_name=name)
    return None


def _get_agent(request: Request):
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet.")
    return agent


# --- endpoints ---------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    """Liveness probe — no agent call, no auth."""
    return HealthResponse()


@router.post("/chat/{thread_id}", response_model=ChatResponse, tags=["chat"])
def chat(thread_id: str, body: ChatRequest, request: Request) -> ChatResponse:
    """Send a user message and receive the agent's reply.

    If the agent pauses for human approval (`interrupted=True`), call
    `POST /chat/{thread_id}/resume` with your decision.
    """
    agent = _get_agent(request)
    config = _thread_config(thread_id)

    logger.info("chat thread_id=%s message_len=%d", thread_id, len(body.message))

    result = agent.invoke(
        {"messages": [HumanMessage(content=body.message)]},
        config=config,
    )

    interrupt_payload = _extract_interrupt(result)
    interrupted = interrupt_payload is not None

    # Collect only the messages produced in this turn (since last checkpoint).
    state = agent.get_state(config)
    all_messages = state.values.get("messages", []) if state and state.values else []
    out_messages = [m for m in (_msg_to_out(m) for m in all_messages) if m is not None]

    last_ai = next(
        (m for m in reversed(out_messages) if m.role == "assistant" and m.content),
        None,
    )
    reply = last_ai.content if last_ai else ""
    if interrupted:
        reply = reply or "Waiting for your approval before calling the tool."

    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        messages=out_messages,
        interrupted=interrupted,
        interrupt_payload=interrupt_payload,
    )


@router.post("/chat/{thread_id}/resume", response_model=ChatResponse, tags=["chat"])
def resume(thread_id: str, body: ResumeRequest, request: Request) -> ChatResponse:
    """Resume a graph that was interrupted by HumanInTheLoopMiddleware.

    Pass the decision from the interrupt (approve / edit / reject).
    """
    agent = _get_agent(request)
    config = _thread_config(thread_id)

    if body.decision == "approve":
        resume_payload = [{"type": "approve"}]
    elif body.decision == "edit":
        if body.edited_args is None:
            raise HTTPException(
                status_code=422,
                detail="edited_args is required when decision='edit'.",
            )
        resume_payload = [{"type": "edit", "args": {"args": body.edited_args}}]
    elif body.decision == "reject":
        resume_payload = [
            {"type": "reject", "args": "User rejected this tool call via API."}
        ]
    else:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown decision '{body.decision}'. Use approve, edit, or reject.",
        )

    logger.info("resume thread_id=%s decision=%s", thread_id, body.decision)
    result = agent.invoke(Command(resume=resume_payload), config=config)

    interrupt_payload = _extract_interrupt(result)
    interrupted = interrupt_payload is not None

    state = agent.get_state(config)
    all_messages = state.values.get("messages", []) if state and state.values else []
    out_messages = [m for m in (_msg_to_out(m) for m in all_messages) if m is not None]

    last_ai = next(
        (m for m in reversed(out_messages) if m.role == "assistant" and m.content),
        None,
    )
    reply = last_ai.content if last_ai else ""

    return ChatResponse(
        thread_id=thread_id,
        reply=reply,
        messages=out_messages,
        interrupted=interrupted,
        interrupt_payload=interrupt_payload,
    )


@router.get("/chat/{thread_id}/history", response_model=HistoryResponse, tags=["chat"])
def history(thread_id: str, request: Request) -> HistoryResponse:
    """Return the full message history for a thread from SQLite."""
    agent = _get_agent(request)
    config = _thread_config(thread_id)

    state = agent.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    out_messages = [m for m in (_msg_to_out(m) for m in messages) if m is not None]

    return HistoryResponse(thread_id=thread_id, messages=out_messages)


@router.delete("/chat/{thread_id}", tags=["chat"])
def delete_thread(thread_id: str, request: Request) -> dict[str, str]:
    """Delete all checkpoints for a thread (wipes conversation from SQLite).

    This removes the thread's history permanently. Use for testing or resets.
    """
    agent = _get_agent(request)
    config = _thread_config(thread_id)

    # Walk checkpoints and delete them all.
    try:
        checkpointer = agent.checkpointer
        for checkpoint_tuple in list(checkpointer.list(config)):
            ns = checkpoint_tuple.config.get("configurable", {})
            checkpointer.delete_thread(ns.get("thread_id", thread_id))
            break  # delete_thread wipes the whole thread; one call is enough
    except AttributeError:
        # Older checkpointer versions may not expose delete_thread.
        logger.warning("checkpointer.delete_thread not available; skipping deletion")

    logger.info("delete_thread thread_id=%s", thread_id)
    return {"deleted": thread_id}
