"""FastAPI router — all agent-facing HTTP endpoints."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from langgraph.types import Command

from ..config import settings
from ..hitl import build_hitl_resume_decision
from ..skill_progress import load_phases, read_progress, reconcile_run_progress
from ..thread_store import load_thread_list
from ..ui import title_store
from .helpers import (
    build_chat_response,
    msg_to_out,
    run_config_for_new_turn,
    run_config_for_resume,
    thread_config,
)
from .schemas import (
    ArtifactContentResponse,
    ArtifactInfo,
    ArtifactListResponse,
    ChatRequest,
    ChatResponse,
    ConfigResponse,
    GenerateTitleRequest,
    HealthResponse,
    HistoryResponse,
    MessageOut,
    ResumeRequest,
    SkillProgressResponse,
    ThreadListResponse,
    ThreadTitleResponse,
)
from .streaming import build_chat_payload, build_resume_payload, stream_agent_run


logger = logging.getLogger("langgraph_app.api.router")
router = APIRouter()


def _get_agent(request: Request):
    agent = getattr(request.app.state, "agent", None)
    if agent is None:
        raise HTTPException(status_code=503, detail="Agent not initialised yet.")
    return agent


def _iso(mtime: float) -> str:
    from datetime import datetime, timezone

    return datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()


def _invoke_resume(agent, body: ResumeRequest, config: dict) -> None:
    if body.answer is not None:
        agent.invoke(Command(resume=body.answer), config=config)
        return
    if body.decision in {"approve", "edit", "reject"}:
        decision = build_hitl_resume_decision(
            body.decision,
            tool_name=body.tool_name or "tool",
            edited_args=body.edited_args,
        )
        agent.invoke(Command(resume={"decisions": [decision]}), config=config)
        return
    raise HTTPException(
        status_code=422,
        detail=(
            "Provide either 'answer' (user-input interrupt) or 'decision' "
            "(approve, edit, reject for HITL)."
        ),
    )


@router.get("/health", response_model=HealthResponse, tags=["meta"])
def health() -> HealthResponse:
    return HealthResponse()


@router.get("/config", response_model=ConfigResponse, tags=["meta"])
def get_config() -> ConfigResponse:
    return ConfigResponse(
        model_name=settings.model_name,
        temperature=settings.temperature,
        max_iterations=settings.max_iterations,
        max_input_chars=settings.max_input_chars,
        guardrail_blocklist=settings.guardrail_blocklist,
        hitl_tools=settings.hitl_tools,
        log_level=settings.log_level,
        db_path=settings.db_path,
    )


@router.get("/threads", response_model=ThreadListResponse, tags=["threads"])
def list_threads() -> ThreadListResponse:
    return ThreadListResponse(threads=load_thread_list())


@router.get("/threads/{thread_id}/title", response_model=ThreadTitleResponse, tags=["threads"])
def get_thread_title(thread_id: str) -> ThreadTitleResponse:
    return ThreadTitleResponse(
        thread_id=thread_id,
        title=title_store.get_title(settings.db_path, thread_id),
    )


@router.post("/threads/{thread_id}/title/generate", response_model=ThreadTitleResponse, tags=["threads"])
def generate_thread_title(thread_id: str, body: GenerateTitleRequest) -> ThreadTitleResponse:
    generated = title_store.generate_title(body.user_message, body.assistant_reply, settings)
    title_store.save_title(settings.db_path, thread_id, generated)
    return ThreadTitleResponse(thread_id=thread_id, title=generated)


@router.post("/chat/{thread_id}", response_model=ChatResponse, tags=["chat"])
def chat(thread_id: str, body: ChatRequest, request: Request) -> ChatResponse:
    agent = _get_agent(request)
    config = run_config_for_new_turn(agent, thread_id, body.bearer_token, body.gitlab_token)
    logger.info("chat thread_id=%s message_len=%d", thread_id, len(body.message))
    agent.invoke(build_chat_payload(body.message), config=config)
    return build_chat_response(agent, thread_id, config)


@router.post("/chat/{thread_id}/stream", tags=["chat"])
def chat_stream(thread_id: str, body: ChatRequest, request: Request) -> StreamingResponse:
    agent = _get_agent(request)
    logger.info("chat_stream thread_id=%s message_len=%d", thread_id, len(body.message))
    return StreamingResponse(
        stream_agent_run(
            agent,
            thread_id,
            build_chat_payload(body.message),
            bearer_token=body.bearer_token,
            gitlab_token=body.gitlab_token,
            is_resume=False,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/chat/{thread_id}/resume", response_model=ChatResponse, tags=["chat"])
def resume(thread_id: str, body: ResumeRequest, request: Request) -> ChatResponse:
    agent = _get_agent(request)
    config = run_config_for_resume(agent, thread_id, body.bearer_token, body.gitlab_token)
    logger.info("resume thread_id=%s", thread_id)
    _invoke_resume(agent, body, config)
    return build_chat_response(agent, thread_id, config)


@router.post("/chat/{thread_id}/resume/stream", tags=["chat"])
def resume_stream(thread_id: str, body: ResumeRequest, request: Request) -> StreamingResponse:
    agent = _get_agent(request)
    try:
        payload = build_resume_payload(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(
        stream_agent_run(
            agent,
            thread_id,
            payload,
            bearer_token=body.bearer_token,
            gitlab_token=body.gitlab_token,
            is_resume=True,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/{thread_id}/history", response_model=HistoryResponse, tags=["chat"])
def history(thread_id: str, request: Request) -> HistoryResponse:
    agent = _get_agent(request)
    config = thread_config(thread_id)
    state = agent.get_state(config)
    messages = state.values.get("messages", []) if state and state.values else []
    out_messages = [m for m in (msg_to_out(m) for m in messages) if m is not None]
    return HistoryResponse(thread_id=thread_id, messages=out_messages)


@router.get("/chat/{thread_id}/progress", response_model=SkillProgressResponse, tags=["chat"])
def get_progress(
    thread_id: str,
    run_hash: str = Query(..., description="Run hash for the active turn."),
) -> SkillProgressResponse:
    reconcile_run_progress(thread_id, run_hash)
    progress = read_progress(thread_id, run_hash)
    skill = str(progress.get("skill", "")) if progress else ""
    return SkillProgressResponse(
        thread_id=thread_id,
        run_hash=run_hash,
        progress=progress,
        phases=load_phases(skill) if skill else [],
    )


@router.delete("/chat/{thread_id}", tags=["chat"])
def delete_thread(thread_id: str, request: Request) -> dict[str, str]:
    agent = _get_agent(request)
    config = thread_config(thread_id)
    try:
        checkpointer = agent.checkpointer
        for checkpoint_tuple in list(checkpointer.list(config)):
            ns = checkpoint_tuple.config.get("configurable", {})
            checkpointer.delete_thread(ns.get("thread_id", thread_id))
            break
    except AttributeError:
        logger.warning("checkpointer.delete_thread not available; skipping deletion")
    title_store.delete_title(settings.db_path, thread_id)
    logger.info("delete_thread thread_id=%s", thread_id)
    return {"deleted": thread_id}


def _thread_artifacts_dir(thread_id: str) -> Path:
    runs_rel = settings.artifacts_runs_root.strip("/")
    return (Path(settings.workspace_dir) / runs_rel / thread_id).resolve()


@router.get("/chat/{thread_id}/artifacts", response_model=ArtifactListResponse, tags=["artifacts"])
def list_artifacts(thread_id: str) -> ArtifactListResponse:
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
    base = _thread_artifacts_dir(thread_id)
    target = (base / artifact_path).resolve()
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
