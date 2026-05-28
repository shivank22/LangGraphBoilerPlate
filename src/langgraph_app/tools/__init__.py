"""Agent tools.

Add new tools as separate modules and expose them here so `agent.py` can
pick them up without changes.

Tool groups
-----------
- ``MAIN_TOOLS``     -> attached to the main deep agent (platform APIs).
- ``RESEARCH_TOOLS`` -> attached to the ``code-researcher`` subagent (GitLab).
- ``ALL_TOOLS``      -> every tool, kept for backwards-compatible imports.
"""

from .api_tool import get_weather
from .bearer_api_tool import call_authenticated_api
from .gitlab_tool import gitlab_api

# Tools the main migration agent uses directly.
MAIN_TOOLS = [call_authenticated_api]

# Tools reserved for the code-research subagent (isolated context).
RESEARCH_TOOLS = [gitlab_api]

# Everything, including the original example tool.
ALL_TOOLS = [get_weather, call_authenticated_api, gitlab_api]

__all__ = [
    "ALL_TOOLS",
    "MAIN_TOOLS",
    "RESEARCH_TOOLS",
    "get_weather",
    "call_authenticated_api",
    "gitlab_api",
]
