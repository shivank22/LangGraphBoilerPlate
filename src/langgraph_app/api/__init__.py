"""FastAPI application factory."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from langgraph_app.agent import build_agent
from langgraph_app.config import PROJECT_ROOT

from .mock_discovery import router as mock_discovery_router
from .router import router


FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


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

if FRONTEND_DIST.is_dir():
    assets_dir = FRONTEND_DIST / "assets"
    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", include_in_schema=False)
    async def spa_index():
        return FileResponse(FRONTEND_DIST / "index.html")

    @app.get("/info", include_in_schema=False)
    async def spa_info():
        return FileResponse(FRONTEND_DIST / "index.html")
