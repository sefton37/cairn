"""Shim — CCManager moved to trcore. This file exists for backward compatibility.

All imports of CCManager, AgentProcess, _slugify, and _summarize_tool_input from
cairn.services.cc_manager continue to work via this re-export. Also re-exports
WORKSPACE_ROOT so tests that patch it can continue to use the original patch path.
"""

from trcore.cc_manager import (
    WORKSPACE_ROOT,
    AgentProcess,
    CCManager,
    _slugify,
    _summarize_tool_input,
)

__all__ = ["AgentProcess", "CCManager", "WORKSPACE_ROOT", "_slugify", "_summarize_tool_input"]
