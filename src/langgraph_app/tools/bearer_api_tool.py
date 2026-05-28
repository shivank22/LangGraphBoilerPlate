"""Authenticated REST API tool.

Calls any HTTP endpoint with a Bearer token supplied at runtime through
LangChain's InjectedToolArg mechanism — the LLM never sees or controls
the token; it is injected from config["configurable"]["bearer_token"].

Usage:
- The LLM specifies url, method, and optional body/params.
- The Streamlit UI (or API caller) passes the bearer token via the
  RunnableConfig configurable dict.
"""

from __future__ import annotations

from typing import Annotated, Any

import httpx
from langchain_core.tools import InjectedToolArg, tool

from ..config import settings


DEFAULT_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

_ALLOWED_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE"})


@tool
def call_authenticated_api(
    url: str,
    method: str,
    json_body: dict[str, Any] | None = None,
    query_params: dict[str, Any] | None = None,
    bearer_token: Annotated[str, InjectedToolArg] = "",
) -> dict[str, Any]:
    """Call an external REST API endpoint using a Bearer token for authentication.

    Use this tool when the user asks you to interact with a protected REST API
    (e.g. fetch data from a service, submit a form, or trigger an action).

    Args:
        url: Full URL of the API endpoint, e.g. "https://api.example.com/v1/items".
        method: HTTP method — one of GET, POST, PUT, PATCH, DELETE (case-insensitive).
        json_body: Optional JSON request body for POST/PUT/PATCH requests.
        query_params: Optional key-value pairs appended as URL query parameters.

    Returns:
        A dict with ``status_code`` (int) and ``data`` (parsed JSON or raw text),
        or an ``error`` key describing what went wrong.
    """
    token = bearer_token or settings.api_bearer_token
    if not token:
        return {"error": "Bearer token not configured. Please enter it in the sidebar or .env."}

    normalised = method.upper().strip()
    if normalised not in _ALLOWED_METHODS:
        return {"error": f"Unsupported HTTP method '{method}'. Allowed: {sorted(_ALLOWED_METHODS)}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.request(
                method=normalised,
                url=url,
                headers=headers,
                json=json_body or None,
                params=query_params or None,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        return {
            "error": f"HTTP {exc.response.status_code} from {url}",
            "status_code": exc.response.status_code,
            "detail": exc.response.text[:500],
        }
    except httpx.HTTPError as exc:
        return {"error": f"Request to {url} failed: {exc!s}"}

    try:
        data = response.json()
    except Exception:
        data = response.text

    return {"status_code": response.status_code, "data": data}