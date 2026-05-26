"""Example API-calling tool.

This is an intentionally small, dependency-light template. To plug in your
own API:

1. Rename `get_weather` to your tool name.
2. Replace the URL, query params, and response shaping.
3. Pull any auth credentials from `langgraph_app.config.settings`, never
   hardcode them here.
4. Keep the `@tool` decorator + clear docstring + typed args — that's what
   the model uses to decide when/how to call the tool.
"""

from __future__ import annotations

import httpx
from langchain_core.tools import tool


OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)


@tool
def get_weather(latitude: float, longitude: float) -> dict:
    """Get the current weather for a latitude/longitude pair.

    Args:
        latitude: Decimal degrees, e.g. 52.52 for Berlin.
        longitude: Decimal degrees, e.g. 13.41 for Berlin.

    Returns:
        A dict with `temperature_c`, `windspeed_kmh`, `weathercode`, and
        the `time` of the observation. Returns an `error` key on failure.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as client:
            response = client.get(OPEN_METEO_URL, params=params)
            response.raise_for_status()
            data = response.json()
    except httpx.HTTPError as exc:
        return {"error": f"weather api request failed: {exc!s}"}

    current = data.get("current_weather") or {}
    if not current:
        return {"error": "weather api returned no current_weather block"}

    return {
        "temperature_c": current.get("temperature"),
        "windspeed_kmh": current.get("windspeed"),
        "weathercode": current.get("weathercode"),
        "time": current.get("time"),
    }
