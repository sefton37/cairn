"""Tests for LSP client."""

from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode.lsp_client import (
    Diagnostic,
    DiagnosticSeverity,
    HoverInfo,
    LSPClient,
    LSPClientError,
    LSPLocation,
    SEVERITY_NAMES,
)


class TestDiagnostic:
    """Tests for Diagnostic dataclass."""

    def test_create_diagnostic(self) -> None:
        """Should create a diagnostic."""
        diag = Diagnostic(
            file_path="main.py",
            line=10,
            column=5,
            end_line=10,
            end_column=15,
            severity="error",
            message="Type error",
            source="pyright",
            code="reportGeneralTypeIssues",
        )

        assert diag.file_path == "main.py"
        assert diag.line == 10
        assert diag.column == 5
        assert diag.severity == "error"
        assert diag.message == "Type error"
        assert diag.source == "pyright"
        assert diag.code == "reportGeneralTypeIssues"

    def test_diagnostic_to_dict(self) -> None:
        """Should serialize to dictionary."""
        diag = Diagnostic(
            file_path="main.py",
            line=10,
            column=5,
            end_line=10,
            end_column=15,
            severity="warning",
            message="Unused variable",
            source="pyright",
        )

        d = diag.to_dict()

        assert d["file_path"] == "main.py"
        assert d["line"] == 10
        assert d["severity"] == "warning"
        assert d["code"] is None


class TestLSPLocation:
    """Tests for LSPLocation dataclass."""

    def test_create_location(self) -> None:
        """Should create a location."""
        loc = LSPLocation(
            file_path="utils.py",
            line=42,
            column=0,
            end_line=42,
            end_column=10,
        )

        assert loc.file_path == "utils.py"
        assert loc.line == 42
        assert loc.column == 0
        assert loc.end_line == 42
        assert loc.end_column == 10

    def test_location_to_dict(self) -> None:
        """Should serialize to dictionary."""
        loc = LSPLocation(
            file_path="utils.py",
            line=42,
            column=0,
        )

        d = loc.to_dict()

        assert d["file_path"] == "utils.py"
        assert d["line"] == 42
        assert d["end_line"] is None


class TestHoverInfo:
    """Tests for HoverInfo dataclass."""

    def test_create_hover(self) -> None:
        """Should create hover info."""
        hover = HoverInfo(
            content="def foo(x: int) -> str",
            range=LSPLocation(file_path="", line=10, column=5),
        )

        assert hover.content == "def foo(x: int) -> str"
        assert hover.range is not None
        assert hover.range.line == 10

    def test_hover_to_dict(self) -> None:
        """Should serialize to dictionary."""
        hover = HoverInfo(content="Some docs")

        d = hover.to_dict()

        assert d["content"] == "Some docs"
        assert d["range"] is None


class TestSeverityNames:
    """Tests for severity name mapping."""

    def test_severity_names(self) -> None:
        """Should map severity codes to names."""
        assert SEVERITY_NAMES[DiagnosticSeverity.ERROR] == "error"
        assert SEVERITY_NAMES[DiagnosticSeverity.WARNING] == "warning"
        assert SEVERITY_NAMES[DiagnosticSeverity.INFORMATION] == "info"
        assert SEVERITY_NAMES[DiagnosticSeverity.HINT] == "hint"


class TestLSPClientInit:
    """Tests for LSPClient initialization."""

    def test_create_client(self, tmp_path: Path) -> None:
        """Should create a client."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
            timeout=30.0,
        )

        assert client.language == "python"
        assert client.server_cmd == ["pyright-langserver", "--stdio"]
        assert client.root_path == tmp_path
        assert client.timeout == 30.0
        assert not client.is_running()

    def test_start_without_server(self, tmp_path: Path) -> None:
        """Should raise FileNotFoundError if server not found."""
        client = LSPClient(
            language="python",
            server_cmd=["nonexistent-lsp-server", "--stdio"],
            root_path=tmp_path,
        )

        with pytest.raises(FileNotFoundError):
            client.start()


class TestLSPClientHelpers:
    """Tests for LSPClient helper methods."""

    def test_path_to_uri(self, tmp_path: Path) -> None:
        """Should convert path to URI."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        # Relative path
        uri = client._path_to_uri("main.py")
        assert uri == f"file://{tmp_path}/main.py"

        # Absolute path
        uri = client._path_to_uri("/absolute/path/main.py")
        assert uri == "file:///absolute/path/main.py"

    def test_uri_to_path(self, tmp_path: Path) -> None:
        """Should convert URI to path."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        path = client._uri_to_path("file:///home/user/main.py")
        assert path == "/home/user/main.py"

    def test_get_language_id(self, tmp_path: Path) -> None:
        """Should get language ID from file extension."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        assert client._get_language_id("main.py") == "python"
        assert client._get_language_id("main.pyi") == "python"
        assert client._get_language_id("app.ts") == "typescript"
        assert client._get_language_id("component.tsx") == "typescriptreact"
        assert client._get_language_id("script.js") == "javascript"
        assert client._get_language_id("lib.rs") == "rust"
        assert client._get_language_id("unknown.xyz") == "python"  # Falls back to language

    def test_parse_location_single(self, tmp_path: Path) -> None:
        """Should parse single location."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = {
            "uri": "file:///home/user/main.py",
            "range": {
                "start": {"line": 10, "character": 5},
                "end": {"line": 10, "character": 15},
            },
        }

        loc = client._parse_location(result)

        assert loc is not None
        assert loc.file_path == "/home/user/main.py"
        assert loc.line == 10
        assert loc.column == 5
        assert loc.end_line == 10
        assert loc.end_column == 15

    def test_parse_location_array(self, tmp_path: Path) -> None:
        """Should parse first location from array."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = [
            {
                "uri": "file:///first.py",
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
            },
            {
                "uri": "file:///second.py",
                "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 5}},
            },
        ]

        loc = client._parse_location(result)

        assert loc is not None
        assert loc.file_path == "/first.py"
        assert loc.line == 1

    def test_parse_location_link(self, tmp_path: Path) -> None:
        """Should parse LocationLink format."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = {
            "targetUri": "file:///target.py",
            "targetRange": {
                "start": {"line": 20, "character": 0},
                "end": {"line": 25, "character": 0},
            },
            "targetSelectionRange": {
                "start": {"line": 20, "character": 4},
                "end": {"line": 20, "character": 10},
            },
        }

        loc = client._parse_location(result)

        assert loc is not None
        assert loc.file_path == "/target.py"
        assert loc.line == 20

    def test_parse_location_none(self, tmp_path: Path) -> None:
        """Should return None for empty result."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        assert client._parse_location(None) is None
        assert client._parse_location([]) is None

    def test_parse_locations(self, tmp_path: Path) -> None:
        """Should parse multiple locations."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = [
            {
                "uri": "file:///first.py",
                "range": {"start": {"line": 1, "character": 0}, "end": {"line": 1, "character": 5}},
            },
            {
                "uri": "file:///second.py",
                "range": {"start": {"line": 2, "character": 0}, "end": {"line": 2, "character": 5}},
            },
        ]

        locs = client._parse_locations(result)

        assert len(locs) == 2
        assert locs[0].file_path == "/first.py"
        assert locs[1].file_path == "/second.py"

    def test_parse_hover(self, tmp_path: Path) -> None:
        """Should parse hover response."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        # MarkupContent format
        result = {
            "contents": {
                "kind": "markdown",
                "value": "```python\ndef foo(x: int) -> str\n```",
            },
            "range": {
                "start": {"line": 10, "character": 0},
                "end": {"line": 10, "character": 3},
            },
        }

        hover = client._parse_hover(result)

        assert hover is not None
        assert "def foo" in hover.content
        assert hover.range is not None
        assert hover.range.line == 10

    def test_parse_hover_string(self, tmp_path: Path) -> None:
        """Should parse string hover content."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = {"contents": "Simple documentation"}

        hover = client._parse_hover(result)

        assert hover is not None
        assert hover.content == "Simple documentation"

    def test_parse_hover_array(self, tmp_path: Path) -> None:
        """Should parse array hover content."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        result = {
            "contents": [
                {"value": "Part 1"},
                "Part 2",
                {"value": "Part 3"},
            ]
        }

        hover = client._parse_hover(result)

        assert hover is not None
        assert "Part 1" in hover.content
        assert "Part 2" in hover.content
        assert "Part 3" in hover.content


class TestLSPClientDiagnosticsHandler:
    """Tests for diagnostics handling."""

    def test_handle_diagnostics(self, tmp_path: Path) -> None:
        """Should handle diagnostics notification."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        params = {
            "uri": "file:///home/user/main.py",
            "diagnostics": [
                {
                    "range": {
                        "start": {"line": 10, "character": 5},
                        "end": {"line": 10, "character": 15},
                    },
                    "severity": 1,  # Error
                    "message": "Type error: expected int",
                    "source": "pyright",
                    "code": "reportGeneralTypeIssues",
                },
                {
                    "range": {
                        "start": {"line": 20, "character": 0},
                        "end": {"line": 20, "character": 10},
                    },
                    "severity": 2,  # Warning
                    "message": "Unused variable",
                    "source": "pyright",
                },
            ],
        }

        client._handle_diagnostics(params)

        diags = client.get_diagnostics("/home/user/main.py")

        assert len(diags) == 2
        assert diags[0].severity == "error"
        assert diags[0].message == "Type error: expected int"
        assert diags[0].code == "reportGeneralTypeIssues"
        assert diags[1].severity == "warning"

    def test_get_all_diagnostics(self, tmp_path: Path) -> None:
        """Should return all cached diagnostics."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        # Add diagnostics for multiple files
        client._handle_diagnostics({
            "uri": "file:///file1.py",
            "diagnostics": [{"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "severity": 1, "message": "Error 1", "source": "pyright"}],
        })
        client._handle_diagnostics({
            "uri": "file:///file2.py",
            "diagnostics": [{"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "severity": 2, "message": "Warning 1", "source": "pyright"}],
        })

        all_diags = client.get_all_diagnostics()

        assert len(all_diags) == 2
        assert "/file1.py" in all_diags
        assert "/file2.py" in all_diags

    def test_clear_diagnostics(self, tmp_path: Path) -> None:
        """Should clear all diagnostics."""
        client = LSPClient(
            language="python",
            server_cmd=["pyright-langserver", "--stdio"],
            root_path=tmp_path,
        )

        client._handle_diagnostics({
            "uri": "file:///file1.py",
            "diagnostics": [{"range": {"start": {"line": 0, "character": 0}, "end": {"line": 0, "character": 0}}, "severity": 1, "message": "Error", "source": "pyright"}],
        })

        assert len(client.get_all_diagnostics()) == 1

        client.clear_diagnostics()

        assert len(client.get_all_diagnostics()) == 0
