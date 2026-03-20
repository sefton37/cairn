"""RIVA proxy handler — forwards riva/* RPC calls to RIVA's Unix socket.

RIVA runs as a separate process listening on ~/.talkingrock/riva.sock.
This handler opens a connection, sends the JSON-RPC request, reads the
response, and returns it transparently to the Tauri frontend.

If RIVA's socket is absent or connection is refused, returns a structured
error rather than crashing Cairn.
"""

from __future__ import annotations

import json
import logging
import struct
from pathlib import Path
from typing import Any

from cairn.settings import settings

logger = logging.getLogger(__name__)

_RIVA_SOCKET = "riva.sock"
_RIVA_ERROR_CODE = -32099
_CONNECT_TIMEOUT = 3.0
_READ_TIMEOUT = 30.0


def _get_socket_path() -> Path:
    return settings.data_dir / _RIVA_SOCKET


def handle_riva_proxy(*, method: str, params: dict[str, Any], req_id: Any) -> dict[str, Any]:
    """Forward a riva/* RPC call to the RIVA service.

    This is a synchronous proxy. It opens a blocking socket connection,
    sends the request, reads the response, and returns it.

    Args:
        method: The full method name (e.g. "riva/ping").
        params: The JSON-RPC params dict.
        req_id: The request ID to forward.

    Returns:
        The JSON-RPC response dict (result or error) from RIVA.
    """
    import socket as sock

    socket_path = _get_socket_path()

    if not socket_path.exists():
        logger.debug("RIVA socket not found at %s", socket_path)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": _RIVA_ERROR_CODE,
                "message": "RIVA service not running",
            },
        }

    try:
        s = sock.socket(sock.AF_UNIX, sock.SOCK_STREAM)
        s.settimeout(_CONNECT_TIMEOUT)
        s.connect(str(socket_path))

        # Build the JSON-RPC request
        request = json.dumps({
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": req_id,
        }).encode("utf-8")

        # Send length-prefixed message
        s.sendall(struct.pack("!I", len(request)))
        s.sendall(request)

        # Read length-prefixed response
        s.settimeout(_READ_TIMEOUT)
        length_bytes = _recv_exactly(s, 4)
        msg_length = struct.unpack("!I", length_bytes)[0]

        if msg_length > 10 * 1024 * 1024:
            raise ValueError(f"RIVA response too large: {msg_length} bytes")

        data = _recv_exactly(s, msg_length)
        s.close()

        response = json.loads(data.decode("utf-8"))
        return response

    except (ConnectionRefusedError, FileNotFoundError):
        logger.debug("RIVA service not reachable at %s", socket_path)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": _RIVA_ERROR_CODE,
                "message": "RIVA service not running",
            },
        }
    except Exception as exc:
        logger.warning("RIVA proxy error: %s", exc)
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {
                "code": _RIVA_ERROR_CODE,
                "message": f"RIVA proxy error: {exc}",
            },
        }


def _recv_exactly(s, n: int) -> bytes:
    """Read exactly n bytes from a socket."""
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("RIVA socket closed unexpectedly")
        buf.extend(chunk)
    return bytes(buf)
