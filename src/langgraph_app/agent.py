"""Single assembly point for the LangGraph deep agent.

`build_agent()` is the only place where the model, tools, middleware,
filesystem backend, skills, subagents, and checkpointer are wired together.
Importing from this module is the recommended entry point for the rest of
the application (UI, scripts, tests).

The agent is built with `deepagents.create_deep_agent`, which augments a
standard LangGraph agent with a planning tool, a filesystem (read/write/edit
files), subagent delegation, and the SKILL.md progressive-disclosure system.
The compiled result is a normal LangGraph graph, so `invoke`, `get_state`,
and `Command(resume=...)` work exactly as before.
"""

from __future__ import annotations

import logging
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend
from langchain_openai import ChatOpenAI

from .backends import ScopedArtifactBackend
from .checkpointer import get_sqlite_checkpointer
from .config import settings
from .middleware import GuardrailMiddleware, LoggingMiddleware
from .tools import MAIN_TOOLS, RESEARCH_TOOLS


def _configure_logging() -> None:
    """Configure root logging once, idempotently."""
    root = logging.getLogger()
    if getattr(_configure_logging, "_configured", False):
        return
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    )
    root.setLevel(settings.log_level.upper())
    _configure_logging._configured = True  # type: ignore[attr-defined]


def _build_model() -> ChatOpenAI:
    if not settings.openai_api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Copy .env.example to .env and fill it in."
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.temperature,
    )


_RESEARCH_SUBAGENT_PROMPT = (
    "You are a code-research specialist supporting a legacy-to-AKS migration. "
    "Given an application and its GitLab project, use the `gitlab_api` tool to "
    "inspect the repository: identify the language/runtime, build system, "
    "Dockerfiles or existing Kubernetes/Helm manifests, configuration and "
    "secrets handling, stateful dependencies (databases, local disk), and any "
    "obvious blockers to containerization. Save useful findings to files when "
    "helpful. Return a concise assessment of the application's AKS migration "
    "readiness with concrete observations and risks."
)


def _ensure_workspace() -> str:
    """Create the workspace + skills directories and return the workspace root."""
    workspace = Path(settings.workspace_dir)
    (workspace / "skills").mkdir(parents=True, exist_ok=True)
    return str(workspace)


def build_agent():
    """Build and return the compiled deep agent.

    Components:
      - model        : ChatOpenAI from settings
      - tools        : MAIN_TOOLS (platform/servers REST API)
      - backend      : FilesystemBackend rooted at settings.workspace_dir
      - skills       : <workspace_dir>/skills (e.g. aks-migration)
      - subagents    : code-researcher (owns the GitLab tool)
      - middleware   : Guardrail + Logging (deep agent adds its own)
      - interrupt_on : HITL approval for tools listed in settings.hitl_tools
      - checkpointer : SqliteSaver
    """
    _configure_logging()

    workspace = _ensure_workspace()
    model = _build_model()
    # virtual_mode=True: all agent paths are virtual, anchored at root_dir
    # (the workspace). A leading-slash path like `/research_canvas.md` or
    # `/skills/...` therefore resolves UNDER the workspace instead of the real
    # filesystem root. This is required so the skills' canvas/scratch writes
    # (which use `/...` paths) succeed; with virtual_mode=False they would hit
    # the read-only OS root. Files still persist to disk under root_dir.
    backend = FilesystemBackend(root_dir=workspace, virtual_mode=True)
    if settings.artifacts_isolation:
        # Transparently rewrite artifact paths to
        # `<runs_root>/<thread_id>/<run_hash>/...` so concurrent conversations
        # and consecutive runs never clobber each other's scratch files. The
        # `/skills` library stays shared and read-only (passthrough). thread_id
        # and run_hash are read from the run config at write time (see
        # api/router.py and ui/views/chat.py).
        backend = ScopedArtifactBackend(
            backend,
            runs_root=settings.artifacts_runs_root,
            passthrough=("/skills",),
        )
    checkpointer = get_sqlite_checkpointer(settings.db_path)

    research_subagent = {
        "name": "code-researcher",
        "description": (
            "Researches an application's GitLab codebase to judge its AKS "
            "migration suitability. Delegate to this subagent with the "
            "application name and its GitLab project id/path."
        ),
        "system_prompt": _RESEARCH_SUBAGENT_PROMPT,
        "tools": RESEARCH_TOOLS,
        "model": model,
        # Don't inherit the top-level HITL gates inside the subagent. Approval
        # prompts raised inside a `task` subagent surface awkwardly, so we keep
        # human-in-the-loop at the main-agent level only. Set to a dict like
        # {"write_file": True} if you DO want to gate the subagent's writes.
        "interrupt_on": {},
    }

    return create_deep_agent(
        model=model,
        tools=MAIN_TOOLS,
        system_prompt=settings.system_prompt,
        backend=backend,
        # Virtual path under root_dir (the workspace); resolves to
        # <workspace>/skills via the FilesystemBackend in virtual_mode.
        skills=["/skills"],
        subagents=[research_subagent],
        middleware=[
            GuardrailMiddleware(
                max_iterations=settings.max_iterations,
                max_input_chars=settings.max_input_chars,
                blocklist=settings.guardrail_blocklist,
            ),
            LoggingMiddleware(),
        ],
        interrupt_on={name: True for name in settings.hitl_tools},
        checkpointer=checkpointer,
    )
