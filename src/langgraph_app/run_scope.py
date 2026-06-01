"""Helpers for deriving the per-run artifact scope (``run_hash``).

Artifacts written during a run are isolated under
``<runs_root>/<thread_id>/<run_hash>/`` by ``ScopedArtifactBackend``. The
``thread_id`` comes from the conversation; the ``run_hash`` identifies a single
user turn and is supplied by the caller (API / UI) through the run config.

We derive ``run_hash`` deterministically from the thread id and the turn index
(the number of human messages that started the turn). This has two useful
properties:

- A HITL **resume** continues the same turn without adding a new human message,
  so recomputing from the turn index yields the *same* ``run_hash`` and the
  resumed work lands in the same folder as the interrupted call.
- Asking for the same skill again in a later message is a new turn with a higher
  index, so it gets a different ``run_hash`` (and a separate artifact folder),
  satisfying "same skill twice in one chat -> different hash".
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from typing import Any


def count_human_messages(messages: Iterable[Any]) -> int:
    """Count human/user messages in a message list (by ``.type``)."""
    return sum(1 for m in messages if getattr(m, "type", None) == "human")


def derive_run_hash(thread_id: str, turn_index: int) -> str:
    """Return a short, stable hash for a given conversation turn."""
    raw = f"{thread_id}:{turn_index}".encode()
    return hashlib.sha1(raw).hexdigest()[:12]
