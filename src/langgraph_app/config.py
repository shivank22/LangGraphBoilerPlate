"""Typed application settings loaded from environment variables / .env file.

Every module in the package should read configuration from the `settings`
singleton exported at the bottom of this file. Do NOT read environment
variables directly elsewhere — that keeps the config surface in one place
and makes the app easy to test and reconfigure.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    system_prompt: str = Field(
        default=(
            "You are a helpful, concise assistant. "
            "Use the tools available to you when relevant, and explain your reasoning briefly."
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
    guardrail_blocklist: list[str] = Field(
        default_factory=list,
        description="Case-insensitive substrings that cause the guardrail to refuse input.",
    )

    hitl_tools: list[str] = Field(
        default_factory=lambda: ["get_weather"],
        description="Tool names that require human approval before execution.",
    )

    log_level: str = Field(default="INFO")

    @field_validator("guardrail_blocklist", "hitl_tools", mode="before")
    @classmethod
    def _split_csv(cls, value: object) -> object:
        """Accept comma-separated strings in env vars and turn them into lists."""
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings accessor (one instance per process)."""
    return Settings()


settings = get_settings()
