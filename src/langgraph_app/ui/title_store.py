"""Conversation title store.

Stores and retrieves LLM-generated titles for each thread in a
`conversation_titles` table in the same SQLite file used by SqliteSaver.
The checkpointer's schema is untouched — this is an additive table.

Public API
----------
get_title(db_path, thread_id)         -> str | None
save_title(db_path, thread_id, title) -> None
get_all_titles(db_path)               -> dict[str, str]
generate_title(user_msg, ai_reply, settings) -> str
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from langgraph_app.config import Settings


logger = logging.getLogger("langgraph_app.ui.title_store")

_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS conversation_titles (
    thread_id  TEXT PRIMARY KEY,
    title      TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now'))
);
"""


def _connect(db_path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.execute(_CREATE_TABLE)
    conn.commit()
    return conn


def get_title(db_path: str | Path, thread_id: str) -> str | None:
    """Return the stored title for `thread_id`, or None if not set."""
    try:
        conn = _connect(db_path)
        row = conn.execute(
            "SELECT title FROM conversation_titles WHERE thread_id = ?", (thread_id,)
        ).fetchone()
        conn.close()
        return row[0] if row else None
    except Exception as exc:
        logger.warning("title_store.get_title failed: %s", exc)
        return None


def save_title(db_path: str | Path, thread_id: str, title: str) -> None:
    """Upsert a title for `thread_id`."""
    try:
        conn = _connect(db_path)
        conn.execute(
            """
            INSERT INTO conversation_titles (thread_id, title)
            VALUES (?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET title = excluded.title
            """,
            (thread_id, title),
        )
        conn.commit()
        conn.close()
        logger.debug("title_store.save_title thread_id=%s title=%r", thread_id, title)
    except Exception as exc:
        logger.warning("title_store.save_title failed: %s", exc)


def delete_title(db_path: str | Path, thread_id: str) -> None:
    """Remove the stored title for `thread_id`, if any."""
    try:
        conn = _connect(db_path)
        conn.execute(
            "DELETE FROM conversation_titles WHERE thread_id = ?", (thread_id,)
        )
        conn.commit()
        conn.close()
        logger.debug("title_store.delete_title thread_id=%s", thread_id)
    except Exception as exc:
        logger.warning("title_store.delete_title failed: %s", exc)


def get_all_titles(db_path: str | Path) -> dict[str, str]:
    """Return all stored titles as {thread_id: title}."""
    try:
        conn = _connect(db_path)
        rows = conn.execute("SELECT thread_id, title FROM conversation_titles").fetchall()
        conn.close()
        return {row[0]: row[1] for row in rows}
    except Exception as exc:
        logger.warning("title_store.get_all_titles failed: %s", exc)
        return {}


def generate_title(user_message: str, assistant_reply: str, settings: "Settings") -> str:
    """Call the LLM once to produce a 4-6 word title for the conversation.

    Uses temperature=0 for determinism and truncates both messages to 300
    chars so the call is always cheap (one small prompt, no tools).
    Falls back to a truncated user message if the LLM call fails.
    """
    from langchain_openai import ChatOpenAI  # local import — keep module-level lean

    prompt = (
        "In 4 to 6 words, write a short title for a conversation that started with:\n\n"
        f"User: {user_message[:300]}\n"
        f"Assistant: {assistant_reply[:300]}\n\n"
        "Reply with only the title. No punctuation at the end, no quotes."
    )

    try:
        llm = ChatOpenAI(
            model=settings.model_name,
            api_key=settings.openai_api_key,
            temperature=0,
        )
        title = llm.invoke(prompt).content.strip()
        # Safety: cap length and strip any stray quotes the model may add.
        title = title.strip("\"'").strip()
        return title[:80] if title else _fallback_title(user_message)
    except Exception as exc:
        logger.warning("title_store.generate_title LLM call failed: %s", exc)
        return _fallback_title(user_message)


def _fallback_title(user_message: str) -> str:
    """Truncate the user's first message as a best-effort title."""
    text = user_message.strip().replace("\n", " ")
    return text[:50] + ("…" if len(text) > 50 else "")
