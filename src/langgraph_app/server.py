"""Monolith launcher — starts FastAPI and optional UI subprocesses.

FastAPI (uvicorn) runs as an asyncio coroutine on port 8000.
Streamlit and/or Vite dev server run as managed subprocesses.

Set ``UI`` env var to control which UIs start:
  react      — FastAPI + Vite dev server (:5173)
  streamlit  — FastAPI + Streamlit (:8501)
  both       — FastAPI + Streamlit + Vite (default during transition)
  none       — FastAPI only

Usage:
    uv run python src/langgraph_app/server.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

import uvicorn

from langgraph_app.api import app


logger = logging.getLogger("langgraph_app.server")

FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8000
STREAMLIT_PORT = 8501
VITE_PORT = 5173

_HERE = Path(__file__).resolve().parent
_ROOT = _HERE.parents[1]
STREAMLIT_SCRIPT = str(_HERE / "ui" / "streamlit_app.py")
FRONTEND_DIR = _ROOT / "frontend"


def _ui_mode() -> str:
    return os.environ.get("UI", "both").strip().lower()


async def _run_streamlit() -> asyncio.subprocess.Process:
    cmd = [
        sys.executable, "-m", "streamlit", "run",
        STREAMLIT_SCRIPT,
        "--server.port", str(STREAMLIT_PORT),
        "--server.headless", "true",
        "--server.address", "0.0.0.0",
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    logger.info("Streamlit started  http://localhost:%d  (pid=%d)", STREAMLIT_PORT, proc.pid)
    return proc


async def _run_vite() -> asyncio.subprocess.Process:
    if not (FRONTEND_DIR / "package.json").is_file():
        raise FileNotFoundError(f"frontend/package.json not found at {FRONTEND_DIR}")
    npm = "npm.cmd" if sys.platform == "win32" else "npm"
    proc = await asyncio.create_subprocess_exec(
        npm, "run", "dev", "--", "--host", "0.0.0.0", "--port", str(VITE_PORT),
        cwd=str(FRONTEND_DIR),
    )
    logger.info("Vite dev server started  http://localhost:%d  (pid=%d)", VITE_PORT, proc.pid)
    return proc


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    mode = _ui_mode()
    logger.info("UI mode: %s", mode)

    uvi_config = uvicorn.Config(
        app,
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        log_level="info",
    )
    uvi_server = uvicorn.Server(uvi_config)

    child_procs: list[asyncio.subprocess.Process] = []

    if mode in {"streamlit", "both"}:
        child_procs.append(await _run_streamlit())
    if mode in {"react", "both"}:
        try:
            child_procs.append(await _run_vite())
        except FileNotFoundError as exc:
            logger.warning("%s — run `npm install` in frontend/ first", exc)

    logger.info("FastAPI running — http://localhost:%d", FASTAPI_PORT)
    logger.info("API docs: http://localhost:%d/docs", FASTAPI_PORT)
    if mode in {"streamlit", "both"}:
        logger.info("Streamlit UI: http://localhost:%d", STREAMLIT_PORT)
    if mode in {"react", "both"} and child_procs:
        logger.info("React UI: http://localhost:%d", VITE_PORT)

    loop = asyncio.get_running_loop()

    def _shutdown(sig_name: str) -> None:
        logger.info("Received %s, shutting down...", sig_name)
        uvi_server.should_exit = True
        for proc in child_procs:
            if proc.returncode is None:
                proc.terminate()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig.name)

    try:
        wait_tasks = [uvi_server.serve()]
        for proc in child_procs:
            wait_tasks.append(proc.wait())
        await asyncio.gather(*wait_tasks)
    finally:
        for proc in child_procs:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
