"""RPC module for Talking Rock.

JSON-RPC 2.0 types and utilities for ui_rpc_server.py.
"""

from __future__ import annotations

from cairn.rpc.types import (
    JSON,
    RpcError,
    PARSE_ERROR,
    INVALID_REQUEST,
    METHOD_NOT_FOUND,
    INVALID_PARAMS,
    INTERNAL_ERROR,
    VALIDATION_ERROR,
    RATE_LIMIT_ERROR,
    AUTH_ERROR,
    NOT_FOUND_ERROR,
    SAFETY_ERROR,
    jsonrpc_error,
    jsonrpc_result,
    readline,
    write,
)

__all__ = [
    # Types
    "JSON",
    "RpcError",
    # Error codes
    "PARSE_ERROR",
    "INVALID_REQUEST",
    "METHOD_NOT_FOUND",
    "INVALID_PARAMS",
    "INTERNAL_ERROR",
    "VALIDATION_ERROR",
    "RATE_LIMIT_ERROR",
    "AUTH_ERROR",
    "NOT_FOUND_ERROR",
    "SAFETY_ERROR",
    # Utilities
    "jsonrpc_error",
    "jsonrpc_result",
    "readline",
    "write",
]
