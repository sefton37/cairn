"""Tests for the unified ToolProvider system."""

from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode import CodeSandbox
from reos.code_mode.tools import (
    ToolCategory,
    ToolInfo,
    ToolResult,
    ToolProvider,
    SandboxToolProvider,
    CompositeToolProvider,
    NullToolProvider,
    create_tool_provider,
)


class TestToolResult:
    """Tests for ToolResult dataclass."""

    def test_successful_result(self) -> None:
        result = ToolResult(
            success=True,
            output="file contents here",
            source="sandbox.read_file",
        )
        assert result.success
        assert "file contents" in result.output
        assert result.error is None

    def test_failed_result(self) -> None:
        result = ToolResult(
            success=False,
            output="",
            error="File not found",
            source="sandbox.read_file",
        )
        assert not result.success
        assert result.error == "File not found"

    def test_to_context_success(self) -> None:
        result = ToolResult(
            success=True,
            output="def hello(): pass",
            source="sandbox.read_file",
        )
        context = result.to_context()
        assert "[Tool Result" in context
        assert "sandbox.read_file" in context
        assert "def hello()" in context

    def test_to_context_error(self) -> None:
        result = ToolResult(
            success=False,
            output="",
            error="Permission denied",
            source="sandbox.read_file",
        )
        context = result.to_context()
        assert "[Tool Error" in context
        assert "Permission denied" in context


class TestToolInfo:
    """Tests for ToolInfo dataclass."""

    def test_tool_info_creation(self) -> None:
        tool = ToolInfo(
            name="read_file",
            description="Read a file",
            category=ToolCategory.SANDBOX,
            input_schema={"type": "object"},
            use_when="need to read code",
        )
        assert tool.name == "read_file"
        assert tool.category == ToolCategory.SANDBOX


class TestSandboxToolProvider:
    """Tests for SandboxToolProvider."""

    def test_list_tools(self, temp_git_repo: Path) -> None:
        """Should list all sandbox tools."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        tools = provider.list_tools()

        assert len(tools) >= 5  # At least 5 tools
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names
        assert "grep" in tool_names
        assert "find_files" in tool_names
        assert "git_status" in tool_names

    def test_has_tool(self, temp_git_repo: Path) -> None:
        """Should check if tool exists."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        assert provider.has_tool("read_file")
        assert provider.has_tool("grep")
        assert not provider.has_tool("nonexistent_tool")

    def test_call_read_file(self, temp_git_repo: Path) -> None:
        """Should read file contents."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("read_file", {"path": "src/reos/example.py"})

        assert result.success
        assert "def hello()" in result.output
        assert result.source == "sandbox.read_file"

    def test_call_read_file_not_found(self, temp_git_repo: Path) -> None:
        """Should handle missing file."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("read_file", {"path": "nonexistent.py"})

        assert not result.success
        assert result.error is not None

    def test_call_grep(self, temp_git_repo: Path) -> None:
        """Should search for patterns."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("grep", {"pattern": "def hello"})

        assert result.success
        assert "example.py" in result.output or "hello" in result.output

    def test_call_find_files(self, temp_git_repo: Path) -> None:
        """Should find files by pattern."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("find_files", {"pattern": "**/*.py"})

        assert result.success
        assert "example.py" in result.output

    def test_call_git_status(self, temp_git_repo: Path) -> None:
        """Should get git status."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("git_status", {})

        assert result.success
        # Clean repo after initial commit
        assert "clean" in result.output.lower() or result.output

    def test_call_unknown_tool(self, temp_git_repo: Path) -> None:
        """Should handle unknown tool gracefully."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        result = provider.call_tool("nonexistent_tool", {})

        assert not result.success
        assert "Unknown tool" in result.error

    def test_implements_protocol(self, temp_git_repo: Path) -> None:
        """Should implement ToolProvider protocol."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = SandboxToolProvider(sandbox)

        assert isinstance(provider, ToolProvider)


class TestNullToolProvider:
    """Tests for NullToolProvider."""

    def test_list_tools_empty(self) -> None:
        """Should return empty list."""
        provider = NullToolProvider()
        assert provider.list_tools() == []

    def test_has_tool_false(self) -> None:
        """Should always return False."""
        provider = NullToolProvider()
        assert not provider.has_tool("anything")

    def test_call_tool_fails(self) -> None:
        """Should fail with disabled message."""
        provider = NullToolProvider()
        result = provider.call_tool("read_file", {"path": "test.py"})

        assert not result.success
        assert "disabled" in result.error.lower()


class TestCompositeToolProvider:
    """Tests for CompositeToolProvider."""

    def test_combines_tools(self, temp_git_repo: Path) -> None:
        """Should combine tools from multiple providers."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox_provider = SandboxToolProvider(sandbox)
        null_provider = NullToolProvider()

        composite = CompositeToolProvider([sandbox_provider, null_provider])
        tools = composite.list_tools()

        # Should have sandbox tools
        tool_names = [t.name for t in tools]
        assert "read_file" in tool_names

    def test_no_duplicates(self, temp_git_repo: Path) -> None:
        """Should not duplicate tool names."""
        sandbox = CodeSandbox(temp_git_repo)
        provider1 = SandboxToolProvider(sandbox)
        provider2 = SandboxToolProvider(sandbox)

        composite = CompositeToolProvider([provider1, provider2])
        tools = composite.list_tools()

        # Should only have one read_file
        read_file_count = sum(1 for t in tools if t.name == "read_file")
        assert read_file_count == 1

    def test_call_tool_first_provider(self, temp_git_repo: Path) -> None:
        """Should call tool from first provider that has it."""
        sandbox = CodeSandbox(temp_git_repo)
        sandbox_provider = SandboxToolProvider(sandbox)
        null_provider = NullToolProvider()

        composite = CompositeToolProvider([sandbox_provider, null_provider])
        result = composite.call_tool("read_file", {"path": "src/reos/example.py"})

        assert result.success
        assert "hello" in result.output

    def test_call_unknown_tool(self, temp_git_repo: Path) -> None:
        """Should fail for unknown tools."""
        sandbox = CodeSandbox(temp_git_repo)
        composite = CompositeToolProvider([SandboxToolProvider(sandbox)])

        result = composite.call_tool("unknown", {})

        assert not result.success
        assert "No provider" in result.error

    def test_add_provider(self, temp_git_repo: Path) -> None:
        """Should allow adding providers dynamically."""
        composite = CompositeToolProvider([NullToolProvider()])
        assert not composite.has_tool("read_file")

        sandbox = CodeSandbox(temp_git_repo)
        composite.add_provider(SandboxToolProvider(sandbox))

        assert composite.has_tool("read_file")


class TestCreateToolProvider:
    """Tests for the factory function."""

    def test_with_sandbox(self, temp_git_repo: Path) -> None:
        """Should create sandbox provider."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = create_tool_provider(sandbox=sandbox)

        assert provider.has_tool("read_file")

    def test_without_sandbox(self) -> None:
        """Should return null provider when nothing configured."""
        provider = create_tool_provider()

        assert isinstance(provider, NullToolProvider)
        assert not provider.has_tool("read_file")

    def test_provider_is_protocol(self, temp_git_repo: Path) -> None:
        """Factory should return ToolProvider compatible object."""
        sandbox = CodeSandbox(temp_git_repo)
        provider = create_tool_provider(sandbox=sandbox)

        # Should be able to call protocol methods
        tools = provider.list_tools()
        assert len(tools) > 0
