"""ScopedArtifactBackend: per-conversation / per-run artifact isolation.

This backend wraps an inner ``BackendProtocol`` (typically a
``FilesystemBackend``) and transparently rewrites the paths the agent uses so
that artifacts land under a run-scoped directory:

    agent path            on-disk / inner path
    ----------            --------------------
    /canvas.md      ->    /runs/<thread_id>/<run_hash>/canvas.md
    /servers.json   ->    /runs/<thread_id>/<run_hash>/servers.json
    /skills/...     ->    /skills/...            (passthrough, shared)

The agent (and the SKILL.md workflows) keep writing plain paths like
``/canvas.md``; isolation is enforced here, by the system, rather than relying
on the LLM to choose unique paths.

Scope components are read from the LangGraph run config
(``get_config()["configurable"]``):

- ``thread_id``  -> per-conversation isolation (deterministic, safe for
  parallel runs since each invocation carries its own thread id).
- ``run_hash``   -> per-invocation isolation, supplied by the caller
  (see ``api/router.py`` / ``ui/views/chat.py``). The same skill requested
  again in a later message lands in a different ``run_hash`` folder.

Only the synchronous backend methods are implemented; ``BackendProtocol``
provides async wrappers that delegate to these via ``asyncio.to_thread`` (which
copies the contextvars, so ``get_config()`` still resolves correctly).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from deepagents.backends.protocol import (
    BackendProtocol,
    EditResult,
    GlobResult,
    GrepResult,
    LsResult,
    ReadResult,
    WriteResult,
)

try:  # langgraph is always present at runtime; guard keeps imports resilient.
    from langgraph.config import get_config
except Exception:  # noqa: BLE001 - fall back to "no scope" outside a graph.
    get_config = None  # type: ignore[assignment]

if TYPE_CHECKING:
    from deepagents.backends.protocol import (
        FileDownloadResponse,
        FileInfo,
        FileUploadResponse,
    )

# Components that are interpolated into filesystem paths must not contain path
# separators or traversal sequences. Anything outside this set is replaced with
# "_" so a hostile/odd thread id or run hash cannot escape the runs root.
_SAFE_COMPONENT_RE = re.compile(r"[^A-Za-z0-9._-]")

_DEFAULT_THREAD = "_shared"
_DEFAULT_RUN = "_no_run"


def _safe_component(value: str, fallback: str) -> str:
    """Sanitize a single path component, falling back when empty/invalid."""
    cleaned = _SAFE_COMPONENT_RE.sub("_", value).strip("._") if value else ""
    return cleaned or fallback


def _normalize(path: str) -> str:
    """Ensure an absolute, forward-slash path without a trailing slash."""
    p = (path or "/").replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    if len(p) > 1 and p.endswith("/"):
        p = p.rstrip("/") or "/"
    return p


class ScopedArtifactBackend(BackendProtocol):
    """Wrap a backend, scoping artifact paths to ``/<runs_root>/<thread>/<run>``.

    Args:
        inner: The backend to delegate to (e.g. a ``FilesystemBackend``).
        runs_root: Virtual root under which run folders are created.
        passthrough: Path prefixes that bypass scoping entirely (shared,
            typically read-only, e.g. the skills library). ``runs_root`` is
            always treated as passthrough so already-scoped paths are never
            double-prefixed.
    """

    def __init__(
        self,
        inner: BackendProtocol,
        *,
        runs_root: str = "/runs",
        passthrough: tuple[str, ...] = ("/skills",),
    ) -> None:
        self._inner = inner
        self._runs_root = _normalize(runs_root)
        # De-duplicate while preserving order; always include the runs root.
        prefixes = [_normalize(p) for p in passthrough]
        if self._runs_root not in prefixes:
            prefixes.append(self._runs_root)
        self._passthrough = tuple(prefixes)

    # -- scope resolution ---------------------------------------------------

    def _scope(self) -> str:
        """Return the scope prefix, e.g. ``/runs/<thread_id>/<run_hash>``."""
        configurable: dict = {}
        if get_config is not None:
            try:
                cfg = get_config()
            except Exception:  # noqa: BLE001 - not inside a graph; use defaults.
                cfg = None
            if cfg:
                configurable = cfg.get("configurable", {}) or {}

        thread_id = _safe_component(str(configurable.get("thread_id") or ""), _DEFAULT_THREAD)
        run_hash = _safe_component(str(configurable.get("run_hash") or ""), _DEFAULT_RUN)
        return f"{self._runs_root}/{thread_id}/{run_hash}"

    def _is_passthrough(self, path: str) -> bool:
        norm = _normalize(path)
        return any(norm == p or norm.startswith(p + "/") for p in self._passthrough)

    def _to_inner(self, path: str) -> str:
        """Translate an agent-facing path to the inner (scoped) path."""
        norm = _normalize(path)
        if self._is_passthrough(norm):
            return norm
        scope = self._scope()
        return scope if norm == "/" else scope + norm

    def _from_inner(self, path: str) -> str:
        """Translate an inner path back to the stable agent-facing path."""
        norm = _normalize(path)
        scope = self._scope()
        if norm == scope:
            return "/"
        if norm.startswith(scope + "/"):
            return norm[len(scope) :]
        return norm

    def _remap_file_info(self, info: FileInfo) -> FileInfo:
        new = dict(info)
        if "path" in new:
            new["path"] = self._from_inner(str(new["path"]))
        return new  # type: ignore[return-value]

    # -- file operations ----------------------------------------------------

    def ls(self, path: str) -> LsResult:
        agent_path = _normalize(path)
        result = self._inner.ls(self._to_inner(agent_path))

        entries: list[FileInfo] = []
        if result.error:
            # A freshly created run has no directory on disk yet; present an
            # empty listing rather than a confusing "not found" for scoped
            # paths. Real passthrough errors are surfaced unchanged.
            if self._is_passthrough(agent_path):
                return result
        else:
            entries = [self._remap_file_info(fi) for fi in (result.entries or [])]

        if agent_path == "/":
            seen = {e.get("path") for e in entries}
            for prefix in self._passthrough:
                if prefix == self._runs_root:
                    continue
                if prefix not in seen:
                    entries.append({"path": prefix, "is_dir": True, "size": 0, "modified_at": ""})
            entries.sort(key=lambda e: e.get("path", ""))

        return LsResult(entries=entries)

    def read(self, file_path: str, offset: int = 0, limit: int = 2000) -> ReadResult:
        return self._inner.read(self._to_inner(file_path), offset=offset, limit=limit)

    def write(self, file_path: str, content: str) -> WriteResult:
        result = self._inner.write(self._to_inner(file_path), content)
        if result.path is not None:
            result.path = self._from_inner(result.path)
        return result

    def edit(
        self,
        file_path: str,
        old_string: str,
        new_string: str,
        replace_all: bool = False,  # noqa: FBT001, FBT002
    ) -> EditResult:
        result = self._inner.edit(self._to_inner(file_path), old_string, new_string, replace_all=replace_all)
        if result.path is not None:
            result.path = self._from_inner(result.path)
        return result

    def grep(self, pattern: str, path: str | None = None, glob: str | None = None) -> GrepResult:
        inner_path = self._to_inner(path if path is not None else "/")
        result = self._inner.grep(pattern, inner_path, glob)
        if result.matches:
            for match in result.matches:
                if "path" in match:
                    match["path"] = self._from_inner(str(match["path"]))
        return result

    def glob(self, pattern: str, path: str = "/") -> GlobResult:
        result = self._inner.glob(pattern, self._to_inner(path))
        if result.matches:
            result.matches = [self._remap_file_info(fi) for fi in result.matches]
        return result

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        translated = [(self._to_inner(p), content) for p, content in files]
        responses = self._inner.upload_files(translated)
        for original, response in zip(files, responses, strict=False):
            response.path = original[0]
        return responses

    def download_files(self, paths: list[str]) -> list[FileDownloadResponse]:
        translated = [self._to_inner(p) for p in paths]
        responses = self._inner.download_files(translated)
        for original, response in zip(paths, responses, strict=False):
            response.path = original
        return responses
