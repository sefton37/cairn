"""Unit tests for the riva/ RPC proxy handler.

Tests verify:
- Returns structured error when socket file does not exist
- Returns structured error when connection is refused
- Returns proxied response on successful socket communication
"""

from __future__ import annotations

import json
import struct
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


_RIVA_ERROR_CODE = -32099


# =============================================================================
# handle_riva_proxy
# =============================================================================


class TestHandleRivaProxy:
    """handle_riva_proxy forwards JSON-RPC calls to the RIVA Unix socket."""

    def test_returns_error_when_socket_file_does_not_exist(self) -> None:
        from cairn.rpc_handlers.riva import handle_riva_proxy

        with patch("cairn.rpc_handlers.riva._get_socket_path") as mock_path:
            mock_path.return_value = Path("/nonexistent/riva.sock")

            result = handle_riva_proxy(method="riva/ping", params={}, req_id=1)

        assert result["error"]["code"] == _RIVA_ERROR_CODE
        assert "not running" in result["error"]["message"]
        assert result["id"] == 1

    def test_returns_error_when_connection_refused(self) -> None:
        from cairn.rpc_handlers.riva import handle_riva_proxy

        mock_socket_path = MagicMock(spec=Path)
        mock_socket_path.exists.return_value = True

        with (
            patch("cairn.rpc_handlers.riva._get_socket_path", return_value=mock_socket_path),
            patch("socket.socket") as mock_sock_class,
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = ConnectionRefusedError("refused")
            mock_sock_class.return_value = mock_sock

            result = handle_riva_proxy(method="riva/ping", params={}, req_id=2)

        assert result["error"]["code"] == _RIVA_ERROR_CODE
        assert result["id"] == 2

    def test_returns_proxied_response_on_success(self) -> None:
        from cairn.rpc_handlers.riva import handle_riva_proxy

        fake_response = {"jsonrpc": "2.0", "id": 3, "result": {"pong": True}}
        fake_response_bytes = json.dumps(fake_response).encode("utf-8")
        length_prefix = struct.pack("!I", len(fake_response_bytes))

        mock_socket_path = MagicMock(spec=Path)
        mock_socket_path.exists.return_value = True
        mock_socket_path.__str__ = lambda self: "/home/user/.talkingrock/riva.sock"

        with (
            patch("cairn.rpc_handlers.riva._get_socket_path", return_value=mock_socket_path),
            patch("socket.socket") as mock_sock_class,
            patch(
                "cairn.rpc_handlers.riva._recv_exactly",
                side_effect=[length_prefix, fake_response_bytes],
            ),
        ):
            mock_sock = MagicMock()
            mock_sock_class.return_value = mock_sock

            result = handle_riva_proxy(method="riva/ping", params={}, req_id=3)

        assert result["result"]["pong"] is True
        assert result["id"] == 3

    def test_returns_error_when_general_exception_occurs(self) -> None:
        from cairn.rpc_handlers.riva import handle_riva_proxy

        mock_socket_path = MagicMock(spec=Path)
        mock_socket_path.exists.return_value = True

        with (
            patch("cairn.rpc_handlers.riva._get_socket_path", return_value=mock_socket_path),
            patch("socket.socket") as mock_sock_class,
        ):
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("unexpected OS error")
            mock_sock_class.return_value = mock_sock

            result = handle_riva_proxy(method="riva/action", params={"x": 1}, req_id=4)

        assert result["error"]["code"] == _RIVA_ERROR_CODE
        assert "proxy error" in result["error"]["message"]

    def test_forwards_method_and_params_in_request(self) -> None:
        from cairn.rpc_handlers.riva import handle_riva_proxy

        sent_data: list[bytes] = []

        fake_response = {"jsonrpc": "2.0", "id": 5, "result": {}}
        fake_response_bytes = json.dumps(fake_response).encode("utf-8")
        length_prefix = struct.pack("!I", len(fake_response_bytes))

        mock_socket_path = MagicMock(spec=Path)
        mock_socket_path.exists.return_value = True
        mock_socket_path.__str__ = lambda self: "/tmp/riva.sock"

        with (
            patch("cairn.rpc_handlers.riva._get_socket_path", return_value=mock_socket_path),
            patch("socket.socket") as mock_sock_class,
            patch(
                "cairn.rpc_handlers.riva._recv_exactly",
                side_effect=[length_prefix, fake_response_bytes],
            ),
        ):
            mock_sock = MagicMock()
            mock_sock.sendall.side_effect = lambda data: sent_data.append(data)
            mock_sock_class.return_value = mock_sock

            handle_riva_proxy(method="riva/tasks/list", params={"filter": "active"}, req_id=5)

        # Second sendall call is the JSON payload (first is the length prefix)
        json_payload = json.loads(sent_data[1].decode("utf-8"))
        assert json_payload["method"] == "riva/tasks/list"
        assert json_payload["params"]["filter"] == "active"
