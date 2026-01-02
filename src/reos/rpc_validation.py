"""Shared JSON-RPC validation utilities.

This module provides reusable validation helpers for JSON-RPC 2.0 servers.
It follows the JSON-RPC 2.0 error code conventions:
- -32700: Parse error
- -32600: Invalid Request
- -32601: Method not found
- -32602: Invalid params
- -32603: Internal error
- -32000 to -32099: Server error (reserved for implementation-defined server-errors)
"""

from __future__ import annotations

from typing import Any

# Type alias for JSON objects
JSON = dict[str, Any]

# Input validation limits to prevent resource exhaustion
MAX_TITLE_LENGTH = 500
MAX_NOTES_LENGTH = 50_000  # 50KB
MAX_TEXT_LENGTH = 500_000  # 500KB for KB files
MAX_PATH_LENGTH = 1000
MAX_ID_LENGTH = 200
MAX_SYSTEM_PROMPT_LENGTH = 100_000  # 100KB
MAX_LIST_LIMIT = 10_000

# JSON-RPC 2.0 error codes
ERROR_PARSE = -32700
ERROR_INVALID_REQUEST = -32600
ERROR_METHOD_NOT_FOUND = -32601
ERROR_INVALID_PARAMS = -32602
ERROR_INTERNAL = -32603
ERROR_SERVER_BASE = -32000  # Base for server-defined errors


class RpcError(RuntimeError):
    """JSON-RPC 2.0 error with code and optional data."""

    def __init__(self, code: int, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


def validate_string_length(value: str, max_length: int, field_name: str) -> None:
    """Validate that a string doesn't exceed the maximum length.

    Raises:
        RpcError: If the string exceeds max_length.
    """
    if len(value) > max_length:
        raise RpcError(
            code=ERROR_INVALID_PARAMS,
            message=f"{field_name} exceeds maximum length of {max_length} characters",
        )


def validate_required_string(
    params: dict[str, Any], key: str, max_length: int, *, allow_empty: bool = False
) -> str:
    """Extract and validate a required string parameter.

    Args:
        params: The parameters dict to extract from.
        key: The parameter key.
        max_length: Maximum allowed string length.
        allow_empty: If True, empty strings are allowed.

    Returns:
        The validated string value.

    Raises:
        RpcError: If the value is missing, not a string, or exceeds max_length.
    """
    value = params.get(key)
    if not isinstance(value, str):
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} is required")
    if not allow_empty and not value.strip():
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} is required")
    validate_string_length(value, max_length, key)
    return value


def validate_optional_string(
    params: dict[str, Any], key: str, max_length: int, *, default: str | None = None
) -> str | None:
    """Extract and validate an optional string parameter.

    Args:
        params: The parameters dict to extract from.
        key: The parameter key.
        max_length: Maximum allowed string length.
        default: Default value if key is not present.

    Returns:
        The validated string value, or None/default if not provided.

    Raises:
        RpcError: If the value is not a string (when provided) or exceeds max_length.
    """
    value = params.get(key, default)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be a string or null")
    validate_string_length(value, max_length, key)
    return value


def validate_required_int(
    params: dict[str, Any], key: str, *, min_value: int | None = None, max_value: int | None = None
) -> int:
    """Extract and validate a required integer parameter.

    Args:
        params: The parameters dict to extract from.
        key: The parameter key.
        min_value: Minimum allowed value (inclusive).
        max_value: Maximum allowed value (inclusive).

    Returns:
        The validated integer value.

    Raises:
        RpcError: If the value is missing, not an int, or out of bounds.
    """
    value = params.get(key)
    if not isinstance(value, int) or isinstance(value, bool):
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be an integer")
    if min_value is not None and value < min_value:
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be at least {min_value}")
    if max_value is not None and value > max_value:
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be at most {max_value}")
    return value


def validate_optional_int(
    params: dict[str, Any],
    key: str,
    *,
    default: int | None = None,
    min_value: int | None = None,
    max_value: int | None = None,
) -> int | None:
    """Extract and validate an optional integer parameter.

    Args:
        params: The parameters dict to extract from.
        key: The parameter key.
        default: Default value if key is not present.
        min_value: Minimum allowed value (inclusive).
        max_value: Maximum allowed value (inclusive).

    Returns:
        The validated integer value, or None/default if not provided.

    Raises:
        RpcError: If the value is not an int (when provided) or out of bounds.
    """
    value = params.get(key, default)
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be an integer or null")
    if min_value is not None and value < min_value:
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be at least {min_value}")
    if max_value is not None and value > max_value:
        raise RpcError(code=ERROR_INVALID_PARAMS, message=f"{key} must be at most {max_value}")
    return value


def validate_params_object(params: Any) -> dict[str, Any]:
    """Validate that params is an object (dict).

    Args:
        params: The params value to check.

    Returns:
        The params as a dict.

    Raises:
        RpcError: If params is not a dict.
    """
    if not isinstance(params, dict):
        raise RpcError(code=ERROR_INVALID_PARAMS, message="params must be an object")
    return params


def jsonrpc_error(*, req_id: Any, code: int, message: str, data: Any | None = None) -> JSON:
    """Create a JSON-RPC 2.0 error response.

    Args:
        req_id: The request ID (can be None for notifications).
        code: The error code.
        message: Human-readable error message.
        data: Optional additional error data.

    Returns:
        A JSON-RPC 2.0 error response dict.
    """
    err: JSON = {"code": code, "message": message}
    if data is not None:
        err["data"] = data
    return {"jsonrpc": "2.0", "id": req_id, "error": err}


def jsonrpc_result(*, req_id: Any, result: Any) -> JSON:
    """Create a JSON-RPC 2.0 success response.

    Args:
        req_id: The request ID.
        result: The result data.

    Returns:
        A JSON-RPC 2.0 success response dict.
    """
    return {"jsonrpc": "2.0", "id": req_id, "result": result}
