"""Unit tests for the files/ RPC handler functions.

Tests verify:
- Path traversal guard blocks '..' segments and paths outside _BASE_DIR
- .md-only restriction is enforced for read/write
- Successful read/write using the real filesystem via tmp_path
- handle_files_list discovers .md files under a directory
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


# The allowed base directory as declared in the module under test.
_BASE_DIR = "/home/kellogg/dev"


def _mock_db() -> MagicMock:
    return MagicMock()


# =============================================================================
# handle_files_list
# =============================================================================


class TestHandleFilesList:
    """handle_files_list walks a directory and returns .md files."""

    def test_returns_md_files_in_directory(self, tmp_path) -> None:
        from cairn.rpc_handlers.files import handle_files_list

        md_file = tmp_path / "notes.md"
        md_file.write_text("# Notes")

        other = tmp_path / "ignored.txt"
        other.write_text("ignored")

        # Patch _BASE_DIR so tmp_path passes the guard
        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            result = handle_files_list(_mock_db(), root=str(tmp_path))

        assert len(result["files"]) == 1
        assert result["files"][0]["name"] == "notes.md"

    def test_raises_rpc_error_for_dot_dot_in_root(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_list

        with pytest.raises(RpcError) as exc_info:
            handle_files_list(_mock_db(), root=f"{_BASE_DIR}/../etc")

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_root_is_not_a_directory(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_list

        file_path = tmp_path / "file.txt"
        file_path.write_text("content")

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            with pytest.raises(RpcError) as exc_info:
                handle_files_list(_mock_db(), root=str(file_path))

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_root_escapes_base_dir(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_list

        with pytest.raises(RpcError) as exc_info:
            handle_files_list(_mock_db(), root="/etc")

        assert exc_info.value.code == -32602


# =============================================================================
# handle_files_read
# =============================================================================


class TestHandleFilesRead:
    """handle_files_read reads a .md file and returns its content."""

    def test_reads_md_file_content(self, tmp_path) -> None:
        from cairn.rpc_handlers.files import handle_files_read

        md_file = tmp_path / "readme.md"
        md_file.write_text("# Hello\nWorld")

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            result = handle_files_read(_mock_db(), path=str(md_file))

        assert result["content"] == "# Hello\nWorld"
        assert "readme.md" in result["path"]

    def test_raises_rpc_error_for_non_md_file(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_read

        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("content")

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            with pytest.raises(RpcError) as exc_info:
                handle_files_read(_mock_db(), path=str(txt_file))

        assert exc_info.value.code == -32602
        assert ".md" in exc_info.value.message

    def test_raises_rpc_error_when_file_not_found(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_read

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            with pytest.raises(RpcError) as exc_info:
                handle_files_read(_mock_db(), path=str(tmp_path / "missing.md"))

        assert exc_info.value.code == -32003

    def test_raises_rpc_error_for_dot_dot_path(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_read

        with pytest.raises(RpcError) as exc_info:
            handle_files_read(_mock_db(), path=f"{_BASE_DIR}/../etc/passwd.md")

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_file_escapes_base_dir(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_read

        with pytest.raises(RpcError) as exc_info:
            handle_files_read(_mock_db(), path="/tmp/secret.md")

        assert exc_info.value.code == -32602


# =============================================================================
# handle_files_write
# =============================================================================


class TestHandleFilesWrite:
    """handle_files_write writes content to a .md file."""

    def test_writes_md_file_successfully(self, tmp_path) -> None:
        from cairn.rpc_handlers.files import handle_files_write

        target = tmp_path / "new.md"

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            result = handle_files_write(_mock_db(), path=str(target), content="# New file")

        assert result["success"] is True
        assert target.read_text() == "# New file"

    def test_raises_rpc_error_for_non_md_path(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_write

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            with pytest.raises(RpcError) as exc_info:
                handle_files_write(_mock_db(), path=str(tmp_path / "file.py"), content="code")

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_content_exceeds_1mb(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.files import handle_files_write

        big_content = "x" * (1024 * 1024 + 1)
        target = tmp_path / "big.md"

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            with pytest.raises(RpcError) as exc_info:
                handle_files_write(_mock_db(), path=str(target), content=big_content)

        assert exc_info.value.code == -32602
        assert "too large" in exc_info.value.message

    def test_creates_parent_directories_if_missing(self, tmp_path) -> None:
        from cairn.rpc_handlers.files import handle_files_write

        nested = tmp_path / "a" / "b" / "c" / "notes.md"

        with patch("cairn.rpc_handlers.files._BASE_DIR", str(tmp_path)):
            result = handle_files_write(_mock_db(), path=str(nested), content="nested")

        assert result["success"] is True
        assert nested.read_text() == "nested"
