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
from langgraph_app.run_scope import count_human_messages, derive_run_hash
from langgraph_app.skill_progress import (
    STATUS_COMPLETED,
    STATUS_PENDING,
    load_phases,
    mark_waiting_for_interrupt,
    read_progress,
    write_progress,
)
from langgraph_app.ui import title_store
from langgraph_app.ui.components.skill_progress import render_skill_progress
from langgraph_app.ui.components.tool_activity import (
    render_tool_activity_card,
    should_show_tool_activity,
)


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
    if "current_run_hash" not in st.session_state:
        st.session_state.current_run_hash = None
    if "bearer_api_token" not in st.session_state:
        st.session_state.bearer_api_token = ""
    if "gitlab_token" not in st.session_state:
        st.session_state.gitlab_token = ""


def _hitl_auto_approve_flag_key(thread_id: str) -> str:
    """Session storage for auto-approve (not bound to a widget key)."""
    return f"hitl_auto_approve_flag_{thread_id}"


def _hitl_auto_approve_toggle_key(thread_id: str) -> str:
    """Streamlit widget key for the sidebar toggle."""
    return f"hitl_auto_approve_toggle_{thread_id}"


def _hitl_auto_approve_enabled(thread_id: str) -> bool:
    return bool(st.session_state.get(_hitl_auto_approve_flag_key(thread_id), False))


def _set_hitl_auto_approve(thread_id: str, enabled: bool) -> None:
    st.session_state[_hitl_auto_approve_flag_key(thread_id)] = enabled


def _request_hitl_approve_all(thread_id: str) -> None:
    """Streamlit callback: enable session auto-approve and process on next rerun."""
    _set_hitl_auto_approve(thread_id, True)
    st.session_state["hitl_approve_all_pending"] = True


def _resolve_display_run_hash(thread_id: str, messages: list[Any]) -> str | None:
    """Derive the run hash for the active turn from checkpoint message history."""
    human_count = count_human_messages(messages)
    if human_count == 0:
        return None
    turn_index = max(human_count - 1, 0)
    return derive_run_hash(thread_id, turn_index)


def _sync_pending_interrupt(agent, thread_id: str) -> None:
    """Refresh pending_interrupt from the agent checkpoint (avoids stale HITL UI)."""
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    run_hash = _resolve_display_run_hash(thread_id, messages) or st.session_state.get(
        "current_run_hash"
    )
    if run_hash:
        st.session_state.current_run_hash = run_hash
    config = _thread_config(thread_id, run_hash)
    st.session_state.pending_interrupt = _extract_interrupt_from_state(agent, config)


def _handle_pending_hitl_auto(agent, thread_id: str) -> bool:
    """Auto-approve a pending HITL interrupt. Returns True when the page should rerun."""
    pending = st.session_state.pending_interrupt
    if not _is_hitl_interrupt(pending):
        st.session_state.pop("hitl_approve_all_pending", None)
        return False
    if not (
        _hitl_auto_approve_enabled(thread_id)
        or st.session_state.get("hitl_approve_all_pending")
    ):
        return False

    _set_hitl_auto_approve(thread_id, True)
    st.session_state.pop("hitl_approve_all_pending", None)
    _run_agent(agent, Command(resume={"decisions": [{"type": "approve"}]}), thread_id)
    _sync_pending_interrupt(agent, thread_id)
    return True


def _switch_thread(thread_id: str) -> None:
    st.session_state.thread_id = thread_id
    st.session_state.pending_interrupt = None
    st.session_state.current_run_hash = None
    st.session_state.pop("hitl_approve_all_pending", None)


def _delete_thread(agent, thread_id: str) -> None:
    """Permanently delete a conversation: checkpoints + stored title.

    Mirrors the server-side deletion in `api/router.py`. If the deleted
    thread is the active one, start a fresh conversation.
    """
    try:
        agent.checkpointer.delete_thread(thread_id)
    except AttributeError:
        # Older checkpointer versions may not expose delete_thread.
        pass
    title_store.delete_title(settings.db_path, thread_id)
    if st.session_state.thread_id == thread_id:
        st.session_state.thread_id = str(uuid.uuid4())
        st.session_state.pending_interrupt = None
        st.session_state.current_run_hash = None


# --- helpers -----------------------------------------------------------------


def _thread_config(thread_id: str, run_hash: str | None = None) -> dict[str, Any]:
    configurable: dict[str, Any] = {
        "thread_id": thread_id,
        "bearer_token": st.session_state.get("bearer_api_token", ""),
        "gitlab_token": st.session_state.get("gitlab_token", ""),
    }
    if run_hash is not None:
        # Scopes artifacts to <runs_root>/<thread_id>/<run_hash>/ via
        # ScopedArtifactBackend (see backends/scoped.py).
        configurable["run_hash"] = run_hash
    return {"configurable": configurable}


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


def _truncate(text: str, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _tool_result_summary(name: str, data: Any) -> str:
    if isinstance(data, dict):
        if "error" in data:
            return f"{name} · error: {_truncate(data['error'])}"
        if "status_code" in data:
            return f"{name} · status {data['status_code']}"
    size_kb = len(str(data).encode("utf-8")) / 1024
    return f"{name} · {size_kb:.1f} KB"


def _render_skill_badge(skill_name: str) -> None:
    st.markdown(
        f'<div style="margin:6px 0;"><span style="background:#1f6f3f;'
        f'color:#fff;padding:3px 10px;border-radius:12px;font-size:0.85em;">'
        f"Using skill: {skill_name}</span></div>",
        unsafe_allow_html=True,
    )


def _skill_badge_shown_for_run(run_hash: str | None) -> bool:
    """True when the skill badge was already rendered above the progress panel."""
    if not run_hash:
        return False
    progress = read_progress(st.session_state.thread_id, run_hash)
    return bool(progress and progress.get("skill"))


def _skill_name_from_call(call: dict[str, Any]) -> str | None:
    """Return the skill name if `call` is a read_file on a /skills/<name>/SKILL.md path."""
    if call.get("name") != "read_file":
        return None
    path = str((call.get("args") or {}).get("file_path", "")).replace("\\", "/")
    parts = [p for p in path.split("/") if p]
    if not parts or not parts[-1].upper().startswith("SKILL"):
        return None
    if "skills" in parts:
        idx = parts.index("skills")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _tool_result_index(messages: list[Any]) -> dict[str, ToolMessage]:
    """Map tool_call_id -> ToolMessage for pairing with assistant tool calls."""
    index: dict[str, ToolMessage] = {}
    for message in messages:
        if not isinstance(message, ToolMessage):
            continue
        call_id = getattr(message, "tool_call_id", None)
        if call_id:
            index[str(call_id)] = message
    return index


def _render_message(
    message: Any,
    *,
    tool_results: dict[str, ToolMessage] | None = None,
    shown_tool_ids: set[str] | None = None,
    message_index: int = 0,
    run_hash: str | None = None,
) -> None:
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
            skill = _skill_name_from_call(call)
            if skill and not _skill_badge_shown_for_run(run_hash):
                _render_skill_badge(skill)
        tool_results = tool_results or {}
        shown_tool_ids = shown_tool_ids if shown_tool_ids is not None else set()
        for call_index, call in enumerate(getattr(message, "tool_calls", None) or []):
            tool_name = str(call.get("name", "tool"))
            if not should_show_tool_activity(tool_name):
                continue
            call_id = str(call.get("id", ""))
            result_message = tool_results.get(call_id) if call_id else None
            render_tool_activity_card(
                call,
                result_message,
                key_suffix=f"{message_index}_{call_index}_{call_id}",
            )
            if call_id:
                shown_tool_ids.add(call_id)
    elif isinstance(message, ToolMessage):
        call_id = str(getattr(message, "tool_call_id", "") or "")
        if shown_tool_ids is not None and call_id in shown_tool_ids:
            return
        tool_name = getattr(message, "name", None) or "tool"
        if not should_show_tool_activity(str(tool_name)):
            return
        content_str = str(message.content).strip() if message.content is not None else ""
        data = parse_json_recursively(content_str) if content_str else None
        with st.expander(f"Tool result: {_tool_result_summary(tool_name, data)}", expanded=False):
            if isinstance(data, (dict, list)):
                st.json(data)
            else:
                st.write(data)


def _progress_is_visible(progress: dict[str, Any] | None) -> bool:
    if not progress or not progress.get("skill"):
        return False
    phases = progress.get("phases") or {}
    return any(
        (phase or {}).get("status") != STATUS_PENDING for phase in phases.values()
    )


def _progress_insert_index(messages: list[Any], thread_id: str) -> int | None:
    """Index of the human message after which the skill progress panel is shown."""
    run_hash = _resolve_display_run_hash(thread_id, messages)
    if not run_hash:
        return None
    progress = read_progress(thread_id, run_hash)
    if not _progress_is_visible(progress):
        return None
    human_indices = [i for i, msg in enumerate(messages) if isinstance(msg, HumanMessage)]
    if not human_indices:
        return None
    return human_indices[-1]


def _render_history(agent, thread_id: str) -> None:
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    run_hash = _resolve_display_run_hash(thread_id, messages) or st.session_state.get(
        "current_run_hash"
    )
    if run_hash:
        st.session_state.current_run_hash = run_hash
    progress_after = _progress_insert_index(messages, thread_id)
    tool_results = _tool_result_index(messages)
    shown_tool_ids: set[str] = set()

    for index, msg in enumerate(messages):
        _render_message(
            msg,
            tool_results=tool_results,
            shown_tool_ids=shown_tool_ids,
            message_index=index,
            run_hash=run_hash,
        )
        if index == progress_after and run_hash:
            placeholder = st.empty()
            st.session_state.skill_progress_placeholder = placeholder
            _update_progress_panel(placeholder, thread_id, run_hash)


# --- agent invocation --------------------------------------------------------


def _extract_interrupt(result: Any) -> Any | None:
    if not isinstance(result, dict):
        return None
    interrupts = result.get("__interrupt__")
    if not interrupts:
        return None
    first = interrupts[0] if isinstance(interrupts, (list, tuple)) else interrupts
    return getattr(first, "value", first)


def _extract_interrupt_from_state(agent, config: dict[str, Any]) -> Any | None:
    state = agent.get_state(config)
    if state and getattr(state, "interrupts", None):
        first = state.interrupts[0]
        return getattr(first, "value", first)
    return None


def _phase_status(progress: dict[str, Any], phase_id: str) -> str:
    phase = progress.get("phases", {}).get(phase_id, {})
    return str(phase.get("status", STATUS_PENDING))


def _reconcile_run_progress(thread_id: str, run_hash: str | None) -> None:
    """Mark earlier phases complete when a later phase has already finished."""
    if not run_hash:
        return
    progress = read_progress(thread_id, run_hash)
    if not progress or not progress.get("skill"):
        return
    phase_ids = [phase["id"] for phase in load_phases(str(progress["skill"]))]
    if not phase_ids:
        return
    last_completed_index = -1
    for index, phase_id in enumerate(phase_ids):
        if _phase_status(progress, phase_id) == STATUS_COMPLETED:
            last_completed_index = index
    if last_completed_index <= 0:
        return
    phases = progress.setdefault("phases", {})
    for index in range(last_completed_index):
        phase_id = phase_ids[index]
        if _phase_status(progress, phase_id) != STATUS_COMPLETED:
            phases[phase_id] = {"status": STATUS_COMPLETED}
    write_progress(thread_id, run_hash, progress)


def _update_progress_panel(
    placeholder: Any,
    thread_id: str,
    run_hash: str | None,
) -> None:
    if placeholder is None or not run_hash:
        return
    _reconcile_run_progress(thread_id, run_hash)
    progress = read_progress(thread_id, run_hash)
    if not progress:
        placeholder.empty()
        return
    skill_name = str(progress.get("skill", ""))
    phases = load_phases(skill_name)
    with placeholder.container():
        if skill_name:
            _render_skill_badge(skill_name)
        render_skill_progress(progress, phases)


def _mark_interrupt_progress(
    thread_id: str,
    run_hash: str,
    interrupt_payload: Any,
) -> None:
    if _is_hitl_interrupt(interrupt_payload):
        requests = interrupt_payload.get("action_requests") or []
        if not requests:
            return
        request = requests[0] if isinstance(requests[0], dict) else {}
        mark_waiting_for_interrupt(
            thread_id,
            run_hash,
            tool_name=str(request.get("name", "call_authenticated_api")),
            args=request.get("args") or {},
        )
    else:
        mark_waiting_for_interrupt(thread_id, run_hash, tool_name="ask_user")


def _drain_hitl_auto_approvals(
    agent,
    thread_id: str,
    config: dict[str, Any],
    placeholder: Any,
    run_hash: str,
) -> None:
    """Auto-approve sequential HITL interrupts while session auto-approve is on."""
    while _hitl_auto_approve_enabled(thread_id):
        interrupt = _extract_interrupt_from_state(agent, config)
        if not _is_hitl_interrupt(interrupt):
            break
        for _chunk in agent.stream(
            Command(resume={"decisions": [{"type": "approve"}]}),
            config=config,
            stream_mode="values",
        ):
            _update_progress_panel(placeholder, thread_id, run_hash)
        _reconcile_run_progress(thread_id, run_hash)
        _update_progress_panel(placeholder, thread_id, run_hash)


def _run_agent(agent, payload: Any, thread_id: str) -> None:
    # Derive a per-turn run_hash so artifacts are isolated per run. A resume
    # (Command payload) continues the interrupted turn, so reuse that turn's
    # index; a fresh message dict starts a new turn.
    state = agent.get_state(_thread_config(thread_id))
    messages = state.values.get("messages", []) if state and state.values else []
    human_count = count_human_messages(messages)
    is_resume = not isinstance(payload, dict)
    turn_index = max(human_count - 1, 0) if is_resume else human_count
    run_hash = derive_run_hash(thread_id, turn_index)
    st.session_state.current_run_hash = run_hash
    config = _thread_config(thread_id, run_hash)
    placeholder = st.session_state.get("skill_progress_placeholder")

    with st.spinner("Thinking..."):
        for _chunk in agent.stream(payload, config=config, stream_mode="values"):
            _update_progress_panel(placeholder, thread_id, run_hash)

        _drain_hitl_auto_approvals(agent, thread_id, config, placeholder, run_hash)

    _reconcile_run_progress(thread_id, run_hash)
    interrupt = _extract_interrupt_from_state(agent, config)
    st.session_state.pending_interrupt = interrupt
    if interrupt is not None:
        hitl = _is_hitl_interrupt(interrupt)
        if not (hitl and _hitl_auto_approve_enabled(thread_id)):
            _mark_interrupt_progress(thread_id, run_hash, interrupt)
    _update_progress_panel(placeholder, thread_id, run_hash)


def _is_hitl_interrupt(interrupt_payload: Any) -> bool:
    """True when the interrupt is a tool-approval request from HITL middleware."""
    return isinstance(interrupt_payload, dict) and bool(interrupt_payload.get("action_requests"))


def _render_user_input(agent, interrupt_payload: Any, thread_id: str) -> None:
    """Render a form for ``ask_user`` / LangGraph ``interrupt()`` user-input pauses."""
    if isinstance(interrupt_payload, dict):
        question = interrupt_payload.get("question") or "Please provide your answer:"
        dropdown_values = interrupt_payload.get("dropdown_values") or []
    else:
        question = str(interrupt_payload)
        dropdown_values = []

    st.markdown("### Your input is needed")
    st.caption("The agent paused to collect your answer before continuing.")

    with st.container(border=True):
        if dropdown_values:
            answer = st.selectbox(
                question,
                options=dropdown_values,
                key="user_input_select",
            )
        else:
            answer = st.text_input(question, key="user_input_text")

        if st.button("Submit answer", type="primary"):
            _run_agent(agent, Command(resume=answer), thread_id)
            st.rerun()


def _render_hitl(agent, interrupt_payload: Any, thread_id: str) -> None:
    """Render approval UI for a single gated tool call.

    Sequential HITL middleware emits one ``action_requests`` entry per interrupt.
    Resume with ``Command(resume={"decisions": [<decision>]})``.
    """
    if _hitl_auto_approve_enabled(thread_id):
        return

    payload = interrupt_payload if isinstance(interrupt_payload, dict) else {}
    action_requests = payload.get("action_requests") or []
    review_configs = payload.get("review_configs") or []

    st.markdown("### Approve tool call")
    st.caption(
        "The agent paused before running one tool. Approve, edit the arguments, "
        "or reject. Additional gated tools in this turn will prompt separately "
        "unless auto-approve is enabled."
    )

    if not action_requests:
        st.warning("Nothing to approve (empty interrupt payload).")
        return

    request = action_requests[0] if isinstance(action_requests[0], dict) else {}
    tool_name = request.get("name") or "tool"
    tool_args = request.get("args") or {}
    description = request.get("description") or ""

    config = review_configs[0] if review_configs else {}
    allowed = [
        d
        for d in (config.get("allowed_decisions") or ["approve", "edit", "reject"])
        if d != "respond"
    ]

    with st.container(border=True):
        st.markdown(f"**Tool:** `{tool_name}`")
        if description:
            st.caption(description)
        edited_args_json = st.text_area(
            "Arguments (edit before approving if needed):",
            value=json.dumps(tool_args, indent=2),
            key="hitl_args",
            height=140,
        )
        choice = st.radio(
            "Decision",
            options=allowed,
            horizontal=True,
            key="hitl_choice",
        )

    col_once, col_all = st.columns(2)
    with col_once:
        submit_once = st.button("Submit decision", type="primary", use_container_width=True)
    with col_all:
        st.button(
            "Approve all for this conversation",
            use_container_width=True,
            help="Approve this tool and automatically approve every remaining "
            "gated tool call in this conversation.",
            on_click=_request_hitl_approve_all,
            args=(thread_id,),
        )

    if submit_once:
        if choice == "edit":
            try:
                args = json.loads(edited_args_json)
            except json.JSONDecodeError as exc:
                st.error(f"Edited arguments are not valid JSON: {exc}")
                return
            decision: dict[str, Any] = {
                "type": "edit",
                "edited_action": {"name": tool_name, "args": args},
            }
        elif choice == "reject":
            decision = {"type": "reject", "message": "User rejected this tool call."}
        else:
            decision = {"type": "approve"}
        _run_agent(agent, Command(resume={"decisions": [decision]}), thread_id)
        st.rerun()


# --- sidebar -----------------------------------------------------------------


def _sidebar(agent) -> None:
    with st.sidebar:
        # New conversation button at the top
        if st.button("+ New conversation", type="primary", use_container_width=True):
            st.session_state.thread_id = str(uuid.uuid4())
            st.session_state.pending_interrupt = None
            st.session_state.current_run_hash = None
            st.rerun()

        st.divider()
        st.caption("API Authentication")
        st.text_input(
            "Bearer token",
            key="bearer_api_token",
            type="password",
            placeholder="1234 for mock API",
            help="Used automatically when the agent calls the platform/servers REST API. "
            "Mock discovery endpoints require `1234`.",
        )
        st.text_input(
            "GitLab PAT",
            key="gitlab_token",
            type="password",
            placeholder="Paste GitLab token here…",
            help="GitLab Personal Access Token used by the code-research subagent.",
        )

        st.divider()
        st.caption("Tool approvals")
        thread_id = st.session_state.thread_id
        toggle_key = _hitl_auto_approve_toggle_key(thread_id)
        st.session_state[toggle_key] = _hitl_auto_approve_enabled(thread_id)
        st.toggle(
            "Auto-approve gated tools (this conversation)",
            key=toggle_key,
            help="When enabled, write_file, edit_file, call_authenticated_api, and "
            "other HITL-gated tools are approved automatically for this conversation. "
            "Questionnaire prompts (ask_user) still require your input.",
        )
        _set_hitl_auto_approve(thread_id, st.session_state[toggle_key])

        st.divider()
        st.toggle(
            "Show all tool activity",
            key="show_tool_activity",
            value=False,
            help="Also show non-HITL tool calls (read_file, write_file, questionnaire, etc.). "
            "HITL-approved API calls are always visible.",
        )

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
                col_sel, col_del = st.columns([0.82, 0.18], vertical_alignment="center")
                if col_sel.button(
                    label,
                    key=f"thread_{t['thread_id']}",
                    use_container_width=True,
                    type="secondary",
                ):
                    _switch_thread(t["thread_id"])
                    st.rerun()
                if col_del.button(
                    "",
                    icon=":material/delete:",
                    key=f"del_{t['thread_id']}",
                    use_container_width=True,
                    help="Delete this conversation",
                ):
                    _delete_thread(agent, t["thread_id"])
                    st.rerun()


# --- page entry point --------------------------------------------------------


def render() -> None:
    _ensure_session()
    agent = _get_agent()
    _sidebar(agent)

    thread_id = st.session_state.thread_id
    col_title, col_info = st.columns([0.92, 0.08], vertical_alignment="center")
    with col_title:
        st.title("DICE Agent")
    with col_info:
        with st.popover("i", help="Conversation details", use_container_width=True):
            st.markdown("**Thread id**")
            st.code(thread_id, language="text")

    _render_history(agent, thread_id)

    _sync_pending_interrupt(agent, thread_id)

    if st.session_state.pending_interrupt is not None:
        if _is_hitl_interrupt(st.session_state.pending_interrupt):
            auto_processed = False
            for _ in range(20):
                if not _handle_pending_hitl_auto(agent, thread_id):
                    break
                auto_processed = True
                _sync_pending_interrupt(agent, thread_id)
                if not _is_hitl_interrupt(st.session_state.pending_interrupt):
                    break
            if auto_processed:
                st.rerun()
                return
            _render_hitl(agent, st.session_state.pending_interrupt, thread_id)
        else:
            _render_user_input(agent, st.session_state.pending_interrupt, thread_id)
        return

    prompt = st.chat_input("Message the agent...")
    if not prompt:
        return

    _render_user_text(prompt)
    progress_placeholder = st.empty()
    st.session_state.skill_progress_placeholder = progress_placeholder
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
