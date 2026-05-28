"""Info page — model, middleware, and runtime configuration details."""

from __future__ import annotations

import streamlit as st

from langgraph_app.config import settings


def render() -> None:
    st.title("Info")
    st.caption("Runtime configuration and middleware details for this agent.")

    st.divider()

    # --- Model ----------------------------------------------------------------
    st.subheader("Model")
    col1, col2 = st.columns(2)
    col1.metric("Model", settings.model_name)
    col2.metric("Temperature", settings.temperature)

    st.divider()

    # --- Middleware -----------------------------------------------------------
    st.subheader("Middleware")
    st.caption("Applied in this order (outer wraps inner).")

    with st.container(border=True):
        st.markdown("#### 1. GuardrailMiddleware")
        st.markdown(
            f"- **Max model calls per run:** `{settings.max_iterations}`\n"
            f"- **Max input characters:** `{settings.max_input_chars}`\n"
            f"- **Blocklist:** `{settings.guardrail_blocklist or '(none)'}`"
        )

    with st.container(border=True):
        st.markdown("#### 2. LoggingMiddleware")
        st.markdown(
            "- Logs before/after every model call.\n"
            "- Captures message count, latency, token usage, and response preview.\n"
            f"- **Log level:** `{settings.log_level}`"
        )

    with st.container(border=True):
        st.markdown("#### 3. HumanInTheLoopMiddleware")
        st.markdown(
            "- Pauses the graph **before** executing any listed tool.\n"
            "- UI surfaces Approve / Edit / Reject buttons.\n"
            f"- **Gated tools:** `{settings.hitl_tools or '(none)'}`"
        )

    st.divider()

    # --- Persistence ----------------------------------------------------------
    st.subheader("Persistence")
    st.markdown(
        f"- **Checkpointer:** `SqliteSaver`\n"
        f"- **Database path:** `{settings.db_path}`\n"
        "- Every node execution writes a checkpoint keyed by `thread_id`.\n"
        "- Conversations survive process restarts."
    )

    st.divider()

    # --- Tools ----------------------------------------------------------------
    st.subheader("Tools")
    with st.container(border=True):
        st.markdown("#### `get_weather`")
        st.markdown(
            "- Calls **Open-Meteo** (no API key required).\n"
            "- Args: `latitude: float`, `longitude: float`\n"
            "- Returns: `temperature_c`, `windspeed_kmh`, `weathercode`, `time`\n"
            "- Swap with your own API in `src/langgraph_app/tools/api_tool.py`."
        )

    st.divider()

    # --- API ------------------------------------------------------------------
    st.subheader("FastAPI REST endpoints")
    st.markdown(
        "| Method | Path | Description |\n"
        "|---|---|---|\n"
        "| GET | `/health` | Liveness probe |\n"
        "| POST | `/chat/{thread_id}` | Send a message |\n"
        "| POST | `/chat/{thread_id}/resume` | Resume after HITL |\n"
        "| GET | `/chat/{thread_id}/history` | Load full history |\n"
        "| DELETE | `/chat/{thread_id}` | Delete a thread |\n"
    )
    st.caption("Interactive docs: http://localhost:8000/docs")
