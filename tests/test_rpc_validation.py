"""Tests for the rpc_validation module."""

from __future__ import annotations

import pytest

from reos.rpc_validation import (
    ERROR_INVALID_PARAMS,
    MAX_ID_LENGTH,
    MAX_TITLE_LENGTH,
    RpcError,
    jsonrpc_error,
    jsonrpc_result,
    validate_optional_int,
    validate_optional_string,
    validate_params_object,
    validate_required_int,
    validate_required_string,
    validate_string_length,
)


class TestRpcError:
    def test_rpc_error_attributes(self) -> None:
        err = RpcError(code=-32602, message="test error", data={"key": "value"})
        assert err.code == -32602
        assert err.message == "test error"
        assert err.data == {"key": "value"}
        assert str(err) == "test error"

    def test_rpc_error_without_data(self) -> None:
        err = RpcError(code=-32601, message="Method not found")
        assert err.code == -32601
        assert err.message == "Method not found"
        assert err.data is None


class TestValidateStringLength:
    def test_valid_length(self) -> None:
        # Should not raise
        validate_string_length("hello", 10, "field")

    def test_exact_length(self) -> None:
        # Should not raise
        validate_string_length("hello", 5, "field")

    def test_exceeds_length(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_string_length("hello world", 5, "field")
        assert exc_info.value.code == ERROR_INVALID_PARAMS
        assert "maximum length" in exc_info.value.message


class TestValidateRequiredString:
    def test_valid_string(self) -> None:
        result = validate_required_string({"key": "value"}, "key", 100)
        assert result == "value"

    def test_missing_key(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_string({}, "key", 100)
        assert exc_info.value.code == ERROR_INVALID_PARAMS
        assert "required" in exc_info.value.message

    def test_empty_string_rejected(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_string({"key": "  "}, "key", 100)
        assert "required" in exc_info.value.message

    def test_empty_string_allowed(self) -> None:
        result = validate_required_string({"key": ""}, "key", 100, allow_empty=True)
        assert result == ""

    def test_exceeds_max_length(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_string({"key": "x" * 200}, "key", 100)
        assert "maximum length" in exc_info.value.message

    def test_not_a_string(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_string({"key": 123}, "key", 100)
        assert "required" in exc_info.value.message


class TestValidateOptionalString:
    def test_valid_string(self) -> None:
        result = validate_optional_string({"key": "value"}, "key", 100)
        assert result == "value"

    def test_missing_key_returns_none(self) -> None:
        result = validate_optional_string({}, "key", 100)
        assert result is None

    def test_missing_key_returns_default(self) -> None:
        result = validate_optional_string({}, "key", 100, default="default")
        assert result == "default"

    def test_explicit_none(self) -> None:
        result = validate_optional_string({"key": None}, "key", 100)
        assert result is None

    def test_not_a_string(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_optional_string({"key": 123}, "key", 100)
        assert "must be a string or null" in exc_info.value.message

    def test_exceeds_max_length(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_optional_string({"key": "x" * 200}, "key", 100)
        assert "maximum length" in exc_info.value.message


class TestValidateRequiredInt:
    def test_valid_int(self) -> None:
        result = validate_required_int({"count": 5}, "count")
        assert result == 5

    def test_missing_key(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_int({}, "count")
        assert "must be an integer" in exc_info.value.message

    def test_not_an_int(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_int({"count": "5"}, "count")
        assert "must be an integer" in exc_info.value.message

    def test_boolean_rejected(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_required_int({"count": True}, "count")
        assert "must be an integer" in exc_info.value.message

    def test_min_value(self) -> None:
        result = validate_required_int({"count": 5}, "count", min_value=1)
        assert result == 5

        with pytest.raises(RpcError) as exc_info:
            validate_required_int({"count": 0}, "count", min_value=1)
        assert "at least" in exc_info.value.message

    def test_max_value(self) -> None:
        result = validate_required_int({"count": 5}, "count", max_value=10)
        assert result == 5

        with pytest.raises(RpcError) as exc_info:
            validate_required_int({"count": 11}, "count", max_value=10)
        assert "at most" in exc_info.value.message


class TestValidateOptionalInt:
    def test_valid_int(self) -> None:
        result = validate_optional_int({"count": 5}, "count")
        assert result == 5

    def test_missing_key_returns_none(self) -> None:
        result = validate_optional_int({}, "count")
        assert result is None

    def test_missing_key_returns_default(self) -> None:
        result = validate_optional_int({}, "count", default=10)
        assert result == 10

    def test_explicit_none(self) -> None:
        result = validate_optional_int({"count": None}, "count")
        assert result is None

    def test_not_an_int(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_optional_int({"count": "5"}, "count")
        assert "must be an integer or null" in exc_info.value.message


class TestValidateParamsObject:
    def test_valid_dict(self) -> None:
        result = validate_params_object({"key": "value"})
        assert result == {"key": "value"}

    def test_not_a_dict(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_params_object("not a dict")
        assert "params must be an object" in exc_info.value.message

    def test_list_rejected(self) -> None:
        with pytest.raises(RpcError) as exc_info:
            validate_params_object([1, 2, 3])
        assert "params must be an object" in exc_info.value.message


class TestJsonRpcResponses:
    def test_jsonrpc_result(self) -> None:
        result = jsonrpc_result(req_id=1, result={"data": "value"})
        assert result == {
            "jsonrpc": "2.0",
            "id": 1,
            "result": {"data": "value"},
        }

    def test_jsonrpc_result_with_string_id(self) -> None:
        result = jsonrpc_result(req_id="abc-123", result="ok")
        assert result["id"] == "abc-123"
        assert result["result"] == "ok"

    def test_jsonrpc_error(self) -> None:
        result = jsonrpc_error(req_id=1, code=-32602, message="Invalid params")
        assert result == {
            "jsonrpc": "2.0",
            "id": 1,
            "error": {"code": -32602, "message": "Invalid params"},
        }

    def test_jsonrpc_error_with_data(self) -> None:
        result = jsonrpc_error(
            req_id=1, code=-32000, message="Server error", data={"detail": "error"}
        )
        assert result["error"]["data"] == {"detail": "error"}

    def test_jsonrpc_error_null_id(self) -> None:
        result = jsonrpc_error(req_id=None, code=-32700, message="Parse error")
        assert result["id"] is None


class TestConstants:
    def test_constants_have_reasonable_values(self) -> None:
        assert MAX_TITLE_LENGTH > 0
        assert MAX_ID_LENGTH > 0
        assert MAX_TITLE_LENGTH < 1000  # Titles shouldn't be huge
        assert MAX_ID_LENGTH < 500  # IDs shouldn't be huge
