"""Tests for LSP manager."""

from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode.lsp_manager import (
    DEFAULT_SERVERS,
    LSPManager,
    LanguageServerConfig,
    check_lsp_server,
    get_available_servers,
)


class TestLanguageServerConfig:
    """Tests for LanguageServerConfig."""

    def test_create_config(self) -> None:
        """Should create a config."""
        config = LanguageServerConfig(
            command=["pyright-langserver", "--stdio"],
            extensions=(".py", ".pyi"),
            language_id="python",
        )

        assert config.command == ["pyright-langserver", "--stdio"]
        assert config.extensions == (".py", ".pyi")
        assert config.language_id == "python"

    def test_config_is_frozen(self) -> None:
        """Config should be immutable."""
        config = LanguageServerConfig(
            command=["pyright-langserver"],
            extensions=(".py",),
            language_id="python",
        )

        with pytest.raises(Exception):  # FrozenInstanceError
            config.command = ["other"]  # type: ignore


class TestDefaultServers:
    """Tests for default server configurations."""

    def test_python_server(self) -> None:
        """Should have Python server config."""
        assert "python" in DEFAULT_SERVERS
        config = DEFAULT_SERVERS["python"]
        assert "pyright" in config.command[0]
        assert ".py" in config.extensions

    def test_typescript_server(self) -> None:
        """Should have TypeScript server config."""
        assert "typescript" in DEFAULT_SERVERS
        config = DEFAULT_SERVERS["typescript"]
        assert "typescript" in config.command[0]
        assert ".ts" in config.extensions

    def test_rust_server(self) -> None:
        """Should have Rust server config."""
        assert "rust" in DEFAULT_SERVERS
        config = DEFAULT_SERVERS["rust"]
        assert "rust-analyzer" in config.command[0]
        assert ".rs" in config.extensions


class TestLSPManager:
    """Tests for LSPManager."""

    def test_create_manager(self, tmp_path: Path) -> None:
        """Should create a manager."""
        manager = LSPManager(tmp_path)

        assert manager.root_path == tmp_path
        assert manager.servers == DEFAULT_SERVERS

    def test_create_with_custom_servers(self, tmp_path: Path) -> None:
        """Should create manager with custom servers."""
        custom = {
            "python": LanguageServerConfig(
                command=["custom-python-lsp"],
                extensions=(".py",),
                language_id="python",
            ),
        }

        manager = LSPManager(tmp_path, servers=custom)

        assert manager.servers == custom
        assert "typescript" not in manager.servers

    def test_get_language_for_file(self, tmp_path: Path) -> None:
        """Should detect language from file extension."""
        manager = LSPManager(tmp_path)

        assert manager.get_language_for_file("main.py") == "python"
        assert manager.get_language_for_file("main.pyi") == "python"
        assert manager.get_language_for_file("app.ts") == "typescript"
        assert manager.get_language_for_file("component.tsx") == "typescript"
        assert manager.get_language_for_file("lib.rs") == "rust"
        assert manager.get_language_for_file("unknown.xyz") is None

    def test_get_client_for_unconfigured_language(self, tmp_path: Path) -> None:
        """Should return None for unconfigured languages."""
        manager = LSPManager(tmp_path)

        # Remove all servers
        manager.servers = {}

        client = manager.get_client("python")
        assert client is None

    def test_get_client_for_file_unconfigured(self, tmp_path: Path) -> None:
        """Should return None for unconfigured file types."""
        manager = LSPManager(tmp_path)

        client = manager.get_client_for_file("file.unknown")
        assert client is None

    def test_is_available(self, tmp_path: Path) -> None:
        """Should check if language is available."""
        manager = LSPManager(tmp_path)

        assert manager.is_available("python")
        assert manager.is_available("typescript")
        assert not manager.is_available("unknown")

    def test_get_status(self, tmp_path: Path) -> None:
        """Should return status information."""
        manager = LSPManager(tmp_path)

        status = manager.get_status()

        assert status["root_path"] == str(tmp_path)
        assert "python" in status["configured"]
        assert status["running"] == []
        assert status["failed"] == []


class TestLSPManagerDiagnostics:
    """Tests for LSPManager diagnostics methods."""

    def test_get_diagnostics_no_client(self, tmp_path: Path) -> None:
        """Should return empty list if no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}  # Remove all servers

        diags = manager.get_diagnostics("main.py")
        assert diags == []

    def test_get_all_diagnostics_empty(self, tmp_path: Path) -> None:
        """Should return empty dict if no clients running."""
        manager = LSPManager(tmp_path)

        all_diags = manager.get_all_diagnostics()
        assert all_diags == {}

    def test_get_errors_empty(self, tmp_path: Path) -> None:
        """Should return empty list if no diagnostics."""
        manager = LSPManager(tmp_path)

        errors = manager.get_errors("main.py")
        assert errors == []


class TestLSPManagerDocSync:
    """Tests for document synchronization."""

    def test_open_file_no_client(self, tmp_path: Path) -> None:
        """Should handle open_file when no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        # Should not raise
        manager.open_file("main.py", "content")

    def test_update_file_no_client(self, tmp_path: Path) -> None:
        """Should handle update_file when no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        # Should not raise
        manager.update_file("main.py", "new content")

    def test_close_file_no_client(self, tmp_path: Path) -> None:
        """Should handle close_file when no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        # Should not raise
        manager.close_file("main.py")


class TestLSPManagerLanguageFeatures:
    """Tests for language features."""

    def test_get_definition_no_client(self, tmp_path: Path) -> None:
        """Should return None if no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        loc = manager.get_definition("main.py", 10, 5)
        assert loc is None

    def test_get_references_no_client(self, tmp_path: Path) -> None:
        """Should return empty list if no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        refs = manager.get_references("main.py", 10, 5)
        assert refs == []

    def test_get_hover_no_client(self, tmp_path: Path) -> None:
        """Should return None if no client available."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        hover = manager.get_hover("main.py", 10, 5)
        assert hover is None


class TestLSPManagerLifecycle:
    """Tests for lifecycle management."""

    def test_shutdown_all_empty(self, tmp_path: Path) -> None:
        """Should handle shutdown with no clients."""
        manager = LSPManager(tmp_path)

        # Should not raise
        manager.shutdown_all()

    def test_restart_unconfigured_server(self, tmp_path: Path) -> None:
        """Should return False for unconfigured server."""
        manager = LSPManager(tmp_path)
        manager.servers = {}

        result = manager.restart_server("python")
        assert result is False


class TestHelperFunctions:
    """Tests for helper functions."""

    def test_check_lsp_server_exists(self) -> None:
        """Should return True for existing commands."""
        # 'ls' should exist on most Linux systems
        assert check_lsp_server(["ls"]) is True

    def test_check_lsp_server_not_exists(self) -> None:
        """Should return False for non-existent commands."""
        assert check_lsp_server(["nonexistent-command-12345"]) is False

    def test_get_available_servers(self) -> None:
        """Should return availability for all servers."""
        available = get_available_servers()

        assert "python" in available
        assert "typescript" in available
        assert "rust" in available
        # Values are booleans
        assert all(isinstance(v, bool) for v in available.values())
