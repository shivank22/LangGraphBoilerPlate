"""Typed application settings loaded from environment variables / .env file.

Every module in the package should read configuration from the `settings`
singleton exported at the bottom of this file. Do NOT read environment
variables directly elsewhere — that keeps the config surface in one place
and makes the app easy to test and reconfigure.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    openai_api_key: str = Field(default="", description="OpenAI API key.")
    model_name: str = Field(default="gpt-5.2", description="OpenAI model identifier.")
    temperature: float = Field(default=0.2, ge=0.0, le=2.0)

    db_path: str = Field(
        default=str(PROJECT_ROOT / "data" / "checkpoints.sqlite"),
        description="Filesystem path to the SQLite checkpoint database.",
    )

    workspace_dir: str = Field(
        default=str(PROJECT_ROOT / "agent_workspace"),
        description=(
            "Root directory for the deep agent's filesystem backend. Skills are "
            "loaded from `<workspace_dir>/skills` and scratch files (canvas.md, "
            "servers.json, ...) are written here."
        ),
    )

    # --- Credentials for outbound API tools ---------------------------------
    # These are optional fallbacks used by headless callers (e.g. the FastAPI
    # routes). The Streamlit UI supplies them per-session instead and injects
    # them through the run config, which takes precedence.
    api_bearer_token: str = Field(
        default="",
        description="Bearer token for the platform/servers REST API (fallback).",
    )
    gitlab_token: str = Field(
        default="",
        description="GitLab Personal Access Token used by the gitlab_api tool (fallback).",
    )
    gitlab_base_url: str = Field(
        default="https://gitlab.com/api/v4",
        description="Base URL for the GitLab REST API (no trailing slash).",
    )

    system_prompt: str = Field(
        default=(
            "You are a migration assistant that helps move legacy on-prem "
            "workloads to managed Azure Kubernetes Service (AKS). "
            "You have access to skills describing multi-step migration "
            "workflows — consult them when a request matches. "
            "Use the available tools to query the platform APIs and GitLab, "
            "save intermediate results to the filesystem (for example "
            "`/canvas.md`), and delegate codebase research to the "
            "`code-researcher` subagent. Explain your reasoning briefly and "
            "cite the files you wrote when presenting recommendations."
        ),
        description="System prompt prepended to every conversation.",
    )

    max_iterations: int = Field(
        default=8,
        ge=1,
        description="Hard cap on model calls per agent run (guardrail).",
    )
    max_input_chars: int = Field(
        default=8000,
        ge=1,
        description="Reject user turns whose latest message exceeds this size (guardrail).",
    )
    # NoDecode tells pydantic-settings NOT to JSON-decode env values for these
    # fields, so the `_split_csv` validator below receives the raw string and
    # can parse a comma-separated list (e.g. `HITL_TOOLS=get_weather,send_email`).
    guardrail_blocklist: Annotated[list[str], NoDecode] = Field(
        default_factory=list,
        description="Case-insensitive substrings that cause the guardrail to refuse input.",
    )

    hitl_tools: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["call_authenticated_api"],
        description="Tool names that require human approval before execution.",
    )

    log_level: str = Field(default="INFO")

    @field_validator("guardrail_blocklist", "hitl_tools", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated strings in env vars and turn them into lists.

        Handles three input shapes:
          - already-a-list (e.g. passed in from Python) -> returned as-is
          - empty string (e.g. `HITL_TOOLS=` in .env)  -> `[]`
          - "a,b,c" or "a, b ,c" -> ["a", "b", "c"]
        """
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()


settings = get_settings()
