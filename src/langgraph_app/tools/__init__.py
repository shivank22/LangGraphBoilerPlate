"""Agent tools.

Add new tools as separate modules and expose them in `ALL_TOOLS` so
`agent.py` can pick them up without changes.
"""

from .api_tool import get_weather

ALL_TOOLS = [get_weather]

__all__ = ["ALL_TOOLS", "get_weather"]
