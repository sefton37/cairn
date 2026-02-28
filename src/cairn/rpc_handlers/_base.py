"""Base utilities for RPC handlers.

Provides decorators and helpers for standardized error handling across
all RPC handler modules.
"""

from __future__ import annotations

import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from cairn.errors import (
    TalkingRockError,
    get_error_code,
    record_error,
)

from . import RpcError

if TYPE_CHECKING:
    from cairn.db import Database

logger = logging.getLogger(__name__)


def rpc_handler(method_name: str) -> Callable:
    """Decorator that converts domain errors to RpcError.

    Standardizes error handling for RPC handlers by:
    1. Propagating RpcError unchanged
    2. Converting TalkingRockError to structured RpcError
    3. Converting ValueError to parameter error (-32602)
    4. Logging and converting unexpected exceptions to internal error (-32603)

    Args:
        method_name: The RPC method name (e.g., "play/acts/create")

    Usage:
        @rpc_handler("play/acts/create")
        def handle_play_acts_create(db: Database, *, title: str) -> dict:
            act_id = create_act(title=title)
            return {"act_id": act_id}
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(db: "Database", **kwargs: Any) -> Any:
            try:
                return func(db, **kwargs)
            except RpcError:
                # Already an RPC error, propagate as-is
                raise
            except TalkingRockError as e:
                # Convert domain error to RPC error with structured data
                raise RpcError(
                    code=get_error_code(e),
                    message=e.message,
                    data=e.to_dict(),
                ) from e
            except ValueError as e:
                # Parameter validation errors
                raise RpcError(
                    code=-32602,
                    message=str(e),
                ) from e
            except TypeError as e:
                # Missing or wrong parameter type
                raise RpcError(
                    code=-32602,
                    message=f"Invalid parameter: {e}",
                ) from e
            except Exception as e:
                # Unexpected error - log and record for debugging
                logger.error(
                    "Internal error in RPC handler %s: %s",
                    method_name,
                    e,
                    exc_info=True,
                )
                record_error(
                    source="rpc",
                    operation=method_name,
                    exc=e,
                    db=db,
                    context={"kwargs_keys": list(kwargs.keys())},
                )
                raise RpcError(
                    code=-32603,
                    message=f"Internal error in {method_name}",
                    data={"error_type": type(e).__name__},
                ) from e

        return wrapper

    return decorator


def require_params(*required: str) -> Callable:
    """Decorator that validates required parameters are present.

    Args:
        *required: Names of required parameters

    Usage:
        @require_params("act_id", "title")
        @rpc_handler("play/acts/update")
        def handle_play_acts_update(db: Database, **kwargs) -> dict:
            ...

    Raises:
        RpcError: If any required parameter is missing
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            missing = [p for p in required if p not in kwargs or kwargs[p] is None]
            if missing:
                raise RpcError(
                    code=-32602,
                    message=f"Missing required parameters: {', '.join(missing)}",
                    data={"missing": missing},
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
