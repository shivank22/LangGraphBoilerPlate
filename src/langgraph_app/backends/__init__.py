"""Custom storage backends for the deep agent.

The deep agent persists every file it writes through a ``BackendProtocol``
implementation. The stock ``FilesystemBackend`` writes all artifacts into a
single shared directory, so concurrent conversations (and even consecutive
runs of the same conversation) overwrite each other's ``canvas.md`` and other
scratch files.

``ScopedArtifactBackend`` wraps any backend and transparently rewrites
artifact paths into ``/<runs_root>/<thread_id>/<run_hash>/...`` so that every
conversation -- and every run within it -- gets an isolated artifact folder,
while shared, read-only paths (the skills library) pass through untouched.
"""

from .scoped import ScopedArtifactBackend

__all__ = ["ScopedArtifactBackend"]
