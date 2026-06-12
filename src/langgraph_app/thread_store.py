"""Thread list and conversation metadata backed by SQLite checkpoints."""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import Any

from langgraph_app.config import settings
from langgraph_app.ui import title_store


logger = logging.getLogger("langgraph_app.thread_store")


def load_thread_list(db_path: str | Path | None = None) -> list[dict[str, Any]]:
    """Return threads ordered by most-recently updated checkpoint.

    Labels come from ``conversation_titles`` (LLM-generated). Threads without
    a title fall back to a short hash label.
    """
    path = Path(db_path or settings.db_path)
    if not path.exists():
        return []
    try:
        conn = sqlite3.connect(str(path), check_same_thread=False)
        rows = conn.execute(
            """
            SELECT thread_id, MAX(checkpoint_id) AS latest
            FROM checkpoints
            GROUP BY thread_id
            ORDER BY latest DESC
            """
        ).fetchall()
        conn.close()
    except Exception as exc:
        logger.warning("load_thread_list failed: %s", exc)
        return []

    all_titles = title_store.get_all_titles(path)
    threads: list[dict[str, Any]] = []
    for thread_id, _ in rows:
        short = thread_id[:8] if len(thread_id) >= 8 else thread_id
        label = all_titles.get(thread_id) or f"Chat {short}…"
        threads.append({"thread_id": thread_id, "label": label, "short_id": short})
    return threads
