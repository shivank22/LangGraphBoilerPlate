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

import base64
import logging
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from ..config import settings
from ..run_scope import count_human_messages, derive_run_hash
from .schemas import (
    ArtifactContentResponse,
    ArtifactInfo,
    ArtifactListResponse,
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


def _thread_config(thread_id: str, run_hash: str | None = None) -> dict[str, Any]:
    """Build the run config, injecting tool credentials from settings.

    Headless API callers don't have a UI session, so the platform bearer token
    and GitLab PAT fall back to the values configured in the environment.

    ``run_hash`` (when provided) scopes the artifacts written during this run to
    ``<runs_root>/<thread_id>/<run_hash>/`` via ``ScopedArtifactBackend``.
    """
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "bearer_token": settings.api_bearer_token,
        "gitlab_token": settings.gitlab_token,
    }
    if run_hash is not None:
        configurable["run_hash"] = run_hash
    return {"configurable": configurable}


def _run_config_for_new_turn(agent, thread_id: str) -> dict[str, Any]:
    """Run config for a fresh user message: a new turn index -> new run_hash."""
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    turn_index = count_human_messages(messages)
    return _thread_config(thread_id, derive_run_hash(thread_id, turn_index))


def _run_config_for_resume(agent, thread_id: str) -> dict[str, Any]:
    """Run config for a HITL resume: reuse the interrupted turn's run_hash.

    The triggering human message is already in state, so the turn index is the
    current human-message count minus one.
    """
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    turn_index = max(count_human_messages(messages) - 1, 0)
    return _thread_config(thread_id, derive_run_hash(thread_id, turn_index))


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


def _iso(mtime: float) -> str:
    """Format a POSIX mtime as an ISO 8601 (UTC) timestamp."""
    from datetime import datetime, timezone

    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


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
    config = _run_config_for_new_turn(agent, thread_id)

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
    """Resume a graph that was interrupted for human input.

    For ``ask_user`` interrupts, pass ``answer``. For HITL tool approval,
    pass ``decision`` (approve / edit / reject).
    """
    agent = _get_agent(request)
    config = _run_config_for_resume(agent, thread_id)

    if body.answer is not None:
        logger.info("resume thread_id=%s user_input", thread_id)
        result = agent.invoke(Command(resume=body.answer), config=config)
    elif body.decision == "approve":
        resume_payload = [{"type": "approve"}]
        logger.info("resume thread_id=%s decision=%s", thread_id, body.decision)
        result = agent.invoke(Command(resume=resume_payload), config=config)
    elif body.decision == "edit":
        if body.edited_args is None:
            raise HTTPException(
                status_code=422,
                detail="edited_args is required when decision='edit'.",
            )
        resume_payload = [{"type": "edit", "args": {"args": body.edited_args}}]
        logger.info("resume thread_id=%s decision=%s", thread_id, body.decision)
        result = agent.invoke(Command(resume=resume_payload), config=config)
    elif body.decision == "reject":
        resume_payload = [
            {"type": "reject", "args": "User rejected this tool call via API."}
        ]
        logger.info("resume thread_id=%s decision=%s", thread_id, body.decision)
        result = agent.invoke(Command(resume=resume_payload), config=config)
    else:
        raise HTTPException(
            status_code=422,
            detail=(
                "Provide either 'answer' (user-input interrupt) or 'decision' "
                "(approve, edit, reject for HITL)."
            ),
        )

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


# --- artifacts ---------------------------------------------------------------


def _thread_artifacts_dir(thread_id: str) -> Path:
    """Absolute path to a thread's artifact root on disk.

    Mirrors ScopedArtifactBackend's layout:
    ``<workspace_dir><runs_root>/<thread_id>/``.
    """
    runs_rel = settings.artifacts_runs_root.strip("/")
    return (Path(settings.workspace_dir) / runs_rel / thread_id).resolve()


@router.get("/chat/{thread_id}/artifacts", response_model=ArtifactListResponse, tags=["artifacts"])
def list_artifacts(thread_id: str) -> ArtifactListResponse:
    """List all artifact files stored for a thread, across its run folders."""
    base = _thread_artifacts_dir(thread_id)
    artifacts: list[ArtifactInfo] = []
    if base.is_dir():
        for file in sorted(base.rglob("*")):
            if not file.is_file():
                continue
            rel = file.relative_to(base)
            stat = file.stat()
            artifacts.append(
                ArtifactInfo(
                    path=rel.as_posix(),
                    run_hash=rel.parts[0] if rel.parts else "",
                    size=stat.st_size,
                    modified_at=_iso(stat.st_mtime),
                )
            )
    return ArtifactListResponse(thread_id=thread_id, artifacts=artifacts)


@router.get(
    "/chat/{thread_id}/artifacts/{artifact_path:path}",
    response_model=ArtifactContentResponse,
    tags=["artifacts"],
)
def get_artifact(thread_id: str, artifact_path: str) -> ArtifactContentResponse:
    """Return the content of a single artifact under a thread's run folders."""
    base = _thread_artifacts_dir(thread_id)
    target = (base / artifact_path).resolve()

    # Path-traversal guard: target must stay within the thread's artifact root.
    if base != target and base not in target.parents:
        raise HTTPException(status_code=400, detail="Invalid artifact path.")
    if not target.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found.")

    raw = target.read_bytes()
    try:
        content = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        content = base64.standard_b64encode(raw).decode("ascii")
        encoding = "base64"

    return ArtifactContentResponse(
        thread_id=thread_id,
        path=artifact_path,
        content=content,
        encoding=encoding,
    )
