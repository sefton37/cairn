"""Tests for atomic_ops/executor.py - StateCapture and _extract_paths.

Coverage areas:
- StateCapture.__init__ error handling (permission denied on backup dir creation)
- StateCapture.capture_file_state with existing/missing files
- _extract_paths() path traversal rejection (paths with '..', /proc/, /sys/, /dev/)
- _extract_paths() normal path extraction from request strings
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from reos.atomic_ops.executor import StateCapture, OperationExecutor, ExecutionConfig


# =============================================================================
# StateCapture Tests
# =============================================================================


class TestStateCaptureInit:
    """Test StateCapture initialization and error handling."""

    def test_state_capture_init_success(self, tmp_path: Path) -> None:
        """StateCapture creates backup directory successfully."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        assert state_capture.backup_dir == backup_dir
        assert backup_dir.exists()
        assert backup_dir.is_dir()

    def test_state_capture_init_creates_parents(self, tmp_path: Path) -> None:
        """StateCapture creates parent directories when needed."""
        backup_dir = tmp_path / "nested" / "deep" / "backups"
        state_capture = StateCapture(str(backup_dir))

        assert backup_dir.exists()
        assert backup_dir.is_dir()

    def test_state_capture_init_permission_denied(self, tmp_path: Path) -> None:
        """StateCapture raises when backup directory creation fails due to permissions."""
        # Create a read-only parent directory
        readonly_parent = tmp_path / "readonly"
        readonly_parent.mkdir()
        readonly_parent.chmod(0o444)  # Read-only

        backup_dir = readonly_parent / "backups"

        try:
            with pytest.raises((PermissionError, OSError)) as exc_info:
                StateCapture(str(backup_dir))
            # Verify the error bubbles up
            assert exc_info.type in (PermissionError, OSError)
        finally:
            # Cleanup: restore write permissions
            readonly_parent.chmod(0o755)

    def test_state_capture_init_existing_directory(self, tmp_path: Path) -> None:
        """StateCapture succeeds when backup directory already exists."""
        backup_dir = tmp_path / "backups"
        backup_dir.mkdir()

        # Should not raise
        state_capture = StateCapture(str(backup_dir))
        assert state_capture.backup_dir == backup_dir


class TestStateCaptureFileState:
    """Test StateCapture.capture_file_state method."""

    def test_capture_file_state_existing_file(self, tmp_path: Path) -> None:
        """capture_file_state records state for existing files."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        # Create test file
        test_file = tmp_path / "test.txt"
        test_content = "test content"
        test_file.write_text(test_content)

        state = state_capture.capture_file_state([str(test_file)])

        assert str(test_file) in state
        file_state = state[str(test_file)]
        assert file_state["exists"] is True
        assert file_state["hash"] is not None
        assert isinstance(file_state["hash"], str)
        assert len(file_state["hash"]) == 64  # SHA256 hex digest
        assert file_state["size"] == len(test_content)
        assert file_state["mtime"] is not None
        assert file_state["backup_path"] is None  # Not yet backed up

    def test_capture_file_state_missing_file(self, tmp_path: Path) -> None:
        """capture_file_state records non-existence for missing files."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        missing_file = tmp_path / "does_not_exist.txt"

        state = state_capture.capture_file_state([str(missing_file)])

        assert str(missing_file) in state
        file_state = state[str(missing_file)]
        assert file_state["exists"] is False
        assert file_state["hash"] is None
        assert file_state["size"] == 0
        assert file_state["mtime"] is None
        assert file_state["backup_path"] is None

    def test_capture_file_state_multiple_files(self, tmp_path: Path) -> None:
        """capture_file_state handles multiple files."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        # Create some files
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file3 = tmp_path / "missing.txt"

        file1.write_text("content 1")
        file2.write_text("content 2")

        state = state_capture.capture_file_state([
            str(file1),
            str(file2),
            str(file3),
        ])

        assert len(state) == 3
        assert state[str(file1)]["exists"] is True
        assert state[str(file2)]["exists"] is True
        assert state[str(file3)]["exists"] is False

    def test_capture_file_state_empty_list(self, tmp_path: Path) -> None:
        """capture_file_state returns empty dict for empty input."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        state = state_capture.capture_file_state([])

        assert state == {}

    def test_capture_file_state_hash_changes(self, tmp_path: Path) -> None:
        """capture_file_state produces different hashes for different content."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        test_file = tmp_path / "test.txt"

        # Capture state with first content
        test_file.write_text("content version 1")
        state1 = state_capture.capture_file_state([str(test_file)])
        hash1 = state1[str(test_file)]["hash"]

        # Modify file and capture again
        test_file.write_text("content version 2")
        state2 = state_capture.capture_file_state([str(test_file)])
        hash2 = state2[str(test_file)]["hash"]

        # Hashes should differ
        assert hash1 != hash2


# =============================================================================
# _extract_paths Tests
# =============================================================================


class TestExtractPaths:
    """Test OperationExecutor._extract_paths method for path extraction and security."""

    @pytest.fixture
    def executor(self, tmp_path: Path) -> OperationExecutor:
        """Create an executor instance for testing."""
        config = ExecutionConfig(backup_dir=str(tmp_path / "backups"))
        return OperationExecutor(store=None, config=config)

    def test_extract_paths_normal_paths(self, executor: OperationExecutor) -> None:
        """_extract_paths extracts normal file paths from requests."""
        request = "Please edit /home/user/document.txt and /tmp/test.log"
        paths = executor._extract_paths(request)

        assert "/home/user/document.txt" in paths
        assert "/tmp/test.log" in paths

    def test_extract_paths_tilde_expansion(self, executor: OperationExecutor) -> None:
        """_extract_paths expands ~ to home directory."""
        request = "Check ~/config.yaml"
        paths = executor._extract_paths(request)

        # Should have expanded ~ to actual home path
        assert len(paths) >= 1
        # Expanded paths should not contain ~
        for path in paths:
            assert not path.startswith("~")

    def test_extract_paths_rejects_double_dot(self, executor: OperationExecutor) -> None:
        """_extract_paths rejects paths containing '..' (path traversal)."""
        request = "Read /home/user/../../../etc/passwd"
        paths = executor._extract_paths(request)

        # Path with .. should be rejected
        assert "/home/user/../../../etc/passwd" not in paths

    def test_extract_paths_rejects_proc(self, executor: OperationExecutor) -> None:
        """_extract_paths rejects paths in /proc/."""
        request = "Read /proc/self/environ and /proc/1/cmdline"
        paths = executor._extract_paths(request)

        # /proc paths should be rejected
        assert not any(p.startswith("/proc/") for p in paths)

    def test_extract_paths_rejects_sys(self, executor: OperationExecutor) -> None:
        """_extract_paths rejects paths in /sys/."""
        request = "Check /sys/class/net/eth0/address"
        paths = executor._extract_paths(request)

        # /sys paths should be rejected
        assert not any(p.startswith("/sys/") for p in paths)

    def test_extract_paths_rejects_dev(self, executor: OperationExecutor) -> None:
        """_extract_paths rejects paths in /dev/."""
        request = "Write to /dev/sda and /dev/null"
        paths = executor._extract_paths(request)

        # /dev paths should be rejected
        assert not any(p.startswith("/dev/") for p in paths)

    def test_extract_paths_mixed_valid_and_invalid(
        self, executor: OperationExecutor, tmp_path: Path
    ) -> None:
        """_extract_paths filters out suspicious paths but keeps valid ones."""
        request = f"Copy /tmp/safe.txt to {tmp_path}/output.txt and also read /proc/meminfo"
        paths = executor._extract_paths(request)

        # Should contain the safe paths
        assert "/tmp/safe.txt" in paths or any("safe.txt" in p for p in paths)
        # Should not contain /proc path
        assert not any("/proc/" in p for p in paths)

    def test_extract_paths_quoted_paths(self, executor: OperationExecutor) -> None:
        """_extract_paths extracts paths from quoted strings."""
        request = 'Edit "/home/user/my file.txt" and \'/tmp/another.log\''
        paths = executor._extract_paths(request)

        # Paths in quotes should be extracted
        assert any("my file.txt" in p or "/home/user/my" in p for p in paths)

    def test_extract_paths_no_paths(self, executor: OperationExecutor) -> None:
        """_extract_paths returns empty list when no paths present."""
        request = "What is the weather today?"
        paths = executor._extract_paths(request)

        assert paths == []

    def test_extract_paths_relative_paths_not_matched(
        self, executor: OperationExecutor
    ) -> None:
        """_extract_paths only matches absolute paths (starting with / or ~)."""
        request = "Edit document.txt and folder/file.txt"
        paths = executor._extract_paths(request)

        # Relative paths should not be matched by the regex
        assert "document.txt" not in paths
        assert "folder/file.txt" not in paths

    def test_extract_paths_proc_realpath_check(
        self, executor: OperationExecutor
    ) -> None:
        """_extract_paths checks realpath and rejects /proc/ paths."""
        # The function should reject /proc paths after resolving with realpath
        # Test with an explicit /proc path
        request = "Check files /proc/cpuinfo /proc/meminfo"
        paths = executor._extract_paths(request)

        # All /proc paths should be filtered out
        assert not any(p.startswith("/proc/") for p in paths), (
            f"Expected no /proc paths, got {paths}"
        )

    def test_extract_paths_multiple_slashes(self, executor: OperationExecutor) -> None:
        """_extract_paths handles paths with various formats."""
        request = "Check /home//user///file.txt"
        paths = executor._extract_paths(request)

        # Should extract the path (even with multiple slashes)
        assert len(paths) >= 1

    def test_extract_paths_with_dots_but_not_dotdot(
        self, executor: OperationExecutor
    ) -> None:
        """_extract_paths allows paths with single dots or dots in filenames."""
        request = "Read /home/user/./config.yaml and /home/user/.bashrc"
        paths = executor._extract_paths(request)

        # Single dot (.) is safe, as are dots in filenames
        # But the code checks for '..' in the original path string
        # So these should pass through
        assert any("config.yaml" in p for p in paths)
        assert any(".bashrc" in p for p in paths)

    def test_extract_paths_dotdot_in_original_string(
        self, executor: OperationExecutor
    ) -> None:
        """_extract_paths rejects paths with .. in the original string."""
        # The code checks: if '..' in p (before expansion)
        request = "Read /home/user/../etc/shadow"
        paths = executor._extract_paths(request)

        # Should be rejected because '..' is in the original path string
        assert len(paths) == 0 or "/home/user/../etc/shadow" not in paths


# =============================================================================
# Integration Tests
# =============================================================================


class TestStateCaptureIntegration:
    """Integration tests combining StateCapture components."""

    def test_state_capture_full_workflow(self, tmp_path: Path) -> None:
        """Test complete StateCapture workflow: init -> capture -> backup -> restore."""
        backup_dir = tmp_path / "backups"
        state_capture = StateCapture(str(backup_dir))

        # Create a test file
        test_file = tmp_path / "important.txt"
        original_content = "important data"
        test_file.write_text(original_content)

        # Capture state
        state_before = state_capture.capture_file_state([str(test_file)])
        assert state_before[str(test_file)]["exists"] is True

        # Backup the file
        backup_path = state_capture.backup_file(str(test_file))
        assert backup_path is not None
        assert Path(backup_path).exists()

        # Modify the file
        test_file.write_text("modified data")

        # Capture state after modification
        state_after = state_capture.capture_file_state([str(test_file)])
        assert state_after[str(test_file)]["hash"] != state_before[str(test_file)]["hash"]

        # Restore from backup
        restored = state_capture.restore_file(backup_path, str(test_file))
        assert restored is True

        # Verify restoration
        assert test_file.read_text() == original_content
