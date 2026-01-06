"""LSP Client - Language Server Protocol client for real-time code intelligence.

Implements JSON-RPC 2.0 over stdio communication with language servers
like pyright, typescript-language-server, and rust-analyzer.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# LSP Diagnostic severity levels
class DiagnosticSeverity:
    ERROR = 1
    WARNING = 2
    INFORMATION = 3
    HINT = 4


SEVERITY_NAMES = {
    DiagnosticSeverity.ERROR: "error",
    DiagnosticSeverity.WARNING: "warning",
    DiagnosticSeverity.INFORMATION: "info",
    DiagnosticSeverity.HINT: "hint",
}


@dataclass
class LSPLocation:
    """Source code location from LSP."""

    file_path: str
    line: int  # 0-indexed
    column: int  # 0-indexed
    end_line: int | None = None
    end_column: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
        }


@dataclass
class Diagnostic:
    """LSP diagnostic (error, warning, info, hint)."""

    file_path: str
    line: int  # 0-indexed
    column: int  # 0-indexed
    end_line: int
    end_column: int
    severity: str  # "error", "warning", "info", "hint"
    message: str
    source: str  # "pyright", "typescript", etc.
    code: str | None = None  # Error code if available

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "file_path": self.file_path,
            "line": self.line,
            "column": self.column,
            "end_line": self.end_line,
            "end_column": self.end_column,
            "severity": self.severity,
            "message": self.message,
            "source": self.source,
            "code": self.code,
        }


@dataclass
class HoverInfo:
    """Hover documentation from LSP."""

    content: str  # Markdown content
    range: LSPLocation | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dictionary."""
        return {
            "content": self.content,
            "range": self.range.to_dict() if self.range else None,
        }


class LSPClientError(RuntimeError):
    """Error in LSP client operations."""

    pass


class LSPClient:
    """Client for a single LSP server instance.

    Manages the lifecycle of a language server process and provides
    methods for LSP operations like diagnostics, go-to-definition,
    find-references, and hover.

    Uses JSON-RPC 2.0 over stdio with Content-Length headers.
    """

    def __init__(
        self,
        language: str,
        server_cmd: list[str],
        root_path: Path,
        timeout: float = 30.0,
    ):
        """Initialize LSP client.

        Args:
            language: Language identifier (e.g., "python", "typescript")
            server_cmd: Command to start the language server
            root_path: Root path of the workspace
            timeout: Request timeout in seconds
        """
        self.language = language
        self.server_cmd = server_cmd
        self.root_path = root_path
        self.timeout = timeout

        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0
        self._pending: dict[int, threading.Event] = {}
        self._responses: dict[int, Any] = {}
        self._diagnostics: dict[str, list[Diagnostic]] = {}
        self._lock = threading.Lock()
        self._reader_thread: threading.Thread | None = None
        self._initialized = False
        self._shutdown = False
        self._document_versions: dict[str, int] = {}

    def start(self) -> None:
        """Start the language server process.

        Raises:
            LSPClientError: If server fails to start
            FileNotFoundError: If server command not found
        """
        if self._process is not None:
            return

        logger.info("Starting LSP server: %s", " ".join(self.server_cmd))

        try:
            self._process = subprocess.Popen(
                self.server_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.root_path,
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"LSP server not found: {self.server_cmd[0]}"
            ) from e
        except Exception as e:
            raise LSPClientError(f"Failed to start LSP server: {e}") from e

        # Start reader thread
        self._reader_thread = threading.Thread(
            target=self._read_responses,
            daemon=True,
            name=f"lsp-reader-{self.language}",
        )
        self._reader_thread.start()

        # Initialize the server
        self._initialize()

    def stop(self) -> None:
        """Shutdown the language server gracefully."""
        if self._process is None or self._shutdown:
            return

        self._shutdown = True
        logger.info("Stopping LSP server: %s", self.language)

        try:
            # Send shutdown request
            self._send_request("shutdown", {})
            # Send exit notification
            self._send_notification("exit", None)
        except Exception as e:
            logger.warning("Error during LSP shutdown: %s", e)

        # Terminate process
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
        except Exception:
            pass

        self._process = None
        self._initialized = False

    def is_running(self) -> bool:
        """Check if the server is running."""
        return (
            self._process is not None
            and self._process.poll() is None
            and self._initialized
        )

    # -------------------------------------------------------------------------
    # Document Synchronization
    # -------------------------------------------------------------------------

    def did_open(self, file_path: str, content: str) -> None:
        """Notify server that a document was opened.

        Args:
            file_path: Path to the file (relative or absolute)
            content: File content
        """
        uri = self._path_to_uri(file_path)
        self._document_versions[uri] = 1

        self._send_notification(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": self._get_language_id(file_path),
                    "version": 1,
                    "text": content,
                }
            },
        )

    def did_change(self, file_path: str, content: str) -> None:
        """Notify server of document changes.

        Args:
            file_path: Path to the file
            content: New file content (full sync)
        """
        uri = self._path_to_uri(file_path)

        # Increment version
        version = self._document_versions.get(uri, 0) + 1
        self._document_versions[uri] = version

        # If not opened yet, open it first
        if uri not in self._document_versions or self._document_versions[uri] == 1:
            self.did_open(file_path, content)
            return

        self._send_notification(
            "textDocument/didChange",
            {
                "textDocument": {
                    "uri": uri,
                    "version": version,
                },
                "contentChanges": [{"text": content}],  # Full sync
            },
        )

    def did_close(self, file_path: str) -> None:
        """Notify server that a document was closed.

        Args:
            file_path: Path to the file
        """
        uri = self._path_to_uri(file_path)

        if uri in self._document_versions:
            del self._document_versions[uri]

        self._send_notification(
            "textDocument/didClose",
            {"textDocument": {"uri": uri}},
        )

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get diagnostics for a file.

        Note: Diagnostics are pushed by the server via notifications.
        This method returns cached diagnostics.

        Args:
            file_path: Path to the file

        Returns:
            List of diagnostics for the file
        """
        uri = self._path_to_uri(file_path)
        with self._lock:
            return list(self._diagnostics.get(uri, []))

    def get_all_diagnostics(self) -> dict[str, list[Diagnostic]]:
        """Get all cached diagnostics.

        Returns:
            Dictionary mapping file paths to diagnostics
        """
        with self._lock:
            result = {}
            for uri, diags in self._diagnostics.items():
                file_path = self._uri_to_path(uri)
                result[file_path] = list(diags)
            return result

    def clear_diagnostics(self) -> None:
        """Clear all cached diagnostics."""
        with self._lock:
            self._diagnostics.clear()

    # -------------------------------------------------------------------------
    # Language Features
    # -------------------------------------------------------------------------

    def get_definition(
        self, file_path: str, line: int, column: int
    ) -> LSPLocation | None:
        """Go to definition at position.

        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            Location of the definition, or None if not found
        """
        uri = self._path_to_uri(file_path)

        result = self._send_request(
            "textDocument/definition",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        return self._parse_location(result)

    def get_references(
        self, file_path: str, line: int, column: int, include_declaration: bool = True
    ) -> list[LSPLocation]:
        """Find all references to symbol at position.

        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            column: Column number (0-indexed)
            include_declaration: Include the declaration itself

        Returns:
            List of locations where the symbol is referenced
        """
        uri = self._path_to_uri(file_path)

        result = self._send_request(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
                "context": {"includeDeclaration": include_declaration},
            },
        )

        return self._parse_locations(result)

    def get_hover(self, file_path: str, line: int, column: int) -> HoverInfo | None:
        """Get hover information at position.

        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            Hover information, or None if not available
        """
        uri = self._path_to_uri(file_path)

        result = self._send_request(
            "textDocument/hover",
            {
                "textDocument": {"uri": uri},
                "position": {"line": line, "character": column},
            },
        )

        return self._parse_hover(result)

    # -------------------------------------------------------------------------
    # JSON-RPC Communication
    # -------------------------------------------------------------------------

    def _initialize(self) -> None:
        """Send initialize request to the server."""
        root_uri = self._path_to_uri(str(self.root_path))

        result = self._send_request(
            "initialize",
            {
                "processId": None,
                "rootUri": root_uri,
                "rootPath": str(self.root_path),
                "capabilities": {
                    "textDocument": {
                        "synchronization": {
                            "didOpen": True,
                            "didChange": True,
                            "didClose": True,
                        },
                        "definition": {"dynamicRegistration": False},
                        "references": {"dynamicRegistration": False},
                        "hover": {
                            "dynamicRegistration": False,
                            "contentFormat": ["markdown", "plaintext"],
                        },
                        "publishDiagnostics": {
                            "relatedInformation": True,
                            "codeDescriptionSupport": True,
                        },
                    },
                    "workspace": {
                        "workspaceFolders": True,
                    },
                },
                "workspaceFolders": [
                    {
                        "uri": root_uri,
                        "name": self.root_path.name,
                    }
                ],
            },
        )

        if result is None:
            raise LSPClientError("Initialize request failed")

        # Send initialized notification
        self._send_notification("initialized", {})
        self._initialized = True

        logger.info("LSP server initialized: %s", self.language)

    def _send_request(self, method: str, params: dict[str, Any]) -> Any:
        """Send a request and wait for response.

        Args:
            method: LSP method name
            params: Request parameters

        Returns:
            Response result

        Raises:
            LSPClientError: If request fails or times out
        """
        if self._process is None or self._shutdown:
            raise LSPClientError("LSP server not running")

        with self._lock:
            self._request_id += 1
            req_id = self._request_id
            event = threading.Event()
            self._pending[req_id] = event

        message = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": method,
            "params": params,
        }

        self._write_message(message)

        # Wait for response
        if not event.wait(timeout=self.timeout):
            with self._lock:
                self._pending.pop(req_id, None)
            raise LSPClientError(f"Request timed out: {method}")

        with self._lock:
            self._pending.pop(req_id, None)
            response = self._responses.pop(req_id, None)

        if response is None:
            return None

        if "error" in response:
            error = response["error"]
            raise LSPClientError(
                f"LSP error ({error.get('code')}): {error.get('message')}"
            )

        return response.get("result")

    def _send_notification(self, method: str, params: Any) -> None:
        """Send a notification (no response expected).

        Args:
            method: LSP method name
            params: Notification parameters
        """
        if self._process is None:
            return

        message: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
        }
        if params is not None:
            message["params"] = params

        self._write_message(message)

    def _write_message(self, message: dict[str, Any]) -> None:
        """Write a JSON-RPC message to the server.

        Args:
            message: Message to send
        """
        if self._process is None or self._process.stdin is None:
            return

        content = json.dumps(message)
        content_bytes = content.encode("utf-8")
        header = f"Content-Length: {len(content_bytes)}\r\n\r\n"

        try:
            self._process.stdin.write(header.encode("utf-8"))
            self._process.stdin.write(content_bytes)
            self._process.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            logger.warning("Failed to write to LSP server: %s", e)

    def _read_responses(self) -> None:
        """Read responses from the server (runs in background thread)."""
        if self._process is None or self._process.stdout is None:
            return

        while not self._shutdown and self._process.poll() is None:
            try:
                message = self._read_message()
                if message is None:
                    break
                self._handle_message(message)
            except Exception as e:
                if not self._shutdown:
                    logger.warning("Error reading LSP message: %s", e)
                break

    def _read_message(self) -> dict[str, Any] | None:
        """Read a single JSON-RPC message from the server.

        Returns:
            Parsed message or None if stream ended
        """
        if self._process is None or self._process.stdout is None:
            return None

        # Read headers
        headers: dict[str, str] = {}
        while True:
            line = self._process.stdout.readline()
            if not line:
                return None

            line_str = line.decode("utf-8").strip()
            if not line_str:
                break

            if ":" in line_str:
                key, value = line_str.split(":", 1)
                headers[key.strip()] = value.strip()

        # Get content length
        content_length = int(headers.get("Content-Length", 0))
        if content_length == 0:
            return None

        # Read content
        content = self._process.stdout.read(content_length)
        if not content:
            return None

        return json.loads(content.decode("utf-8"))

    def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle an incoming message from the server.

        Args:
            message: Parsed JSON-RPC message
        """
        # Check if it's a response to a request
        if "id" in message and message["id"] is not None:
            req_id = message["id"]
            with self._lock:
                if req_id in self._pending:
                    self._responses[req_id] = message
                    self._pending[req_id].set()
            return

        # Handle notifications
        method = message.get("method", "")
        params = message.get("params", {})

        if method == "textDocument/publishDiagnostics":
            self._handle_diagnostics(params)
        elif method == "window/logMessage":
            self._handle_log_message(params)

    def _handle_diagnostics(self, params: dict[str, Any]) -> None:
        """Handle diagnostics notification from server.

        Args:
            params: Diagnostics parameters
        """
        uri = params.get("uri", "")
        raw_diagnostics = params.get("diagnostics", [])

        diagnostics = []
        for d in raw_diagnostics:
            range_info = d.get("range", {})
            start = range_info.get("start", {})
            end = range_info.get("end", {})

            severity_num = d.get("severity", DiagnosticSeverity.ERROR)
            severity = SEVERITY_NAMES.get(severity_num, "error")

            code = d.get("code")
            if code is not None:
                code = str(code)

            diagnostics.append(
                Diagnostic(
                    file_path=self._uri_to_path(uri),
                    line=start.get("line", 0),
                    column=start.get("character", 0),
                    end_line=end.get("line", 0),
                    end_column=end.get("character", 0),
                    severity=severity,
                    message=d.get("message", ""),
                    source=d.get("source", self.language),
                    code=code,
                )
            )

        with self._lock:
            self._diagnostics[uri] = diagnostics

        logger.debug(
            "Received %d diagnostics for %s",
            len(diagnostics),
            self._uri_to_path(uri),
        )

    def _handle_log_message(self, params: dict[str, Any]) -> None:
        """Handle log message from server.

        Args:
            params: Log message parameters
        """
        message = params.get("message", "")
        msg_type = params.get("type", 4)  # 4 = Log

        if msg_type == 1:  # Error
            logger.error("LSP [%s]: %s", self.language, message)
        elif msg_type == 2:  # Warning
            logger.warning("LSP [%s]: %s", self.language, message)
        elif msg_type == 3:  # Info
            logger.info("LSP [%s]: %s", self.language, message)
        else:
            logger.debug("LSP [%s]: %s", self.language, message)

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    def _path_to_uri(self, path: str) -> str:
        """Convert file path to URI.

        Args:
            path: File path (relative or absolute)

        Returns:
            file:// URI
        """
        if not Path(path).is_absolute():
            path = str(self.root_path / path)
        return f"file://{path}"

    def _uri_to_path(self, uri: str) -> str:
        """Convert URI to file path.

        Args:
            uri: file:// URI

        Returns:
            File path
        """
        if uri.startswith("file://"):
            return uri[7:]
        return uri

    def _get_language_id(self, file_path: str) -> str:
        """Get LSP language ID for a file.

        Args:
            file_path: Path to the file

        Returns:
            Language ID (e.g., "python", "typescript")
        """
        ext = Path(file_path).suffix.lower()
        language_map = {
            ".py": "python",
            ".pyi": "python",
            ".ts": "typescript",
            ".tsx": "typescriptreact",
            ".js": "javascript",
            ".jsx": "javascriptreact",
            ".rs": "rust",
            ".go": "go",
        }
        return language_map.get(ext, self.language)

    def _parse_location(self, result: Any) -> LSPLocation | None:
        """Parse location from LSP response.

        Args:
            result: LSP response (Location, Location[], or LocationLink[])

        Returns:
            First location found, or None
        """
        if result is None:
            return None

        # Handle array of locations
        if isinstance(result, list):
            if not result:
                return None
            result = result[0]

        # Handle LocationLink
        if "targetUri" in result:
            uri = result["targetUri"]
            range_info = result.get("targetRange", result.get("targetSelectionRange", {}))
        else:
            uri = result.get("uri", "")
            range_info = result.get("range", {})

        start = range_info.get("start", {})
        end = range_info.get("end", {})

        return LSPLocation(
            file_path=self._uri_to_path(uri),
            line=start.get("line", 0),
            column=start.get("character", 0),
            end_line=end.get("line"),
            end_column=end.get("character"),
        )

    def _parse_locations(self, result: Any) -> list[LSPLocation]:
        """Parse multiple locations from LSP response.

        Args:
            result: LSP response (Location[])

        Returns:
            List of locations
        """
        if result is None:
            return []

        if not isinstance(result, list):
            loc = self._parse_location(result)
            return [loc] if loc else []

        locations = []
        for item in result:
            loc = self._parse_location(item)
            if loc:
                locations.append(loc)

        return locations

    def _parse_hover(self, result: Any) -> HoverInfo | None:
        """Parse hover response.

        Args:
            result: LSP hover response

        Returns:
            Hover information, or None
        """
        if result is None:
            return None

        contents = result.get("contents")
        if contents is None:
            return None

        # Contents can be MarkupContent, MarkedString, or MarkedString[]
        if isinstance(contents, str):
            content = contents
        elif isinstance(contents, dict):
            content = contents.get("value", "")
        elif isinstance(contents, list):
            parts = []
            for item in contents:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict):
                    parts.append(item.get("value", ""))
            content = "\n\n".join(parts)
        else:
            return None

        range_info = result.get("range")
        location = None
        if range_info:
            start = range_info.get("start", {})
            end = range_info.get("end", {})
            location = LSPLocation(
                file_path="",  # Not provided in hover
                line=start.get("line", 0),
                column=start.get("character", 0),
                end_line=end.get("line"),
                end_column=end.get("character"),
            )

        return HoverInfo(content=content, range=location)
