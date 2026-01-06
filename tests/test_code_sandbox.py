"""Tests for CodeSandbox - sandboxed file operations for Code Mode."""

from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode import CodeSandbox, CodeSandboxError


class TestCodeSandboxInit:
    """Tests for CodeSandbox initialization and validation."""

    def test_init_valid_git_repo(self, temp_git_repo: Path) -> None:
        """Should initialize successfully with a valid git repo."""
        sandbox = CodeSandbox(temp_git_repo)
        assert sandbox.repo_path == temp_git_repo.resolve()

    def test_init_string_path(self, temp_git_repo: Path) -> None:
        """Should accept string path."""
        sandbox = CodeSandbox(str(temp_git_repo))
        assert sandbox.repo_path == temp_git_repo.resolve()

    def test_init_nonexistent_path(self, tmp_path: Path) -> None:
        """Should raise error for non-existent path."""
        with pytest.raises(CodeSandboxError, match="does not exist"):
            CodeSandbox(tmp_path / "nonexistent")

    def test_init_not_a_directory(self, tmp_path: Path) -> None:
        """Should raise error when path is a file."""
        file_path = tmp_path / "file.txt"
        file_path.write_text("content")
        with pytest.raises(CodeSandboxError, match="not a directory"):
            CodeSandbox(file_path)

    def test_init_not_a_git_repo(self, tmp_path: Path) -> None:
        """Should raise error when directory isn't a git repo."""
        with pytest.raises(CodeSandboxError, match="Not a git repository"):
            CodeSandbox(tmp_path)


class TestSafePath:
    """Tests for path safety validation."""

    def test_safe_path_normal(self, temp_git_repo: Path) -> None:
        """Should resolve normal paths correctly."""
        sandbox = CodeSandbox(temp_git_repo)
        result = sandbox._safe_path("src/reos/example.py")
        assert result == temp_git_repo / "src" / "reos" / "example.py"

    def test_safe_path_strips_leading_slash(self, temp_git_repo: Path) -> None:
        """Should strip leading slashes."""
        sandbox = CodeSandbox(temp_git_repo)
        result = sandbox._safe_path("/src/reos/example.py")
        assert result == temp_git_repo / "src" / "reos" / "example.py"

    def test_safe_path_rejects_dotdot(self, temp_git_repo: Path) -> None:
        """Should reject paths with .."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="illegal"):
            sandbox._safe_path("../escape")

    def test_safe_path_rejects_empty(self, temp_git_repo: Path) -> None:
        """Should reject empty paths."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="required"):
            sandbox._safe_path("")

    def test_safe_path_rejects_escape_via_symlink(self, temp_git_repo: Path) -> None:
        """Should reject paths that escape via symlink resolution."""
        sandbox = CodeSandbox(temp_git_repo)
        # Create symlink pointing outside
        escape_link = temp_git_repo / "escape_link"
        escape_link.symlink_to(temp_git_repo.parent)

        with pytest.raises(CodeSandboxError, match="escapes"):
            sandbox._safe_path("escape_link/outside")


class TestFileOperations:
    """Tests for file read/write/edit/delete operations."""

    def test_read_file_existing(self, temp_git_repo: Path) -> None:
        """Should read existing file."""
        sandbox = CodeSandbox(temp_git_repo)
        content = sandbox.read_file("src/reos/example.py")
        assert "def hello()" in content

    def test_read_file_not_found(self, temp_git_repo: Path) -> None:
        """Should raise error for missing file."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="not found"):
            sandbox.read_file("nonexistent.py")

    def test_read_file_with_line_range(self, temp_git_repo: Path) -> None:
        """Should read specific line range."""
        sandbox = CodeSandbox(temp_git_repo)
        # example.py has 2 lines
        content = sandbox.read_file("src/reos/example.py", start=1, end=1)
        assert "def hello()" in content
        assert "return" not in content

    def test_write_file_new(self, temp_git_repo: Path) -> None:
        """Should create new file."""
        sandbox = CodeSandbox(temp_git_repo)
        result = sandbox.write_file("new_file.py", "# new content\n")

        assert result.created is True
        assert result.backup_path is None
        assert (temp_git_repo / "new_file.py").read_text() == "# new content\n"

    def test_write_file_overwrite_with_backup(self, temp_git_repo: Path) -> None:
        """Should create backup when overwriting."""
        sandbox = CodeSandbox(temp_git_repo)

        # Write initial content
        sandbox.write_file("test.py", "original")

        # Overwrite
        result = sandbox.write_file("test.py", "updated")

        assert result.created is False
        assert result.backup_path is not None
        assert (temp_git_repo / result.backup_path).read_text() == "original"
        assert (temp_git_repo / "test.py").read_text() == "updated"

    def test_write_file_creates_parent_dirs(self, temp_git_repo: Path) -> None:
        """Should create parent directories as needed."""
        sandbox = CodeSandbox(temp_git_repo)
        result = sandbox.write_file("new/nested/dir/file.py", "content")

        assert result.created is True
        assert (temp_git_repo / "new/nested/dir/file.py").read_text() == "content"

    def test_create_file_new(self, temp_git_repo: Path) -> None:
        """Should create new file."""
        sandbox = CodeSandbox(temp_git_repo)
        result = sandbox.create_file("brand_new.py", "# new")

        assert result.created is True
        assert (temp_git_repo / "brand_new.py").read_text() == "# new"

    def test_create_file_already_exists(self, temp_git_repo: Path) -> None:
        """Should fail if file already exists."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="already exists"):
            sandbox.create_file("src/reos/example.py", "new content")

    def test_edit_file_single_replacement(self, temp_git_repo: Path) -> None:
        """Should replace single occurrence."""
        sandbox = CodeSandbox(temp_git_repo)

        # Create test file
        sandbox.write_file("edit_test.py", "hello world")

        result = sandbox.edit_file("edit_test.py", "hello", "goodbye")

        assert result.replacements == 1
        assert (temp_git_repo / "edit_test.py").read_text() == "goodbye world"

    def test_edit_file_with_backup(self, temp_git_repo: Path) -> None:
        """Should create backup when editing."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("edit_test.py", "original content", backup=False)

        result = sandbox.edit_file("edit_test.py", "original", "modified")

        assert result.backup_path is not None
        assert (temp_git_repo / result.backup_path).read_text() == "original content"

    def test_edit_file_not_found(self, temp_git_repo: Path) -> None:
        """Should fail if file doesn't exist."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="not found"):
            sandbox.edit_file("nonexistent.py", "old", "new")

    def test_edit_file_text_not_found(self, temp_git_repo: Path) -> None:
        """Should fail if search text not in file."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("test.py", "some content")

        with pytest.raises(CodeSandboxError, match="not found"):
            sandbox.edit_file("test.py", "nonexistent", "new")

    def test_edit_file_multiple_matches_error(self, temp_git_repo: Path) -> None:
        """Should fail if text matches multiple times without replace_all."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("test.py", "hello hello hello")

        with pytest.raises(CodeSandboxError, match="matches 3 times"):
            sandbox.edit_file("test.py", "hello", "goodbye")

    def test_edit_file_replace_all(self, temp_git_repo: Path) -> None:
        """Should replace all occurrences with replace_all=True."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("test.py", "hello hello hello")

        result = sandbox.edit_file("test.py", "hello", "hi", replace_all=True)

        assert result.replacements == 3
        assert (temp_git_repo / "test.py").read_text() == "hi hi hi"

    def test_delete_file(self, temp_git_repo: Path) -> None:
        """Should delete file with backup."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("to_delete.py", "content", backup=False)

        result = sandbox.delete_file("to_delete.py")

        assert result.backup_path is not None
        assert not (temp_git_repo / "to_delete.py").exists()
        assert (temp_git_repo / result.backup_path).read_text() == "content"

    def test_delete_file_not_found(self, temp_git_repo: Path) -> None:
        """Should fail if file doesn't exist."""
        sandbox = CodeSandbox(temp_git_repo)
        with pytest.raises(CodeSandboxError, match="not found"):
            sandbox.delete_file("nonexistent.py")


class TestSearchOperations:
    """Tests for grep and find_files operations."""

    def test_grep_finds_matches(self, temp_git_repo: Path) -> None:
        """Should find regex matches in files."""
        sandbox = CodeSandbox(temp_git_repo)
        matches = sandbox.grep(r"def \w+", glob_pattern="**/*.py")

        assert len(matches) >= 1
        assert any(m.path == "src/reos/example.py" for m in matches)
        assert any("def hello" in m.line_content for m in matches)

    def test_grep_with_glob_filter(self, temp_git_repo: Path) -> None:
        """Should filter by glob pattern."""
        sandbox = CodeSandbox(temp_git_repo)

        # Only search markdown files
        matches = sandbox.grep(r"Roadmap", glob_pattern="**/*.md")

        assert len(matches) >= 1
        assert all(m.path.endswith(".md") for m in matches)

    def test_grep_case_insensitive(self, temp_git_repo: Path) -> None:
        """Should support case-insensitive search."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox.write_file("case_test.py", "HELLO World")

        matches = sandbox.grep("hello", glob_pattern="case_test.py", ignore_case=True)

        assert len(matches) == 1

    def test_grep_max_results(self, temp_git_repo: Path) -> None:
        """Should respect max_results limit."""
        sandbox = CodeSandbox(temp_git_repo)
        # Create file with many matches
        sandbox.write_file("many.py", "\n".join(f"line{i}" for i in range(100)))

        matches = sandbox.grep(r"line", glob_pattern="many.py", max_results=5)

        assert len(matches) == 5

    def test_find_files_all(self, temp_git_repo: Path) -> None:
        """Should find all files."""
        sandbox = CodeSandbox(temp_git_repo)
        files = sandbox.find_files("**/*")

        assert "src/reos/example.py" in files
        assert "docs/tech-roadmap.md" in files

    def test_find_files_with_pattern(self, temp_git_repo: Path) -> None:
        """Should filter by glob pattern."""
        sandbox = CodeSandbox(temp_git_repo)
        files = sandbox.find_files("**/*.py")

        assert all(f.endswith(".py") for f in files)

    def test_find_files_ignores_patterns(self, temp_git_repo: Path) -> None:
        """Should ignore specified patterns."""
        sandbox = CodeSandbox(temp_git_repo)

        # Default ignores __pycache__, .git, etc.
        files = sandbox.find_files("**/*")

        assert not any(".git" in f for f in files)

    def test_get_structure(self, temp_git_repo: Path) -> None:
        """Should return directory structure."""
        sandbox = CodeSandbox(temp_git_repo)
        structure = sandbox.get_structure(max_depth=2)

        # Should have repo root as key
        root_key = f"{temp_git_repo.name}/"
        assert root_key in structure

        # Should have nested directories
        root = structure[root_key]
        assert "src/" in root or "docs/" in root


class TestGitOperations:
    """Tests for git-related operations."""

    def test_git_status_clean_repo(self, temp_git_repo: Path) -> None:
        """Should report clean status for unmodified repo."""
        sandbox = CodeSandbox(temp_git_repo)
        status = sandbox.git_status()

        assert status.clean is True
        assert status.branch == "master" or status.branch == "main"
        assert status.staged == []
        assert status.modified == []
        assert status.untracked == []

    def test_git_status_with_changes(self, temp_git_repo: Path) -> None:
        """Should detect modified and untracked files."""
        sandbox = CodeSandbox(temp_git_repo)

        # Create untracked file
        (temp_git_repo / "untracked.py").write_text("new file")

        # Modify existing file
        (temp_git_repo / "src/reos/example.py").write_text("modified")

        status = sandbox.git_status()

        assert status.clean is False
        assert "untracked.py" in status.untracked
        assert "src/reos/example.py" in status.modified

    def test_git_diff_unstaged(self, temp_git_repo: Path) -> None:
        """Should show unstaged changes."""
        sandbox = CodeSandbox(temp_git_repo)

        # Modify file
        (temp_git_repo / "src/reos/example.py").write_text("modified content")

        diff = sandbox.git_diff(staged=False)

        assert "modified content" in diff or "example.py" in diff

    def test_recent_commits(self, temp_git_repo: Path) -> None:
        """Should return recent commits."""
        sandbox = CodeSandbox(temp_git_repo)
        commits = sandbox.recent_commits(count=5)

        assert len(commits) >= 1
        assert commits[0].sha
        assert commits[0].message == "initial"


class TestCommandExecution:
    """Tests for sandboxed command execution."""

    def test_run_command_success(self, temp_git_repo: Path) -> None:
        """Should run command and return output."""
        sandbox = CodeSandbox(temp_git_repo)
        returncode, stdout, stderr = sandbox.run_command("echo hello")

        assert returncode == 0
        assert "hello" in stdout

    def test_run_command_in_repo_dir(self, temp_git_repo: Path) -> None:
        """Should run command in repo directory."""
        sandbox = CodeSandbox(temp_git_repo)
        returncode, stdout, stderr = sandbox.run_command("pwd")

        assert returncode == 0
        assert str(temp_git_repo) in stdout

    def test_run_command_failure(self, temp_git_repo: Path) -> None:
        """Should return non-zero code for failed command."""
        sandbox = CodeSandbox(temp_git_repo)
        returncode, stdout, stderr = sandbox.run_command("exit 1")

        assert returncode == 1

    def test_run_command_timeout(self, temp_git_repo: Path) -> None:
        """Should timeout long-running commands."""
        sandbox = CodeSandbox(temp_git_repo)
        returncode, stdout, stderr = sandbox.run_command("sleep 10", timeout=1)

        assert returncode == -1
        assert "timed out" in stderr
