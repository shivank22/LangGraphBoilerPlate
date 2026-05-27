"""Pydantic request / response models for the FastAPI layer.

Keep these thin — they are a transport contract, not business logic.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., description="The user's message text.")


class MessageOut(BaseModel):
    role: str = Field(..., description="One of: 'user', 'assistant', 'tool'.")
    content: str = Field(default="", description="Plain-text or markdown content of the message.")
    tool_calls: list[dict[str, Any]] | None = Field(
        default=None,
        description="Tool calls requested by the assistant (if any).",
    )
    tool_name: str | None = Field(
        default=None,
        description="For role='tool': the name of the tool that produced this result.",
    )


class ChatResponse(BaseModel):
    thread_id: str
    reply: str = Field(description="The last assistant text reply.")
    messages: list[MessageOut] = Field(
        description="All new messages produced this turn (user + assistant + tool)."
    )
    interrupted: bool = Field(
        default=False,
        description="True when HITL middleware paused the graph before a tool call.",
    )
    interrupt_payload: Any | None = Field(
        default=None,
        description="The raw interrupt value when interrupted=True; pass back via POST /chat/{thread_id}/resume.",
    )


class ResumeRequest(BaseModel):
    decision: str = Field(..., description="One of: 'approve', 'edit', 'reject'.")
    edited_args: dict[str, Any] | None = Field(
        default=None,
        description="Edited tool arguments (only required when decision='edit').",
    )


class HistoryResponse(BaseModel):
    thread_id: str
    messages: list[MessageOut]


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
