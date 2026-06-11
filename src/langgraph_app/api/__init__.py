"""FastAPI application factory.

The `app` object is the single FastAPI instance for the whole service.
It is importable as `langgraph_app.api:app` for uvicorn.

Lifecycle:
  - On startup, `build_agent()` is called once and stored on `app.state.agent`.
    All router endpoints read from `request.app.state.agent`.
  - On shutdown, nothing special is needed (SQLite connection stays open until
    process exit, which is fine for a single-process monolith).
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from langgraph_app.agent import build_agent

from .mock_discovery import router as mock_discovery_router
from .router import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.agent = build_agent()
    yield


app = FastAPI(
    title="LangGraph Agent API",
    description=(
        "HTTP interface for the LangGraph + OpenAI agent. "
        "All conversation state is persisted in SQLite keyed by thread_id."
    ),
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(mock_discovery_router)
