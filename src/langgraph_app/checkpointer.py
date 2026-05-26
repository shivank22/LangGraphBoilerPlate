"""SQLite checkpointer factory.

A single SqliteSaver instance is intentionally shared across threads (the
checkpointer itself takes care of locking). The shared instance is fine for
Streamlit's threading model and for local development. For production
multi-process workloads swap this out for `PostgresSaver`.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from langgraph.checkpoint.sqlite import SqliteSaver


def get_sqlite_checkpointer(db_path: str | Path) -> SqliteSaver:
    """Return a `SqliteSaver` backed by a file at `db_path`.

    The parent directory is created if it doesn't exist.
    """
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path), check_same_thread=False)
    return SqliteSaver(conn)
