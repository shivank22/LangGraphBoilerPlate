"""Monolith launcher — starts FastAPI and Streamlit in a single process.

FastAPI (uvicorn) runs as an asyncio coroutine on port 8000.
Streamlit runs as a managed subprocess on port 8501 (it owns its own event
loop and cannot safely share ours).

Usage:
    uv run python src/langgraph_app/server.py

Both servers stay alive until you press Ctrl-C.  A SIGINT/SIGTERM to this
process is forwarded to the Streamlit subprocess before this process exits.
"""

from __future__ import annotations

import asyncio
import logging
import signal
import sys
from pathlib import Path

import uvicorn

from langgraph_app.api import app


logger = logging.getLogger("langgraph_app.server")

FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8000
STREAMLIT_PORT = 8501

# Path to the Streamlit entry-point, resolved relative to this file so the
# launcher works regardless of the current working directory.
_HERE = Path(__file__).resolve().parent
STREAMLIT_SCRIPT = str(_HERE / "ui" / "streamlit_app.py")


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


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )

    uvi_config = uvicorn.Config(
        app,
        host=FASTAPI_HOST,
        port=FASTAPI_PORT,
        log_level="info",
    )
    uvi_server = uvicorn.Server(uvi_config)

    st_proc = await _run_streamlit()

    logger.info(
        "Monolith running — FastAPI: http://localhost:%d  |  Streamlit: http://localhost:%d",
        FASTAPI_PORT,
        STREAMLIT_PORT,
    )
    logger.info("API docs: http://localhost:%d/docs", FASTAPI_PORT)

    loop = asyncio.get_running_loop()

    def _shutdown(sig_name: str) -> None:
        logger.info("Received %s, shutting down...", sig_name)
        uvi_server.should_exit = True
        if st_proc.returncode is None:
            st_proc.terminate()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, _shutdown, sig.name)

    try:
        await asyncio.gather(
            uvi_server.serve(),
            st_proc.wait(),
        )
    finally:
        if st_proc.returncode is None:
            st_proc.terminate()
            try:
                await asyncio.wait_for(st_proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                st_proc.kill()


if __name__ == "__main__":
    asyncio.run(main())
