"""Tests for RPC handler base utilities.

Tests the rpc_handler and require_params decorators.
"""

from __future__ import annotations

import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from cairn.db import Database
from cairn.errors import (
    TalkingRockError,
    ValidationError,
    NotFoundError,
    get_error_code,
)
from cairn.rpc_handlers import RpcError
from cairn.rpc_handlers._base import rpc_handler, require_params


@pytest.fixture
def temp_db() -> Iterator[Database]:
    """Create a temporary database for tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db = Database(db_path=Path(tmpdir) / "test.db")
        db.migrate()
        yield db
        db.close()


class TestRpcHandlerDecorator:
    """Tests for the @rpc_handler decorator."""

    def test_returns_result_on_success(self, temp_db: Database) -> None:
        """Handler returns result on successful execution."""

        @rpc_handler("test/method")
        def handler(db: Database, *, name: str) -> dict[str, Any]:
            return {"greeting": f"Hello, {name}!"}

        result = handler(temp_db, name="World")
        assert result == {"greeting": "Hello, World!"}

    def test_propagates_rpc_error_unchanged(self, temp_db: Database) -> None:
        """RpcError is propagated without modification."""

        @rpc_handler("test/method")
        def handler(db: Database) -> dict:
            raise RpcError(code=-32600, message="Invalid Request")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert exc_info.value.code == -32600
        assert exc_info.value.message == "Invalid Request"

    def test_converts_talking_rock_error(self, temp_db: Database) -> None:
        """TalkingRockError is converted to RpcError with correct code."""

        @rpc_handler("test/method")
        def handler(db: Database) -> dict:
            raise ValidationError("Invalid input", field="email")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert exc_info.value.code == get_error_code(ValidationError(""))
        assert exc_info.value.message == "Invalid input"
        assert exc_info.value.data["field"] == "email"

    def test_converts_value_error(self, temp_db: Database) -> None:
        """ValueError is converted to RpcError with -32602."""

        @rpc_handler("test/method")
        def handler(db: Database) -> dict:
            raise ValueError("act_id is required")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert exc_info.value.code == -32602
        assert "act_id is required" in exc_info.value.message

    def test_converts_type_error(self, temp_db: Database) -> None:
        """TypeError is converted to RpcError with -32602."""

        @rpc_handler("test/method")
        def handler(db: Database) -> dict:
            raise TypeError("expected str, got int")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert exc_info.value.code == -32602
        assert "Invalid parameter" in exc_info.value.message

    def test_converts_unexpected_error(self, temp_db: Database) -> None:
        """Unexpected exceptions become internal error -32603."""

        @rpc_handler("test/method")
        def handler(db: Database) -> dict:
            raise RuntimeError("Something unexpected")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert exc_info.value.code == -32603
        assert "Internal error" in exc_info.value.message
        assert exc_info.value.data["error_type"] == "RuntimeError"

    def test_includes_method_name_in_internal_error(self, temp_db: Database) -> None:
        """Internal error message includes the method name."""

        @rpc_handler("play/acts/create")
        def handler(db: Database) -> dict:
            raise RuntimeError("Oops")

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db)

        assert "play/acts/create" in exc_info.value.message

    def test_preserves_function_name(self, temp_db: Database) -> None:
        """Decorator preserves the original function name."""

        @rpc_handler("test/method")
        def my_handler(db: Database) -> dict:
            return {}

        assert my_handler.__name__ == "my_handler"


class TestRequireParamsDecorator:
    """Tests for the @require_params decorator."""

    def test_allows_valid_params(self, temp_db: Database) -> None:
        """Handler executes when required params are present."""

        @require_params("act_id", "title")
        @rpc_handler("test/method")
        def handler(db: Database, **kwargs: Any) -> dict:
            return {"act_id": kwargs["act_id"], "title": kwargs["title"]}

        result = handler(temp_db, act_id="act-1", title="My Act")
        assert result == {"act_id": "act-1", "title": "My Act"}

    def test_rejects_missing_params(self, temp_db: Database) -> None:
        """Handler raises RpcError when required params are missing."""

        @require_params("act_id", "title")
        @rpc_handler("test/method")
        def handler(db: Database, **kwargs: Any) -> dict:
            return {}

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db, act_id="act-1")  # Missing title

        assert exc_info.value.code == -32602
        assert "title" in exc_info.value.message
        assert exc_info.value.data["missing"] == ["title"]

    def test_rejects_none_values(self, temp_db: Database) -> None:
        """Handler treats None as missing parameter."""

        @require_params("act_id")
        @rpc_handler("test/method")
        def handler(db: Database, **kwargs: Any) -> dict:
            return {}

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db, act_id=None)

        assert exc_info.value.code == -32602
        assert "act_id" in exc_info.value.message

    def test_reports_multiple_missing(self, temp_db: Database) -> None:
        """Handler reports all missing parameters."""

        @require_params("act_id", "title", "notes")
        @rpc_handler("test/method")
        def handler(db: Database, **kwargs: Any) -> dict:
            return {}

        with pytest.raises(RpcError) as exc_info:
            handler(temp_db, title="Title")  # Missing act_id and notes

        assert exc_info.value.code == -32602
        assert set(exc_info.value.data["missing"]) == {"act_id", "notes"}


class TestDecoratorChaining:
    """Tests for combining decorators."""

    def test_require_params_with_rpc_handler(self, temp_db: Database) -> None:
        """Decorators work correctly when chained."""

        @require_params("name")
        @rpc_handler("test/greet")
        def greet(db: Database, **kwargs: Any) -> dict:
            return {"message": f"Hello, {kwargs['name']}!"}

        # Success case
        result = greet(temp_db, name="Alice")
        assert result == {"message": "Hello, Alice!"}

        # Missing param case
        with pytest.raises(RpcError) as exc_info:
            greet(temp_db)
        assert exc_info.value.code == -32602
