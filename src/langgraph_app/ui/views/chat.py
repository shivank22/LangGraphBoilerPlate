"""Chat page — conversation list in sidebar, chat UI in main area."""

from __future__ import annotations

import ast
import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any

import streamlit as st
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.types import Command

from langgraph_app.agent import build_agent
from langgraph_app.config import settings
from langgraph_app.ui import title_store


USER_AVATAR = "\U0001F9D1\u200D\U0001F4BB"  # 🧑‍💻
BOT_AVATAR = "\U0001F47E"  # 👾

_MSG_STYLE = (
    "font-size: 1.05rem;"
    "line-height: 1.6;"
    "padding: 14px 18px;"
    "margin: 12px 0;"
    "max-width: 80%;"
    "border-radius: 16px;"
    "display: inline-block;"
    "word-wrap: break-word;"
    "overflow-wrap: anywhere;"
)
_USER_BUBBLE = _MSG_STYLE + "background: rgba(56, 132, 255, 0.15);"
_BOT_BUBBLE  = _MSG_STYLE + "background: rgba(127, 127, 127, 0.12);"


# --- agent cache -------------------------------------------------------------


@st.cache_resource(show_spinner="Building agent...")
def _get_agent():
    return build_agent()


# --- SQLite conversation list ------------------------------------------------


def _load_thread_list() -> list[dict]:
    """Return threads ordered by most-recently updated.

    Labels come from `conversation_titles` (LLM-generated). Threads that
    don't yet have a title fall back to the short hash.
    """
    db_path = Path(settings.db_path)
    if not db_path.exists():
        return []
    try:
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        rows = conn.execute(
            """
            SELECT thread_id, MAX(checkpoint_id) AS latest
            FROM checkpoints
            GROUP BY thread_id
            ORDER BY latest DESC
            """
        ).fetchall()
        conn.close()
    except Exception:
        return []

    all_titles = title_store.get_all_titles(db_path)

    threads = []
    for thread_id, _ in rows:
        short = thread_id[:8] if len(thread_id) >= 8 else thread_id
        label = all_titles.get(thread_id) or f"Chat {short}…"
        threads.append({"thread_id": thread_id, "label": label, "short_id": short})
    return threads


# --- session -----------------------------------------------------------------


def _ensure_session() -> None:
    if "thread_id" not in st.session_state:
        st.session_state.thread_id = str(uuid.uuid4())
    if "pending_interrupt" not in st.session_state:
        st.session_state.pending_interrupt = None


def _switch_thread(thread_id: str) -> None:
    st.session_state.thread_id = thread_id
    st.session_state.pending_interrupt = None


# --- helpers -----------------------------------------------------------------


def _thread_config(thread_id: str) -> dict[str, Any]:
    return {"configurable": {"thread_id": thread_id}}


def parse_json_recursively(content: Any) -> Any:
    if isinstance(content, dict):
        return {k: parse_json_recursively(v) for k, v in content.items()}
    if isinstance(content, list):
        return [parse_json_recursively(i) for i in content]
    if isinstance(content, str):
        try:
            return parse_json_recursively(ast.literal_eval(content))
        except (ValueError, SyntaxError):
            return content
    return content


# --- rendering ---------------------------------------------------------------


def _render_user_text(content: Any) -> None:
    st.markdown(
        f'<div style="text-align: right; margin: 10px 0;">'
        f'<span style="{_USER_BUBBLE}">{content} {USER_AVATAR}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_bot_text(content: Any) -> None:
    st.markdown(
        f'<div style="text-align: left; margin: 10px 0;">'
        f'<span style="{_BOT_BUBBLE}">{BOT_AVATAR} {content}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_structured_bot(content_data: Any) -> None:
    if isinstance(content_data, dict):
        if "uuid" in content_data:
            st.subheader(f"Directory: {content_data['uuid']}")
        if "code" in content_data:
            st.write("### Code File:")
            try:
                with open(content_data["code"], "r") as f:
                    st.code(f.read(), language="python")
            except Exception as e:
                st.error(f"Could not load code file: {e}")
        if "image_urls" in content_data and isinstance(content_data["image_urls"], list):
            st.write("### Images:")
            for url in content_data["image_urls"]:
                try:
                    st.write(f"**{url.split('/')[-1]}**")
                    st.image(url)
                except Exception as e:
                    st.error(f"Could not load image: {e}")
        if "result" in content_data and isinstance(content_data["result"], dict):
            if content_data["result"].get("exit_code") == 0:
                st.success("Execution succeeded")
            else:
                st.error(f"Execution failed (exit code {content_data['result'].get('exit_code')})")
        st.json(content_data)
    elif isinstance(content_data, list):
        st.write("### List Content:")
        for idx, item in enumerate(content_data):
            st.write(f"{idx + 1}. {item}")
    else:
        _render_bot_text(content_data)


def _render_message(message: Any) -> None:
    if isinstance(message, HumanMessage):
        content_str = message.content if isinstance(message.content, str) else str(message.content)
        _render_user_text(parse_json_recursively(content_str.strip()) if content_str else "")
    elif isinstance(message, AIMessage):
        text = message.content if isinstance(message.content, str) else ""
        if text:
            data = parse_json_recursively(text.strip())
            if isinstance(data, (dict, list)):
                _render_structured_bot(data)
            else:
                _render_bot_text(data)
        for call in getattr(message, "tool_calls", None) or []:
            with st.chat_message("assistant", avatar=BOT_AVATAR):
                st.markdown(f"**Tool call:** `{call.get('name', 'tool')}`")
                st.code(json.dumps(call.get("args", {}), indent=2), language="json")
    elif isinstance(message, ToolMessage):
        content_str = str(message.content).strip() if message.content is not None else ""
        data = parse_json_recursively(content_str) if content_str else None
        with st.chat_message("assistant", avatar=BOT_AVATAR):
            st.markdown(f"**Tool result:** `{getattr(message, 'name', None) or 'tool'}`")
            if isinstance(data, (dict, list)):
                st.json(data)
            else:
                st.write(data)


def _render_history(agent, thread_id: str) -> None:
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    for msg in messages:
        _render_message(msg)


# --- agent invocation --------------------------------------------------------


def _extract_interrupt(result: Any) -> Any | None:
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    return getattr(first, "value", first)


def _run_agent(agent, payload: Any, thread_id: str) -> None:
    with st.spinner("Thinking..."):
        result = agent.invoke(payload, config=_thread_config(thread_id))
    st.session_state.pending_interrupt = _extract_interrupt(result)


def _render_hitl(agent, interrupt_payload: Any, thread_id: str) -> None:
    requests = interrupt_payload if isinstance(interrupt_payload, list) else [interrupt_payload]
    st.markdown("### Approve tool call")
    st.caption("The agent paused before running a tool. Approve, edit the arguments, or reject.")

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

    if st.button("Submit decision", type="primary"):
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
                    {"type": "reject", "args": "User rejected this tool call."}
                )
        _run_agent(agent, Command(resume=resume_payload), thread_id)
        st.rerun()


# --- sidebar -----------------------------------------------------------------


def _sidebar(agent) -> None:
    with st.sidebar:
        # New conversation button at the top
        if st.button("+ New conversation", type="primary", use_container_width=True):
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.pending_interrupt = None
            st.rerun()

        st.divider()
        st.caption("Previous conversations")

        threads = _load_thread_list()
        active = st.session_state.thread_id

        if not threads:
            st.caption("No saved conversations yet.")
        else:
            for t in threads:
                is_active = t["thread_id"] == active
                label = ("▶  " if is_active else "   ") + t["label"]
                if st.button(
                    label,
                    key=f"thread_{t['thread_id']}",
                    use_container_width=True,
                    type="secondary",
                ):
                    _switch_thread(t["thread_id"])
                    st.rerun()


# --- page entry point --------------------------------------------------------


def render() -> None:
    _ensure_session()
    agent = _get_agent()
    _sidebar(agent)

    thread_id = st.session_state.thread_id
    st.title("Chat")
    st.caption(f"Thread: `{thread_id[:8]}…`")

    _render_history(agent, thread_id)

    if st.session_state.pending_interrupt is not None:
        _render_hitl(agent, st.session_state.pending_interrupt, thread_id)
        return

    prompt = st.chat_input("Message the agent...")
    if not prompt:
        return

    _render_user_text(prompt)
    _run_agent(agent, {"messages": [HumanMessage(content=prompt)]}, thread_id)

    # After the first user+assistant exchange, generate an LLM title once.
    if title_store.get_title(settings.db_path, thread_id) is None:
        state = agent.get_state(_thread_config(thread_id))
        msgs = state.values.get("messages", []) if state and state.values else []
        human_msgs = [m for m in msgs if isinstance(m, HumanMessage)]
        ai_msgs = [m for m in msgs if isinstance(m, AIMessage)]
        if human_msgs and ai_msgs:
            first_user = human_msgs[0].content if isinstance(human_msgs[0].content, str) else str(human_msgs[0].content)
            last_ai = ai_msgs[-1].content if isinstance(ai_msgs[-1].content, str) else str(ai_msgs[-1].content)
            with st.spinner("Naming conversation…"):
                generated = title_store.generate_title(first_user, last_ai, settings)
            title_store.save_title(settings.db_path, thread_id, generated)

    st.rerun()
