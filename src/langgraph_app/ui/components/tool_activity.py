"""Compact tool-call activity cards for the chat UI."""

from __future__ import annotations

import json
from typing import Any

import streamlit as st

from langgraph_app.config import settings


def is_hitl_tool(tool_name: str) -> bool:
    return tool_name in settings.hitl_tools


def should_show_tool_activity(tool_name: str) -> bool:
    """HITL-gated tools are always shown; others follow the sidebar toggle."""
    if is_hitl_tool(tool_name):
        return True
    return bool(st.session_state.get("show_tool_activity", False))


def _truncate(text: str, limit: int = 72) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "\u2026"


def _parse_content(content: Any) -> Any:
    if isinstance(content, (dict, list)):
        return content
    if isinstance(content, str):
        text = content.strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return content


def describe_tool_call(call: dict[str, Any]) -> str:
    """One-line human description of a tool invocation."""
    name = call.get("name", "tool")
    args = call.get("args") or {}
    if not isinstance(args, dict):
        return name

    if name == "call_authenticated_api":
        method = str(args.get("method", "GET")).upper()
        url = str(args.get("url", ""))
        return f"{method} {url}" if url else method

    if name == "ask_user":
        return _truncate(str(args.get("question", "User input")))

    if name in {"load_application_questionnaire", "save_questionnaire_answer"}:
        aa = args.get("aa_code")
        if aa:
            return f"AA {aa}"
        return name

    if name == "build_discovery_artifact":
        aa = args.get("aa_code")
        return f"AA {aa}" if aa else "discovery JSON"

    if name == "read_file":
        return _truncate(str(args.get("file_path", "")))

    if name in {"write_file", "edit_file"}:
        return _truncate(str(args.get("file_path", "")))

    if args:
        key = next(iter(args))
        return f"{key}={_truncate(args[key])}"
    return name


def describe_tool_result(tool_name: str, data: Any) -> str:
    if isinstance(data, dict):
        if data.get("error"):
            return f"Error: {_truncate(str(data['error']))}"
        if tool_name == "call_authenticated_api":
            status = data.get("status_code")
            return f"HTTP {status}" if status is not None else "OK"
        if tool_name == "save_questionnaire_answer":
            unanswered = data.get("unanswered_count")
            if unanswered is not None:
                return f"{data.get('answered_count', '?')} answered, {unanswered} remaining"
        if tool_name == "build_discovery_artifact":
            apps = data.get("application_count")
            servers = data.get("server_count")
            if apps is not None and servers is not None:
                return f"{servers} servers, {apps} applications"
        if tool_name == "load_application_questionnaire":
            return (
                f"{data.get('answered_count', 0)}/{data.get('total', 0)} answered"
            )
    return _truncate(str(data))


def _status_line(tool_name: str, data: Any | None) -> tuple[str, str]:
    """Return (status label, css color) for the activity card."""
    if data is None:
        return ("Requested", "#888")
    if isinstance(data, dict) and data.get("error"):
        return ("Executed · Error", "#c0392b")
    if is_hitl_tool(tool_name):
        return ("Approved · Executed", "#2e7d4f")
    return ("Executed", "#4c8bf5")


def render_tool_activity_card(
    call: dict[str, Any],
    result_message: Any | None = None,
    *,
    key_suffix: str = "",
) -> None:
    """Render a compact tool activity strip with optional detail expander."""
    tool_name = str(call.get("name", "tool"))
    description = describe_tool_call(call)
    result_data = None
    if result_message is not None:
        result_data = _parse_content(getattr(result_message, "content", None))

    status, status_color = _status_line(tool_name, result_data)
    result_summary = describe_tool_result(tool_name, result_data) if result_data is not None else ""

    hitl_badge = ""
    if is_hitl_tool(tool_name):
        hitl_badge = (
            '<span style="background:#2e7d4f;color:#fff;padding:2px 8px;'
            'border-radius:10px;font-size:0.75em;margin-right:6px;">HITL</span>'
        )

    detail_line = result_summary or "Awaiting result…"
    st.markdown(
        f'<div style="margin:6px 0 6px 20px;padding:10px 14px;border-left:3px solid {status_color};'
        f'background:rgba(127,127,127,0.08);border-radius:6px;font-size:0.92em;">'
        f'{hitl_badge}<strong>`{tool_name}`</strong> '
        f'<span style="color:{status_color};">{status}</span><br>'
        f'<span style="color:#555;">{_truncate(description, 120)}</span><br>'
        f'<span style="color:#888;font-size:0.88em;">{detail_line}</span>'
        f"</div>",
        unsafe_allow_html=True,
    )

    with st.expander("Details", expanded=False, key=f"tool_details_{key_suffix}"):
        st.caption("Arguments")
        st.json(call.get("args") or {})
        if result_data is not None:
            st.caption("Result")
            if isinstance(result_data, (dict, list)):
                st.json(result_data)
            else:
                st.code(str(result_data))
