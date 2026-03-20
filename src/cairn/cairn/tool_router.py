"""Per-domain LLM tool router for CAIRN.

Maps domains to focused tool catalogs and uses the LLM to select the right
tool from a small, domain-scoped set (3-8 tools). This replaces broad
tool selection with targeted routing that keeps the model focused on
relevant options only.

The router caches results per (domain, user_input) hash within a single
request lifecycle. Call clear_router_cache() at the start of each request.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per-domain tool catalogs: tool_name → description used in the LLM prompt.
# Each domain has a default_tool that is selected when the LLM can't decide.
DOMAIN_TOOL_CATALOGS: dict[str, dict[str, str]] = {
    "surfacing": {
        "cairn_surface_next": (
            "Get the next thing needing attention based on deadlines and staleness. "
            "Use for: 'what should I work on', 'next thing', 'priorities', 'what's important'"
        ),
        "cairn_surface_today": (
            "Get everything relevant for today — calendar events and due items. "
            "Use for: 'what's today', 'today's plan', 'daily overview', 'good morning'"
        ),
        "cairn_surface_stale": (
            "Get items not touched in a while. "
            "Use for: 'what have I neglected', 'stale items', 'forgotten things'"
        ),
        "cairn_surface_attention": (
            "Get items needing attention — upcoming events, overdue items. "
            "Use for: 'what needs attention', 'anything urgent', 'morning brief'"
        ),
    },
    "tasks": {
        "cairn_get_todos": (
            "Get all tasks/todos from The Play. "
            "Use for: 'my tasks', 'todo list', 'what's on my plate'"
        ),
        "cairn_get_unchecked_todos": (
            "Get unchecked to-do items. "
            "Use for: 'open todos', 'what's not done', 'remaining tasks'"
        ),
        "cairn_touch_item": (
            "Mark an item as interacted with. "
            "Use for: 'I worked on X', 'mark X as viewed/completed'"
        ),
    },
    "play": {
        "cairn_list_acts": (
            "List all Acts in The Play. "
            "Use for: 'show my acts', 'what acts', 'life areas'"
        ),
        "cairn_create_act": (
            "Create a new Act. "
            "Use for: 'create act', 'new act', 'add act for X'"
        ),
        "cairn_update_act": (
            "Update an Act's title, notes, or color. "
            "Use for: 'rename act', 'change act color'"
        ),
        "cairn_delete_act": (
            "Delete an Act. "
            "Use for: 'delete act', 'remove act'"
        ),
        "cairn_set_active_act": (
            "Set which Act is currently active/in-focus. "
            "Use for: 'switch to X', 'focus on X act'"
        ),
        "cairn_list_scenes": (
            "List Scenes in an Act. "
            "Use for: 'scenes in X', 'what's in X act'"
        ),
        "cairn_create_scene": (
            "Create a new Scene. "
            "Use for: 'new scene', 'add scene to X'"
        ),
        "cairn_update_scene": (
            "Update or move a Scene. "
            "Use for: 'rename scene', 'move scene to X'"
        ),
        "cairn_delete_scene": (
            "Delete a Scene. "
            "Use for: 'delete scene', 'remove scene'"
        ),
    },
    "knowledge": {
        "cairn_list_items": (
            "List items in the knowledge base. "
            "Use for: 'show everything', 'my items', 'what do I have'"
        ),
        "cairn_get_item": (
            "Get full details for a specific item. "
            "Use for: 'details on X', 'tell me about item X'"
        ),
        "cairn_create_page": (
            "Create a new page/document. "
            "Use for: 'new page', 'create document'"
        ),
        "cairn_update_page": (
            "Update a page's title or icon. "
            "Use for: 'rename page', 'change page icon'"
        ),
        "cairn_list_pages": (
            "List pages in an act. "
            "Use for: 'my pages', 'what pages', 'documents in X'"
        ),
        "cairn_get_page_content": (
            "Read a page's content. "
            "Use for: 'show page X', 'read page'"
        ),
        "cairn_get_page_tree": (
            "Get page hierarchy. "
            "Use for: 'page structure', 'outline'"
        ),
        "cairn_export_page_markdown": (
            "Export page as markdown. "
            "Use for: 'export page', 'download as markdown'"
        ),
        "cairn_create_block": (
            "Add content block to a page. "
            "Use for: 'add paragraph', 'add heading', 'add todo item'"
        ),
        "cairn_update_block": (
            "Edit a content block. "
            "Use for: 'change that paragraph', 'edit block'"
        ),
        "cairn_search_blocks": (
            "Search text across all pages. "
            "Use for: 'find in notes', 'search for X'"
        ),
        "cairn_add_scene_block": (
            "Embed a scene reference in a page. "
            "Use for: 'link scene to page'"
        ),
    },
    "calendar": {
        "cairn_get_calendar": (
            "Get calendar events for a date range. "
            "Use for: 'calendar this week', 'schedule', 'what meetings'"
        ),
        "cairn_get_upcoming_events": (
            "Get events coming up soon. "
            "Use for: 'upcoming events', 'what's coming up', 'am I free'"
        ),
        "cairn_thunderbird_status": (
            "Check calendar integration status. "
            "Use for: 'is calendar connected', 'thunderbird status'"
        ),
    },
    "contacts": {
        "cairn_search_contacts": (
            "Search contacts by name, email, or org. "
            "Use for: 'find contact', 'who is X', 'contact info for X'"
        ),
    },
    "health": {
        "cairn_health_report": (
            "Run a system health check. "
            "Use for: 'health check', 'how am I doing', 'system health'"
        ),
        "cairn_acknowledge_health": (
            "Dismiss a health finding. "
            "Use for: 'dismiss finding', 'acknowledge', 'got it'"
        ),
        "cairn_health_history": (
            "Show health trends over time. "
            "Use for: 'health history', 'trends', 'how has health changed'"
        ),
    },
    "meta": {
        "cairn_undo_last": (
            "Undo the last reversible action. "
            "Use for: 'undo', 'revert', 'put it back'"
        ),
        "cairn_confirm_action": (
            "Confirm a pending action. "
            "Use for: 'yes', 'confirm', 'do it', 'go ahead'"
        ),
        "cairn_cancel_action": (
            "Cancel a pending action. "
            "Use for: 'no', 'cancel', 'never mind', 'don't'"
        ),
    },
    "personal": {
        "cairn_list_items": (
            "List knowledge base items to find personal info. "
            "Use for: 'what do you know about me', 'my goals'"
        ),
        "cairn_get_item": (
            "Get details on a specific item. "
            "Use for: 'tell me about X'"
        ),
    },
    "general": {
        "cairn_list_items": (
            "List items in the knowledge base. "
            "Use for: 'show me everything', 'what do I have'"
        ),
        "cairn_surface_next": (
            "Get what needs attention next. "
            "Use for: 'what should I do', 'what's important'"
        ),
        "cairn_surface_today": (
            "Get today's overview. "
            "Use for: 'what's happening today'"
        ),
        "cairn_get_calendar": (
            "Get calendar events. "
            "Use for: 'my schedule', 'calendar'"
        ),
        "cairn_get_todos": (
            "Get tasks. "
            "Use for: 'my tasks', 'todos'"
        ),
        "cairn_list_acts": (
            "List Acts in The Play. "
            "Use for: 'my acts', 'life areas'"
        ),
    },
}

# Default tool per domain — used when LLM fails or returns null
DOMAIN_DEFAULTS: dict[str, str] = {
    "surfacing": "cairn_surface_next",
    "tasks": "cairn_get_todos",
    "play": "cairn_list_acts",
    "knowledge": "cairn_list_items",
    "calendar": "cairn_get_calendar",
    "contacts": "cairn_search_contacts",
    "health": "cairn_health_report",
    "meta": "cairn_undo_last",
    "personal": "cairn_list_items",
    "general": "cairn_list_items",
}

# Cache: (domain, user_input) hash → (tool_name | None, args dict)
_ROUTER_CACHE: dict[int, tuple[str | None, dict[str, Any]]] = {}


def route_to_tool(
    domain: str,
    user_input: str,
    llm: Any,
    play_data: dict[str, Any] | None = None,
) -> tuple[str | None, dict[str, Any]]:
    """Route user input to the correct tool within a domain catalog.

    Uses the LLM to select from a small set of domain-specific tools.
    Results are cached per (domain, user_input) hash within a request
    lifecycle to avoid redundant LLM calls when both tool_selector and
    arg_extractor invoke this function for the same input.

    Args:
        domain: Classified domain (surfacing, play, calendar, etc.)
        user_input: The user's natural language request.
        llm: LLM provider with chat_json method.
        play_data: Optional Play context (acts, scenes). Reserved for future use.

    Returns:
        (tool_name, args) tuple. tool_name is None if no tool should be called.
    """
    cache_key = hash((domain, user_input))
    if cache_key in _ROUTER_CACHE:
        return _ROUTER_CACHE[cache_key]

    catalog = DOMAIN_TOOL_CATALOGS.get(domain)
    if not catalog:
        result: tuple[str | None, dict[str, Any]] = (None, {})
        _ROUTER_CACHE[cache_key] = result
        return result

    default_tool = DOMAIN_DEFAULTS.get(domain)

    # Single-tool domains don't need an LLM call
    if len(catalog) == 1:
        tool_name = next(iter(catalog))
        result = (tool_name, {})
        _ROUTER_CACHE[cache_key] = result
        return result

    tool_list = "\n".join(f"- {name}: {desc}" for name, desc in catalog.items())

    system = f"""You MUST select a tool for this user request. One of these tools is the right choice.

Tools:
{tool_list}

Return ONLY a JSON object:
{{"tool": "tool_name_here", "reasoning": "one line why"}}

RULES:
- You MUST pick exactly one tool. Do NOT return null.
- Pick the tool whose description best matches the user's words.
- If uncertain, pick the most general/safe tool in the list.
- The tool name must be EXACTLY one of the names listed above."""

    user_msg = f'User request: "{user_input}"'

    try:
        raw = llm.chat_json(system=system, user=user_msg, temperature=0.0, top_p=0.9)
        data = json.loads(raw)

        tool_name = data.get("tool")
        if not tool_name or tool_name not in catalog:
            # LLM returned null or hallucinated — use domain default
            logger.debug(
                "Tool router: LLM returned '%s' for domain '%s', using default '%s'",
                tool_name, domain, default_tool,
            )
            tool_name = default_tool

        result = (tool_name, data.get("args", {})) if tool_name else (None, {})
        _ROUTER_CACHE[cache_key] = result
        return result

    except (json.JSONDecodeError, Exception) as e:
        logger.warning("Tool router failed for domain '%s': %s — using default", domain, e)
        result = (default_tool, {}) if default_tool else (None, {})
        _ROUTER_CACHE[cache_key] = result
        return result


def clear_router_cache() -> None:
    """Clear the router cache. Call at the start of each request."""
    _ROUTER_CACHE.clear()
