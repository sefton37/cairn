"""Shared tool implementations for ReOS MCP + internal agent.

ReOS provides CAIRN tools for personal knowledge management:

- Calendar and event access via Thunderbird
- Contact search via Thunderbird
- Acts and Scenes management (The Play)
- Todo/task surfacing and prioritisation

The MCP server wraps these results into MCP's `content` envelope.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .db import Database

_JSON = dict[str, Any]


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]


def list_tools() -> list[Tool]:
    """List all available CAIRN tools."""
    tools: list[Tool] = []

    # =========================================================================
    # CAIRN Tools (Knowledge Management & Thunderbird Integration)
    # CAIRN is the Attention Minder - helps manage tasks, calendar, contacts
    # =========================================================================
    tools.extend(
        [
            Tool(
                name="cairn_get_calendar",
                description=(
                    "Get calendar events from Thunderbird for a date range. "
                    "Use this to see the user's schedule, appointments, and meetings."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "start": {
                            "type": "string",
                            "description": "Start date (ISO format, default: now)",
                        },
                        "end": {
                            "type": "string",
                            "description": "End date (ISO format, default: 30 days from start)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_get_upcoming_events",
                description=(
                    "Get upcoming calendar events in the next N hours. "
                    "Great for showing what's coming up soon."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "hours": {
                            "type": "number",
                            "description": "Hours to look ahead (default: 24)",
                        },
                        "limit": {
                            "type": "number",
                            "description": "Max events to return (default: 10)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_get_todos",
                description="Get todos/tasks from Thunderbird calendar.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "include_completed": {
                            "type": "boolean",
                            "description": "Include completed todos (default: false)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_search_contacts",
                description="Search Thunderbird contacts by name, email, or organization.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "limit": {"type": "number", "description": "Max results (default: 20)"},
                    },
                    "required": ["query"],
                },
            ),
            Tool(
                name="cairn_thunderbird_status",
                description="Check Thunderbird integration status (detected paths, availability).",
                input_schema={"type": "object", "properties": {}},
            ),
            Tool(
                name="cairn_surface_today",
                description=(
                    "Get everything relevant for today (calendar events, due items, priorities)."
                ),
                input_schema={"type": "object", "properties": {}},
            ),
            Tool(
                name="cairn_surface_next",
                description=(
                    "Get the next thing that needs attention based on priority, "
                    "due dates, and context."
                ),
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_items": {
                            "type": "number",
                            "description": "Max items to surface (default: 5)",
                        },
                    },
                },
            ),
            # --- Play CRUD Tools (Acts, Scenes management) ---
            Tool(
                name="cairn_list_acts",
                description="List all Acts in The Play. Shows the organizational structure.",
                input_schema={"type": "object", "properties": {}},
            ),
            Tool(
                name="cairn_create_act",
                description="Create a new Act in The Play. An Act is a major area of life/work.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title for the new Act"},
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="cairn_update_act",
                description="Update an Act's title. Use fuzzy matching for act_name.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act to update (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                        "new_title": {"type": "string", "description": "New title for the Act"},
                    },
                    "required": ["new_title"],
                },
            ),
            Tool(
                name="cairn_delete_act",
                description="Delete an Act and all its contents. Cannot delete 'Your Story' act.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act to delete (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_set_active_act",
                description="Set the active Act for the current session.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act to set active (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_list_scenes",
                description="List all Scenes in an Act.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                    },
                },
            ),
            Tool(
                name="cairn_create_scene",
                description="Create a new Scene in an Act.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                        "title": {"type": "string", "description": "Title for the new Scene"},
                    },
                    "required": ["title"],
                },
            ),
            Tool(
                name="cairn_update_scene",
                description="Update a Scene's title.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "scene_name": {
                            "type": "string",
                            "description": "Name of the Scene to update (fuzzy matched)",
                        },
                        "scene_id": {
                            "type": "string",
                            "description": "Scene ID (alternative to scene_name)",
                        },
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act containing the Scene",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                        "new_title": {"type": "string", "description": "New title for the Scene"},
                    },
                    "required": ["new_title"],
                },
            ),
            Tool(
                name="cairn_delete_scene",
                description="Delete a Scene. Cannot delete 'Stage Direction' scene.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "scene_name": {
                            "type": "string",
                            "description": "Name of the Scene to delete (fuzzy matched)",
                        },
                        "scene_id": {
                            "type": "string",
                            "description": "Scene ID (alternative to scene_name)",
                        },
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act containing the Scene",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                    },
                },
            ),
        ]
    )

    # =========================================================================
    # Play alias tools (cairn_play_* → same as cairn_list_*)
    # These names are used in agent tests and older prompt templates.
    # =========================================================================
    tools.extend(
        [
            Tool(
                name="cairn_play_acts_list",
                description="List all Acts in The Play (alias for cairn_list_acts).",
                input_schema={"type": "object", "properties": {}},
            ),
            Tool(
                name="cairn_play_scenes_list",
                description="List Scenes in an Act (alias for cairn_list_scenes).",
                input_schema={
                    "type": "object",
                    "properties": {
                        "act_name": {
                            "type": "string",
                            "description": "Name of the Act (fuzzy matched)",
                        },
                        "act_id": {
                            "type": "string",
                            "description": "Act ID (alternative to act_name)",
                        },
                        "path": {
                            "type": "string",
                            "description": "Ignored (legacy argument from system tool era)",
                        },
                    },
                },
            ),
        ]
    )

    return tools


def call_tool(db: Database, *, name: str, arguments: dict[str, Any] | None) -> Any:
    """Dispatch tool calls to appropriate handlers.

    CAIRN tools delegate to CairnToolHandler.
    """
    args = arguments or {}

    # --- Play alias tools: remap to canonical cairn_list_* names ---
    _play_aliases = {
        "cairn_play_acts_list": "cairn_list_acts",
        "cairn_play_scenes_list": "cairn_list_scenes",
    }
    if name in _play_aliases:
        name = _play_aliases[name]

    # --- CAIRN Tools (Knowledge Management & Thunderbird Integration) ---
    if name.startswith("cairn_"):
        import logging

        from .cairn.mcp_tools import CairnToolError, CairnToolHandler
        from .cairn.store import CairnStore
        from .play_fs import play_root

        def get_current_play_path(db):
            """Get current play path, or None."""
            try:
                path = play_root()
                return str(path) if path.exists() else None
            except Exception as e:
                cairn_logger.debug("Failed to get play path: %s", e)
                return None

        cairn_logger = logging.getLogger("cairn.cairn")
        cairn_logger.info("CAIRN tool called: %s with args: %s", name, args)

        try:
            play_path = get_current_play_path(db)
            if not play_path:
                cairn_logger.warning("CAIRN tool %s failed: No Play path configured", name)
                return {
                    "error": "No Play path configured. Select or create an Act first.",
                    "tool": name,
                }

            store_path = Path(play_path) / ".cairn" / "cairn.db"
            store = CairnStore(store_path)

            # Get LLM for entity resolution (cheap local inference)
            from cairn.providers import get_provider

            try:
                llm = get_provider(db)
            except Exception as e:
                cairn_logger.warning(
                    "LLM provider unavailable, falling back to fuzzy match: %s", e
                )
                llm = None

            handler = CairnToolHandler(store=store, llm=llm)

            result = handler.call_tool(name, args)
            cairn_logger.info("CAIRN tool %s succeeded: %s", name, result)
            return result

        except CairnToolError as e:
            cairn_logger.error("CAIRN tool %s error: %s", name, e.message)
            return {"error": e.message, "code": e.code, "tool": name}
        except Exception as e:
            cairn_logger.exception("CAIRN tool %s unexpected error: %s", name, e)
            return {"error": str(e), "tool": name}

    raise ToolError(code="unknown_tool", message=f"Unknown tool: {name}")


def render_tool_result(result: Any) -> str:
    if result is None:
        return "null"
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False)
