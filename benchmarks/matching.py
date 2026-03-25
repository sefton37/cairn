"""Scoring functions for Cairn benchmark results.

Four scoring dimensions:
    tool_match       — did the model select the correct tool?
    args_match       — did the arguments satisfy the expected schema?
    execution_success — did the tool call succeed without error?
    response_quality — heuristic quality label for the response text
"""

from __future__ import annotations

import json
from typing import Any


def tool_match(actual: str | None, expected: str) -> int:
    """1 if the tool selected matches the expected tool exactly.

    For 'none' expected (off-topic cases), actual must be None.
    """
    if expected == "none":
        return 1 if actual is None else 0
    return 1 if actual == expected else 0


def args_match(actual_args: dict | str | None, expected_schema: dict | str | None) -> int:
    """1 if actual args satisfy expected_args_schema.

    - If expected_schema is None, always returns 1 (no constraint).
    - If actual_args is None but schema requires fields, returns 0.
    - Uses jsonschema.validate() if available, otherwise checks required keys.
    """
    if expected_schema is None:
        return 1

    # Parse JSON strings
    schema = json.loads(expected_schema) if isinstance(expected_schema, str) else expected_schema
    args = json.loads(actual_args) if isinstance(actual_args, str) else actual_args

    if schema is None:
        return 1
    if args is None:
        return 0

    # Try jsonschema if available
    try:
        import jsonschema

        jsonschema.validate(instance=args, schema=schema)
        return 1
    except ImportError:
        pass
    except Exception:
        return 0

    # Fallback: check required keys are present
    required = schema.get("required", [])
    for key in required:
        if key not in args:
            return 0
    return 1


def execution_success(tool_execution_ok: int | None, tool_error: str | None) -> int:
    """1 if tool ran and produced no error."""
    return 1 if tool_execution_ok == 1 and not tool_error else 0


def response_quality_heuristic(response_text: str | None, expected_tool: str) -> str:
    """Heuristic quality label: 'good' | 'partial' | 'wrong'.

    Simple checks:
    - 'wrong' if response is None or empty
    - 'wrong' if response contains known error patterns
    - 'partial' if response is very short (< 20 chars) for non-off-topic
    - 'good' otherwise
    """
    if not response_text or not response_text.strip():
        return "wrong"

    text_lower = response_text.lower()
    error_patterns = ["error:", "failed", "unknown tool", "exception", "traceback"]
    for pattern in error_patterns:
        if pattern in text_lower:
            return "wrong"

    if expected_tool != "none" and len(response_text.strip()) < 20:
        return "partial"

    return "good"


def score_result(
    tool_selected: str | None,
    tool_args: dict | str | None,
    tool_execution_ok: int | None,
    tool_error: str | None,
    response_text: str | None,
    expected_tool: str,
    expected_args_schema: dict | str | None,
) -> dict[str, Any]:
    """Compute all scoring dimensions for a single result.

    Returns dict with tool_match, args_match, execution_success, response_quality.
    """
    tm = tool_match(tool_selected, expected_tool)

    # For off-topic (expected_tool="none"), correct behavior is no tool call
    if expected_tool == "none":
        am = 1 if tm == 1 else 0
        es = 1 if tm == 1 else 0
    else:
        am = args_match(tool_args, expected_args_schema) if tm == 1 else 0
        es = execution_success(tool_execution_ok, tool_error) if tm == 1 else 0

    rq = response_quality_heuristic(response_text, expected_tool)

    return {
        "tool_match": tm,
        "args_match": am,
        "execution_success": es,
        "response_quality": rq,
    }
