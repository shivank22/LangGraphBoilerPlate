"""GitLab REST API tool.

Used by the `code-researcher` subagent to inspect an application's source
repository when assessing AKS migration suitability.

Authentication uses a GitLab Personal Access Token (PAT). The token is
supplied at runtime through the run config — the LLM never sees it — read from
config["configurable"]["gitlab_token"], falling back to ``settings.gitlab_token``
for headless callers. GitLab authenticates PATs via the ``PRIVATE-TOKEN`` header.
"""

from __future__ import annotations

from typing import Any

import httpx
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from ..config import settings


DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


def _build_url(path: str) -> str:
    base = settings.gitlab_base_url.rstrip("/")
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return f"{base}/{path.lstrip('/')}"


@tool
def gitlab_api(
    path: str,
    method: str = "GET",
    json_body: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    config: RunnableConfig = None,  # injected by LangChain; hidden from the model
) -> dict[str, Any]:
    """Call the GitLab REST API to research a repository.

    Use this to look up projects, browse repository files, read file contents,
    list branches/commits, or fetch any other GitLab resource needed to assess
    how an application should be migrated to AKS.

    Args:
        path: API path relative to the GitLab base URL (e.g.
            "projects/42/repository/tree") or a full URL.
        method: HTTP method — one of GET, POST, PUT, PATCH, DELETE.
        json_body: Optional JSON request body for write operations.
        query_params: Optional query parameters (e.g. {"ref": "main", "path": "k8s"}).

    Returns:
        A dict with ``status_code`` and ``data`` (parsed JSON or raw text),
        or an ``error`` key describing what went wrong.
    """
    configurable = (config or {}).get("configurable", {})
    token = configurable.get("gitlab_token") or settings.gitlab_token
    if not token:
        return {"error": "GitLab PAT not configured. Please enter it in the sidebar or .env."}

    normalised = method.upper().strip()
    if normalised not in _ALLOWED_METHODS:
        return {"error": f"Unsupported HTTP method '{method}'. Allowed: {sorted(_ALLOWED_METHODS)}"}

    headers = {
        "PRIVATE-TOKEN": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.request(
                method=normalised,
                url=_build_url(path),
                headers=headers,
                json=json_body or None,
                params=query_params or None,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"HTTP {exc.response.status_code} from GitLab",
            "status_code": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except httpx.HTTPError as exc:
        return {"error": f"GitLab request failed: {exc!s}"}

    try:
        data = response.json()
    except Exception:
        data = response.text

    return {"status_code": response.status_code, "data": data}
