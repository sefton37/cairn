"""Command/tool registry: what the LLM can see and reason about."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Command:
    """A single command that the LLM can call."""

    name: str
    description: str
    parameters: dict[str, Any]  # JSON schema for parameters
    handler: Callable[[dict[str, Any]], str] | None = None  # Will be set at runtime


def get_command_registry() -> list[Command]:
    """Get the list of commands the LLM can reason about.

    This is sent to the LLM in the system prompt so it can decide which tools to use.
    """
    return [
        Command(
            name="reflect_recent",
            description=(
                "Summarize recent attention patterns "
                "(switches, focus, fragmentation). No parameters."
            ),
            parameters={},
        ),
        Command(
            name="inspect_session",
            description=(
                "Get details about a recent work session "
                "(folder, duration, events)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "hours_back": {
                        "type": "number",
                        "description": "How many hours back to look",
                    }
                },
            },
        ),
        Command(
            name="list_events",
            description=(
                "List recent events from the event log "
                "(editor activity, saves, notes)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "number",
                        "description": "How many events to show (default 20)",
                    }
                },
            },
        ),
        Command(
            name="note",
            description="Store a note or observation in the audit log.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string", "description": "The note to store"}},
                "required": ["text"],
            },
        ),
    ]


def registry_as_json_schema() -> dict[str, Any]:
    """Serialize the command registry as a JSON schema for the LLM."""
    commands = get_command_registry()
    return {
        "type": "object",
        "description": (
            "Available commands you can call to reason about the "
            "user's attention and projects."
        ),
        "commands": [
            {
                "name": cmd.name,
                "description": cmd.description,
                "parameters": cmd.parameters,
            }
            for cmd in commands
        ],
    }
