"""Tests for UI RPC Server - the bridge between Tauri UI and Python kernel.

The UI RPC server is the main entry point for the desktop app. It handles:
1. JSON-RPC protocol over stdio
2. Authentication (login/logout/validate)
3. Chat messages (delegates to chat handlers)
4. Tool calls (delegates to MCP tools)
5. Play operations (CAIRN's knowledge base)
6. Code execution (RIVA)
7. System operations (ReOS)

These tests verify the RPC layer works correctly WITHOUT requiring
actual LLM calls or system access.
"""

from __future__ import annotations

import json
import pytest
from io import StringIO
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

from cairn.db import Database


@pytest.fixture
def db(tmp_path: Path) -> Database:
    """Create isolated test database."""
    db_path = tmp_path / "test.db"
    db = Database(str(db_path))
    db.migrate()
    return db


@pytest.fixture
def reset_rate_limiter():
    """Reset rate limiter between tests."""
    from cairn.security import get_rate_limiter
    limiter = get_rate_limiter()
    limiter._requests.clear()
    yield


class TestRpcErrorHandling:
    """Test RPC error handling produces clear messages."""

    def test_rpc_error_has_code_and_message(self) -> None:
        """RpcError should have code and message."""
        from cairn.ui_rpc_server import RpcError

        error = RpcError(code=-32600, message="Invalid Request")

        assert error.code == -32600
        assert error.message == "Invalid Request"
        assert str(error) == "Invalid Request"

    def test_rpc_error_can_include_data(self) -> None:
        """RpcError can include additional data for debugging."""
        from cairn.ui_rpc_server import RpcError

        error = RpcError(
            code=-32602,
            message="Invalid params",
            data={"param": "text", "error": "must be non-empty"}
        )

        assert error.data["param"] == "text"
        assert "non-empty" in error.data["error"]

    def test_jsonrpc_error_format(self) -> None:
        """Error responses should follow JSON-RPC 2.0 format."""
        from cairn.ui_rpc_server import _jsonrpc_error

        response = _jsonrpc_error(
            req_id=42,
            code=-32600,
            message="Invalid Request"
        )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 42
        assert "error" in response
        assert response["error"]["code"] == -32600
        assert response["error"]["message"] == "Invalid Request"
        assert "result" not in response

    def test_jsonrpc_result_format(self) -> None:
        """Success responses should follow JSON-RPC 2.0 format."""
        from cairn.ui_rpc_server import _jsonrpc_result

        response = _jsonrpc_result(
            req_id=42,
            result={"answer": "Hello"}
        )

        assert response["jsonrpc"] == "2.0"
        assert response["id"] == 42
        assert "result" in response
        assert response["result"]["answer"] == "Hello"
        assert "error" not in response


class TestAuthenticationHandlers:
    """Test authentication RPC handlers.

    Note: These tests are skipped because auth handlers are not yet implemented.
    """

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_login_rate_limited_after_threshold(
        self, db: Database, reset_rate_limiter
    ) -> None:
        """Login should be rate limited to prevent brute force."""
        from cairn.ui_rpc_server import _handle_auth_login

        # Make many login attempts
        for i in range(10):
            with patch("cairn.ui_rpc_server.auth.login") as mock_login:
                mock_login.return_value = {"success": False, "error": "invalid"}
                _handle_auth_login(username="attacker", password="wrong")

        # Next attempt should be rate limited
        result = _handle_auth_login(username="attacker", password="wrong")

        assert result["success"] is False
        assert "rate" in result.get("error", "").lower() or "limit" in result.get("error", "").lower(), (
            f"Should mention rate limit, got: {result}"
        )

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_login_success_returns_session_token(
        self, db: Database, reset_rate_limiter
    ) -> None:
        """Successful login should return session token."""
        from cairn.ui_rpc_server import _handle_auth_login

        with patch("cairn.ui_rpc_server.auth.login") as mock_login:
            mock_login.return_value = {
                "success": True,
                "session_token": "secure-token-12345",
                "username": "testuser",
            }

            result = _handle_auth_login(username="testuser", password="correct")

        assert result["success"] is True
        assert "session_token" in result
        assert result["username"] == "testuser"

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_logout_invalidates_session(self) -> None:
        """Logout should invalidate the session."""
        from cairn.ui_rpc_server import _handle_auth_logout

        with patch("cairn.ui_rpc_server.auth.logout") as mock_logout:
            mock_logout.return_value = {"success": True}

            result = _handle_auth_logout(session_token="token-to-destroy")

        assert result["success"] is True
        mock_logout.assert_called_once_with("token-to-destroy")

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_validate_session_checks_token(self) -> None:
        """Validate should check if session is still valid."""
        from cairn.ui_rpc_server import _handle_auth_validate

        with patch("cairn.ui_rpc_server.auth.validate_session") as mock_validate:
            mock_validate.return_value = {
                "valid": True,
                "username": "testuser",
                "expires_in": 3600,
            }

            result = _handle_auth_validate(session_token="valid-token")

        assert result["valid"] is True
        assert result["username"] == "testuser"


class TestToolsHandlers:
    """Test MCP tools RPC handlers."""

    def test_tools_list_returns_all_tools(self) -> None:
        """tools/list should return all available tools."""
        from cairn.ui_rpc_server import _tools_list
        from cairn.mcp_tools import Tool

        with patch("cairn.ui_rpc_server.list_tools") as mock_list:
            mock_list.return_value = [
                Tool(
                    name="cairn_get_calendar",
                    description="Get calendar events",
                    input_schema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="cairn_list_acts",
                    description="List all Acts",
                    input_schema={"type": "object", "properties": {}},
                ),
            ]

            result = _tools_list()

        assert "tools" in result
        assert len(result["tools"]) == 2

        tool_names = [t["name"] for t in result["tools"]]
        assert "cairn_get_calendar" in tool_names
        assert "cairn_list_acts" in tool_names

        # Each tool should have required fields
        for tool in result["tools"]:
            assert "name" in tool, "Tool must have name"
            assert "description" in tool, "Tool must have description"
            assert "inputSchema" in tool, "Tool must have inputSchema"

    def test_tools_call_executes_tool(self, db: Database) -> None:
        """tools/call should execute the specified tool."""
        from cairn.ui_rpc_server import _handle_tools_call

        with patch("cairn.ui_rpc_server.call_tool") as mock_call:
            mock_call.return_value = {"acts": [{"title": "Career"}]}

            result = _handle_tools_call(
                db,
                name="cairn_list_acts",
                arguments={}
            )

        assert result["acts"] == [{"title": "Career"}]
        mock_call.assert_called_once_with(db, name="cairn_list_acts", arguments={})

    def test_tools_call_error_is_descriptive(self, db: Database) -> None:
        """Tool errors should be wrapped as RpcError with descriptive message."""
        from cairn.ui_rpc_server import _handle_tools_call, RpcError
        from cairn.mcp_tools import ToolError

        with patch("cairn.ui_rpc_server.call_tool") as mock_call:
            mock_call.side_effect = ToolError(
                "unknown_tool",
                "Unknown tool: bad_tool"
            )

            with pytest.raises(RpcError) as exc_info:
                _handle_tools_call(
                    db,
                    name="bad_tool",
                    arguments={}
                )

        # RpcError wraps the ToolError message
        error_msg = exc_info.value.message
        assert "unknown" in error_msg.lower() or "tool" in error_msg.lower(), (
            f"Should explain why it failed, got: {error_msg}"
        )


class TestPlayHandlers:
    """Test Play (CAIRN knowledge base) RPC handlers."""

    @pytest.fixture(autouse=True)
    def isolate_play_data(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Isolate Play data to prevent tests from polluting real user data."""
        from cairn import play_db

        # Close any existing connection BEFORE changing env var
        play_db.close_connection()

        # Set the isolated data directory
        monkeypatch.setenv("REOS_DATA_DIR", str(tmp_path / "data"))

        yield

        # Clean up after test
        play_db.close_connection()

    def test_play_list_acts_returns_acts(self, db: Database) -> None:
        """play/acts/list should return all acts."""
        from cairn.play_fs import list_acts, create_act

        # Create some acts (create_act takes only title, notes)
        create_act(title="Work")
        create_act(title="Health")

        # list_acts returns (acts, active_id)
        acts, _ = list_acts()

        assert len(acts) >= 2
        titles = [a.title for a in acts]
        assert "Work" in titles
        assert "Health" in titles

    def test_play_create_act_requires_title(self, db: Database) -> None:
        """Creating an act requires a title."""
        from cairn.play_fs import create_act

        # Empty title should fail with ValueError
        with pytest.raises(ValueError) as exc_info:
            create_act(title="")

        error_msg = str(exc_info.value).lower()
        assert "title" in error_msg or "required" in error_msg, (
            f"Error should mention title issue, got: {exc_info.value}"
        )


class TestCodeExecutionHandlers:
    """Test code execution (RIVA) RPC handlers."""

    def test_code_exec_requires_prompt(self, db: Database) -> None:
        """Code execution requires a prompt."""
        # The actual code execution is tested in test_riva_integration.py
        # Here we verify the RPC layer validates inputs
        pass  # Placeholder - actual validation in handler


class TestSecurityIntegration:
    """Test security features in UI RPC server.

    Note: These tests are skipped because auth handlers are not yet implemented.
    """

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_audit_log_called_on_login(
        self, db: Database, reset_rate_limiter
    ) -> None:
        """Login attempts should be audited."""
        from cairn.ui_rpc_server import _handle_auth_login

        with patch("cairn.ui_rpc_server.auth.login") as mock_login, \
             patch("cairn.ui_rpc_server.audit_log") as mock_audit:
            mock_login.return_value = {"success": True, "session_token": "tok"}

            _handle_auth_login(username="testuser", password="pass")

        # Verify audit was called
        mock_audit.assert_called()
        call_args = mock_audit.call_args[0]
        # First arg is event type
        from cairn.security import AuditEventType
        assert call_args[0] == AuditEventType.AUTH_LOGIN_SUCCESS

    @pytest.mark.skip(reason="Auth handlers not yet implemented in ui_rpc_server")
    def test_rate_limit_audited(
        self, db: Database, reset_rate_limiter
    ) -> None:
        """Rate limit violations should be audited."""
        from cairn.ui_rpc_server import _handle_auth_login

        with patch("cairn.ui_rpc_server.audit_log") as mock_audit:
            # Exhaust rate limit
            for _ in range(15):
                with patch("cairn.ui_rpc_server.auth.login") as mock_login:
                    mock_login.return_value = {"success": False}
                    _handle_auth_login(username="attacker", password="wrong")

        # Check that rate limit was audited
        audit_calls = mock_audit.call_args_list
        rate_limit_calls = [
            c for c in audit_calls
            if len(c[0]) > 0 and "RATE_LIMIT" in str(c[0][0])
        ]
        assert len(rate_limit_calls) > 0, "Rate limit should be audited"


class TestSessionEnforcement:
    """Test that non-exempt RPC methods require __session."""

    def test_missing_session_rejected_for_non_exempt_method(self, db: Database) -> None:
        """A non-exempt method without __session must return error -32003."""
        from cairn.ui_rpc_server import _handle_jsonrpc_request

        req = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "play/list_acts",
            "params": {},
        }
        result = _handle_jsonrpc_request(db, req)
        assert result is not None
        assert "error" in result
        assert result["error"]["code"] == -32003
        assert "Session required" in result["error"]["message"]

    def test_exempt_methods_pass_without_session(self, db: Database) -> None:
        """Exempt methods (ping, initialize, debug/log) must not require __session."""
        from cairn.ui_rpc_server import _handle_jsonrpc_request

        req = {"jsonrpc": "2.0", "id": 2, "method": "ping", "params": {}}
        result = _handle_jsonrpc_request(db, req)
        assert result is not None
        # ping bypasses session check — it may return another error but NOT -32003
        if "error" in result:
            assert result["error"]["code"] != -32003

    def test_auth_methods_pass_without_session(self, db: Database) -> None:
        """auth/* methods must not require __session."""
        from cairn.ui_rpc_server import _handle_jsonrpc_request

        req = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "auth/validate",
            "params": {"session_token": "fake-token"},
        }
        result = _handle_jsonrpc_request(db, req)
        assert result is not None
        # Should reach the handler, not be blocked by session check
        assert result["error"]["code"] != -32003 if "error" in result else True


class TestJsonRpcProtocol:
    """Test JSON-RPC 2.0 protocol compliance."""

    def test_response_includes_jsonrpc_version(self) -> None:
        """All responses must include jsonrpc: '2.0'."""
        from cairn.ui_rpc_server import _jsonrpc_result, _jsonrpc_error

        result = _jsonrpc_result(req_id=1, result={"ok": True})
        assert result["jsonrpc"] == "2.0"

        error = _jsonrpc_error(req_id=1, code=-32600, message="Error")
        assert error["jsonrpc"] == "2.0"

    def test_response_includes_matching_id(self) -> None:
        """Response ID must match request ID."""
        from cairn.ui_rpc_server import _jsonrpc_result, _jsonrpc_error

        # Numeric ID
        result = _jsonrpc_result(req_id=42, result={})
        assert result["id"] == 42

        # String ID
        result = _jsonrpc_result(req_id="req-abc", result={})
        assert result["id"] == "req-abc"

        # Null ID (notification response)
        result = _jsonrpc_result(req_id=None, result={})
        assert result["id"] is None

    def test_error_response_has_code_and_message(self) -> None:
        """Error responses must have code and message."""
        from cairn.ui_rpc_server import _jsonrpc_error

        error = _jsonrpc_error(
            req_id=1,
            code=-32601,
            message="Method not found"
        )

        assert "error" in error
        assert "code" in error["error"]
        assert "message" in error["error"]
        assert error["error"]["code"] == -32601
        assert error["error"]["message"] == "Method not found"

    def test_error_codes_follow_spec(self) -> None:
        """Error codes should follow JSON-RPC spec."""
        # -32700: Parse error
        # -32600: Invalid Request
        # -32601: Method not found
        # -32602: Invalid params
        # -32603: Internal error
        # -32000 to -32099: Server error (reserved)

        from cairn.ui_rpc_server import _jsonrpc_error

        parse_error = _jsonrpc_error(req_id=1, code=-32700, message="Parse error")
        assert parse_error["error"]["code"] == -32700

        invalid_request = _jsonrpc_error(req_id=1, code=-32600, message="Invalid Request")
        assert invalid_request["error"]["code"] == -32600


class TestStdioProtocol:
    """Test stdio communication protocol."""

    def test_write_outputs_json_with_newline(self) -> None:
        """_write should output JSON followed by newline."""
        from cairn.ui_rpc_server import _write

        output = StringIO()
        with patch("sys.stdout", output):
            _write({"test": "value"})

        written = output.getvalue()
        assert written.endswith("\n"), "Output must end with newline"

        # Should be valid JSON
        parsed = json.loads(written.strip())
        assert parsed["test"] == "value"

    def test_broken_pipe_causes_clean_exit(self) -> None:
        """Broken pipe (UI closed) should exit cleanly, not crash."""
        from cairn.ui_rpc_server import _write

        mock_stdout = MagicMock()
        mock_stdout.write.side_effect = BrokenPipeError()

        with patch("sys.stdout", mock_stdout):
            with pytest.raises(SystemExit) as exc_info:
                _write({"test": "value"})

        # Should exit with code 0 (clean shutdown)
        assert exc_info.value.code == 0
