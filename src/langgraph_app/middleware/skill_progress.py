"""Middleware that tracks skill execution progress from tool calls."""

from __future__ import annotations

import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ToolCallRequest
from langchain_core.messages import ToolMessage
from langgraph.errors import GraphInterrupt
from langgraph.types import Command

from ..skill_progress import apply_tool_call, read_progress


logger = logging.getLogger("langgraph_app.middleware.skill_progress")


class SkillProgressMiddleware(AgentMiddleware):
    """Update per-run skill-progress.json after each tool call."""

    name = "SkillProgressMiddleware"

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Any,
    ) -> ToolMessage | Command[Any]:
        tool_call = request.tool_call or {}
        tool_name = str(tool_call.get("name", ""))
        args = tool_call.get("args") or {}
        if not isinstance(args, dict):
            args = {}

        thread_id, run_hash = _run_scope(request)
        progress = read_progress(thread_id, run_hash) if thread_id and run_hash else None

        try:
            result = handler(request)
        except GraphInterrupt:
            if thread_id and run_hash:
                apply_tool_call(
                    progress,
                    thread_id=thread_id,
                    run_hash=run_hash,
                    tool_name=tool_name,
                    args=args,
                    interrupted=True,
                )
            raise

        if thread_id and run_hash:
            try:
                apply_tool_call(
                    progress,
                    thread_id=thread_id,
                    run_hash=run_hash,
                    tool_name=tool_name,
                    args=args,
                    result=result,
                )
            except Exception:
                logger.exception(
                    "skill_progress: failed to update progress for tool=%s",
                    tool_name,
                )

        return result


def _run_scope(request: ToolCallRequest) -> tuple[str | None, str | None]:
    runtime = request.runtime
    if runtime is None:
        return None, None
    config = getattr(runtime, "config", None) or {}
    configurable = config.get("configurable", {}) if isinstance(config, dict) else {}
    thread_id = configurable.get("thread_id")
    run_hash = configurable.get("run_hash")
    return (
        str(thread_id) if thread_id else None,
        str(run_hash) if run_hash else None,
    )
