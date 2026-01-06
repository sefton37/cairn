"""LSP Manager - Manage multiple language servers for a repository.

Provides a unified interface for LSP operations across different languages,
with lazy server startup and automatic language detection.
"""

from __future__ import annotations

import atexit
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from reos.code_mode.lsp_client import (
    Diagnostic,
    HoverInfo,
    LSPClient,
    LSPClientError,
    LSPLocation,
)

if TYPE_CHECKING:
    from reos.code_mode.sandbox import CodeSandbox

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LanguageServerConfig:
    """Configuration for a language server."""

    command: list[str]
    extensions: tuple[str, ...]
    language_id: str


# Default language server configurations
DEFAULT_SERVERS: dict[str, LanguageServerConfig] = {
    "python": LanguageServerConfig(
        command=["pyright-langserver", "--stdio"],
        extensions=(".py", ".pyi"),
        language_id="python",
    ),
    "typescript": LanguageServerConfig(
        command=["typescript-language-server", "--stdio"],
        extensions=(".ts", ".tsx"),
        language_id="typescript",
    ),
    "javascript": LanguageServerConfig(
        command=["typescript-language-server", "--stdio"],
        extensions=(".js", ".jsx"),
        language_id="javascript",
    ),
    "rust": LanguageServerConfig(
        command=["rust-analyzer"],
        extensions=(".rs",),
        language_id="rust",
    ),
}


class LSPManager:
    """Manage LSP servers for a repository.

    Provides:
    - Lazy server startup (only when needed)
    - Automatic language detection from file extension
    - Unified interface for diagnostics, definition, references, hover
    - Graceful shutdown on exit
    """

    def __init__(
        self,
        root_path: Path,
        servers: dict[str, LanguageServerConfig] | None = None,
        timeout: float = 30.0,
    ):
        """Initialize LSP manager.

        Args:
            root_path: Root path of the workspace
            servers: Custom server configurations (uses defaults if not provided)
            timeout: Request timeout in seconds
        """
        self.root_path = root_path
        self.servers = servers or DEFAULT_SERVERS
        self.timeout = timeout

        self._clients: dict[str, LSPClient] = {}
        self._failed: set[str] = set()  # Languages that failed to start
        self._lock = threading.Lock()

        # Register shutdown handler
        atexit.register(self.shutdown_all)

    @classmethod
    def from_sandbox(
        cls,
        sandbox: CodeSandbox,
        servers: dict[str, LanguageServerConfig] | None = None,
    ) -> LSPManager:
        """Create LSP manager from a CodeSandbox.

        Args:
            sandbox: Code sandbox instance
            servers: Custom server configurations

        Returns:
            LSP manager for the sandbox's repository
        """
        return cls(sandbox.repo_path, servers)

    def get_client(self, language: str) -> LSPClient | None:
        """Get or create a client for a language.

        Args:
            language: Language identifier (e.g., "python", "typescript")

        Returns:
            LSP client, or None if server unavailable
        """
        with self._lock:
            # Check if already running
            if language in self._clients:
                client = self._clients[language]
                if client.is_running():
                    return client
                # Server died, remove it
                del self._clients[language]

            # Check if previously failed
            if language in self._failed:
                return None

            # Check if we have a config for this language
            if language not in self.servers:
                logger.debug("No LSP server configured for: %s", language)
                return None

            # Start the server
            config = self.servers[language]
            client = LSPClient(
                language=language,
                server_cmd=config.command,
                root_path=self.root_path,
                timeout=self.timeout,
            )

            try:
                client.start()
                self._clients[language] = client
                logger.info("Started LSP server for %s", language)
                return client
            except FileNotFoundError:
                logger.warning(
                    "LSP server not found for %s: %s",
                    language,
                    config.command[0],
                )
                self._failed.add(language)
                return None
            except LSPClientError as e:
                logger.warning("Failed to start LSP server for %s: %s", language, e)
                self._failed.add(language)
                return None

    def get_client_for_file(self, file_path: str) -> LSPClient | None:
        """Get appropriate client based on file extension.

        Args:
            file_path: Path to the file

        Returns:
            LSP client for the file's language, or None
        """
        ext = Path(file_path).suffix.lower()

        for language, config in self.servers.items():
            if ext in config.extensions:
                return self.get_client(language)

        return None

    def get_language_for_file(self, file_path: str) -> str | None:
        """Get language identifier for a file.

        Args:
            file_path: Path to the file

        Returns:
            Language identifier, or None
        """
        ext = Path(file_path).suffix.lower()

        for language, config in self.servers.items():
            if ext in config.extensions:
                return language

        return None

    # -------------------------------------------------------------------------
    # Diagnostics
    # -------------------------------------------------------------------------

    def get_diagnostics(self, file_path: str) -> list[Diagnostic]:
        """Get diagnostics for a file.

        Args:
            file_path: Path to the file

        Returns:
            List of diagnostics
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return []

        return client.get_diagnostics(file_path)

    def get_all_diagnostics(self) -> dict[str, list[Diagnostic]]:
        """Get diagnostics from all active servers.

        Returns:
            Dictionary mapping file paths to diagnostics
        """
        result: dict[str, list[Diagnostic]] = {}

        with self._lock:
            for client in self._clients.values():
                if client.is_running():
                    for path, diags in client.get_all_diagnostics().items():
                        if path in result:
                            result[path].extend(diags)
                        else:
                            result[path] = list(diags)

        return result

    def get_errors(self, file_path: str | None = None) -> list[Diagnostic]:
        """Get only error-level diagnostics.

        Args:
            file_path: Optional file path to filter by

        Returns:
            List of error diagnostics
        """
        if file_path:
            diagnostics = self.get_diagnostics(file_path)
        else:
            all_diags = self.get_all_diagnostics()
            diagnostics = []
            for diags in all_diags.values():
                diagnostics.extend(diags)

        return [d for d in diagnostics if d.severity == "error"]

    # -------------------------------------------------------------------------
    # Document Synchronization
    # -------------------------------------------------------------------------

    def open_file(self, file_path: str, content: str | None = None) -> None:
        """Open a file in the language server.

        Args:
            file_path: Path to the file
            content: File content (reads from disk if not provided)
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return

        if content is None:
            try:
                full_path = self.root_path / file_path
                content = full_path.read_text()
            except Exception as e:
                logger.warning("Failed to read file %s: %s", file_path, e)
                return

        client.did_open(file_path, content)

    def update_file(self, file_path: str, content: str) -> None:
        """Update file content in the language server.

        Args:
            file_path: Path to the file
            content: New file content
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return

        client.did_change(file_path, content)

    def close_file(self, file_path: str) -> None:
        """Close a file in the language server.

        Args:
            file_path: Path to the file
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return

        client.did_close(file_path)

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
            Location of the definition, or None
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return None

        try:
            return client.get_definition(file_path, line, column)
        except LSPClientError as e:
            logger.warning("get_definition failed: %s", e)
            return None

    def get_references(
        self, file_path: str, line: int, column: int
    ) -> list[LSPLocation]:
        """Find all references to symbol at position.

        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            List of locations
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return []

        try:
            return client.get_references(file_path, line, column)
        except LSPClientError as e:
            logger.warning("get_references failed: %s", e)
            return []

    def get_hover(self, file_path: str, line: int, column: int) -> HoverInfo | None:
        """Get hover information at position.

        Args:
            file_path: Path to the file
            line: Line number (0-indexed)
            column: Column number (0-indexed)

        Returns:
            Hover information, or None
        """
        client = self.get_client_for_file(file_path)
        if client is None:
            return None

        try:
            return client.get_hover(file_path, line, column)
        except LSPClientError as e:
            logger.warning("get_hover failed: %s", e)
            return None

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    def shutdown_all(self) -> None:
        """Shutdown all language servers."""
        with self._lock:
            for language, client in list(self._clients.items()):
                logger.info("Shutting down LSP server: %s", language)
                try:
                    client.stop()
                except Exception as e:
                    logger.warning("Error shutting down %s: %s", language, e)
            self._clients.clear()
            self._failed.clear()

    def restart_server(self, language: str) -> bool:
        """Restart a specific language server.

        Args:
            language: Language identifier

        Returns:
            True if server restarted successfully
        """
        with self._lock:
            # Stop existing
            if language in self._clients:
                try:
                    self._clients[language].stop()
                except Exception:
                    pass
                del self._clients[language]

            # Clear failed flag
            self._failed.discard(language)

        # Try to start again
        return self.get_client(language) is not None

    def get_status(self) -> dict[str, Any]:
        """Get status of all language servers.

        Returns:
            Dictionary with server status information
        """
        with self._lock:
            return {
                "root_path": str(self.root_path),
                "configured": list(self.servers.keys()),
                "running": [
                    lang
                    for lang, client in self._clients.items()
                    if client.is_running()
                ],
                "failed": list(self._failed),
            }

    def is_available(self, language: str) -> bool:
        """Check if a language server is available.

        Args:
            language: Language identifier

        Returns:
            True if server is configured and not failed
        """
        return language in self.servers and language not in self._failed


def check_lsp_server(command: list[str]) -> bool:
    """Check if an LSP server is installed.

    Args:
        command: Server command

    Returns:
        True if the server executable exists
    """
    import shutil

    return shutil.which(command[0]) is not None


def get_available_servers() -> dict[str, bool]:
    """Get availability status of all configured servers.

    Returns:
        Dictionary mapping language to availability
    """
    return {
        language: check_lsp_server(config.command)
        for language, config in DEFAULT_SERVERS.items()
    }
