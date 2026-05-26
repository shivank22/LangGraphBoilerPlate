"""Streamlit chat UI for the LangGraph agent.

Run with:

    uv run streamlit run src/langgraph_app/ui/streamlit_app.py

The agent is built once per process (cached via `st.cache_resource`) and
state is persisted in SQLite via the configured checkpointer, keyed by
`thread_id`. A new conversation simply generates a fresh `thread_id`.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from langgraph_app.agent import build_agent
from langgraph_app.config import settings


st.set_page_config(page_title="LangGraph Agent", page_icon=None, layout="centered")


@st.cache_resource(show_spinner="Building agent...")
def _get_agent():
    return build_agent()


def _thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def _ensure_session() -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    if "pending_interrupt" not in st.session_state:
        st.session_state.pending_interrupt = None


def _render_message(message) -> None:
    if isinstance(message, HumanMessage):
        with st.chat_message("user"):
            st.markdown(message.content)
    elif isinstance(message, AIMessage):
        content = message.content or ""
        tool_calls = getattr(message, "tool_calls", None) or []
        if not content and not tool_calls:
            return
        with st.chat_message("assistant"):
            if content:
                st.markdown(content)
            for call in tool_calls:
                with st.expander(f"Tool call: {call.get('name')}", expanded=False):
                    st.code(json.dumps(call.get("args", {}), indent=2), language="json")
    elif isinstance(message, ToolMessage):
        with st.chat_message("assistant"):
            with st.expander(f"Tool result: {message.name}", expanded=False):
                content = message.content
                if isinstance(content, (dict, list)):
                    st.code(json.dumps(content, indent=2), language="json")
                else:
                    try:
                        parsed = json.loads(content)
                        st.code(json.dumps(parsed, indent=2), language="json")
                    except (ValueError, TypeError):
                        st.markdown(str(content))


def _render_history(agent, thread_id: str) -> None:
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    for message in messages:
        _render_message(message)


def _extract_interrupt(result: dict | None) -> Any | None:
    """Return the first interrupt payload if the result contains one."""
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    return getattr(first, "value", first)


def _run_agent(agent, payload: Any, thread_id: str) -> None:
    """Invoke the agent and stash any interrupt payload for HITL rendering."""
    with st.spinner("Thinking..."):
        result = agent.invoke(payload, config=_thread_config(thread_id))
    st.session_state.pending_interrupt = _extract_interrupt(result)


def _render_hitl(agent, interrupt_payload: Any, thread_id: str) -> None:
    """Render the HITL approval UI for the active interrupt."""
    requests = interrupt_payload if isinstance(interrupt_payload, list) else [interrupt_payload]

    st.warning("Human approval required before the agent can run the next tool call.")

    decisions: list[dict[str, Any]] = []
    for idx, request in enumerate(requests):
        request_dict = request if isinstance(request, dict) else {}
        action_request = request_dict.get("action_request", {})
        tool_name = action_request.get("action") or request_dict.get("name") or "tool"
        tool_args = action_request.get("args") or request_dict.get("args") or {}
        description = request_dict.get("description") or ""

        with st.container(border=True):
            st.markdown(f"**Tool:** `{tool_name}`")
            if description:
                st.caption(description)
            edited_args_json = st.text_area(
                "Arguments (edit before approving if needed):",
                value=json.dumps(tool_args, indent=2),
                key=f"hitl_args_{idx}",
                height=140,
            )

            choice = st.radio(
                "Decision",
                options=["approve", "edit", "reject"],
                horizontal=True,
                key=f"hitl_choice_{idx}",
            )
            decisions.append({"choice": choice, "edited_args_json": edited_args_json})

    if st.button("Submit decision(s)", type="primary"):
        resume_payload = []
        for decision in decisions:
            if decision["choice"] == "approve":
                resume_payload.append({"type": "approve"})
            elif decision["choice"] == "edit":
                try:
                    args = json.loads(decision["edited_args_json"])
                except json.JSONDecodeError as exc:
                    st.error(f"Edited arguments are not valid JSON: {exc}")
                    return
                resume_payload.append({"type": "edit", "args": {"args": args}})
            else:
                resume_payload.append(
                    {
                        "type": "reject",
                        "args": "User rejected this tool call. Continue without it.",
                    }
                )

        _run_agent(agent, Command(resume=resume_payload), thread_id)
        st.rerun()


def _sidebar(agent) -> None:
    with st.sidebar:
        st.subheader("Session")
        st.code(st.session_state.thread_id, language="text")
        if st.button("New conversation"):
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.pending_interrupt = None
            st.rerun()

        st.divider()
        st.subheader("Model")
        st.write(f"`{settings.model_name}`")
        st.caption(f"temperature={settings.temperature}")

        st.divider()
        st.subheader("Middleware")
        st.markdown(
            "- GuardrailMiddleware\n"
            f"  - max_iterations: `{settings.max_iterations}`\n"
            f"  - max_input_chars: `{settings.max_input_chars}`\n"
            f"  - blocklist: `{settings.guardrail_blocklist or '[]'}`\n"
            "- LoggingMiddleware\n"
            "- HumanInTheLoopMiddleware\n"
            f"  - tools: `{settings.hitl_tools or '[]'}`"
        )


def main() -> None:
    _ensure_session()

    st.title("LangGraph Chat Agent")
    st.caption(
        "Modular LangGraph + OpenAI agent with SQLite persistence, "
        "logging, human-in-the-loop, and guardrail middleware."
    )

    agent = _get_agent()
    _sidebar(agent)

    _render_history(agent, st.session_state.thread_id)

    if st.session_state.pending_interrupt is not None:
        _render_hitl(agent, st.session_state.pending_interrupt, st.session_state.thread_id)
        return

    prompt = st.chat_input("Message the agent...")
    if not prompt:
        return

    with st.chat_message("user"):
        st.markdown(prompt)

    _run_agent(
        agent,
        {"messages": [HumanMessage(content=prompt)]},
        st.session_state.thread_id,
    )
    st.rerun()


main()
