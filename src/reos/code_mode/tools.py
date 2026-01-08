"""Unified Tool Provider for Code Mode.

This module provides a unified interface for tools that RIVA can use
during code execution. It avoids duplication by wrapping existing
implementations (CodeSandbox, MCP tools, etc.) behind a common protocol.

The goal: When RIVA is uncertain or can't verify, it can call tools
to gather information, search for solutions, or fetch documentation.

Tool Categories:
1. Sandbox Tools - File operations within the repository
2. Web Tools - Search, fetch documentation, lookup errors
3. MCP Bridge - Access to external MCP servers (optional)
4. System Tools - Bridge to linux_tools (optional)

Usage:
    provider = SandboxToolProvider(sandbox)
    result = provider.call_tool("read_file", {"path": "src/main.py"})

    # Composite provider for multiple sources
    provider = CompositeToolProvider([
        SandboxToolProvider(sandbox),
        WebToolProvider(),
    ])
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from .sandbox import CodeSandbox

logger = logging.getLogger(__name__)


# =============================================================================
# Core Data Structures
# =============================================================================


class ToolCategory(Enum):
    """Categories of tools available to RIVA."""

    SANDBOX = "sandbox"      # File operations within repo
    WEB = "web"              # Web search, fetch, docs
    MCP = "mcp"              # External MCP servers
    SYSTEM = "system"        # Linux system tools


@dataclass(frozen=True)
class ToolInfo:
    """Metadata about an available tool."""

    name: str
    description: str
    category: ToolCategory
    input_schema: dict[str, Any] = field(default_factory=dict)

    # When should RIVA consider using this tool?
    use_when: str = ""  # e.g., "uncertain about API usage", "error debugging"


@dataclass
class ToolResult:
    """Result from calling a tool."""

    success: bool
    output: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    # Metadata for RIVA to understand the result
    confidence: float = 1.0  # How reliable is this result?
    source: str = ""         # Where did this come from?

    def to_context(self) -> str:
        """Format result as context for LLM prompt."""
        if self.success:
            return f"[Tool Result - {self.source}]\n{self.output}"
        else:
            return f"[Tool Error - {self.source}]\n{self.error}"


# =============================================================================
# Tool Provider Protocol
# =============================================================================


@runtime_checkable
class ToolProvider(Protocol):
    """Protocol for tool providers.

    Any class implementing this protocol can provide tools to RIVA.
    This allows composing multiple tool sources (sandbox, web, MCP, etc.)
    """

    def list_tools(self) -> list[ToolInfo]:
        """List all available tools from this provider."""
        ...

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a tool by name with given arguments."""
        ...

    def has_tool(self, name: str) -> bool:
        """Check if this provider has a tool with the given name."""
        ...


# =============================================================================
# Sandbox Tool Provider - Wraps CodeSandbox
# =============================================================================


class SandboxToolProvider:
    """Tool provider that wraps CodeSandbox methods.

    This avoids duplicating file operation logic - we just expose
    the existing sandbox methods through the ToolProvider interface.
    """

    def __init__(self, sandbox: "CodeSandbox") -> None:
        self._sandbox = sandbox
        self._tools = self._build_tool_list()

    def _build_tool_list(self) -> list[ToolInfo]:
        """Build list of available sandbox tools."""
        return [
            ToolInfo(
                name="read_file",
                description="Read contents of a file in the repository",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Relative path to file"},
                        "start_line": {"type": "integer", "description": "Starting line (1-indexed)"},
                        "end_line": {"type": "integer", "description": "Ending line (inclusive)"},
                    },
                    "required": ["path"],
                },
                use_when="need to understand existing code structure or content",
            ),
            ToolInfo(
                name="grep",
                description="Search for patterns in repository files",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Regex pattern to search"},
                        "path": {"type": "string", "description": "Path to search in (default: repo root)"},
                        "include_glob": {"type": "string", "description": "Glob pattern for files to include"},
                        "max_results": {"type": "integer", "description": "Maximum results (default: 50)"},
                    },
                    "required": ["pattern"],
                },
                use_when="looking for usage patterns, function definitions, or specific code",
            ),
            ToolInfo(
                name="find_files",
                description="Find files matching a glob pattern",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "pattern": {"type": "string", "description": "Glob pattern (e.g., '**/*.py')"},
                        "max_results": {"type": "integer", "description": "Maximum results"},
                    },
                    "required": ["pattern"],
                },
                use_when="exploring repository structure or finding related files",
            ),
            ToolInfo(
                name="get_structure",
                description="Get repository directory structure",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "max_depth": {"type": "integer", "description": "Maximum depth (default: 3)"},
                        "include_hidden": {"type": "boolean", "description": "Include hidden files"},
                    },
                },
                use_when="need overview of project layout",
            ),
            ToolInfo(
                name="git_status",
                description="Get current git status (modified files, staged changes)",
                category=ToolCategory.SANDBOX,
                input_schema={"type": "object", "properties": {}},
                use_when="need to understand current state of changes",
            ),
            ToolInfo(
                name="git_diff",
                description="Get diff of changes",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "staged": {"type": "boolean", "description": "Show staged changes only"},
                    },
                },
                use_when="need to see exactly what has changed",
            ),
            ToolInfo(
                name="run_command",
                description="Run a shell command in the repository",
                category=ToolCategory.SANDBOX,
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to run"},
                        "timeout": {"type": "integer", "description": "Timeout in seconds (default: 30)"},
                    },
                    "required": ["command"],
                },
                use_when="need to run tests, linters, or other commands",
            ),
        ]

    def list_tools(self) -> list[ToolInfo]:
        """List all sandbox tools."""
        return self._tools.copy()

    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return any(t.name == name for t in self._tools)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call a sandbox tool."""
        try:
            if name == "read_file":
                # Sandbox uses: read_file(path, start, end)
                content = self._sandbox.read_file(
                    path=arguments["path"],
                    start=arguments.get("start_line", 1),
                    end=arguments.get("end_line"),
                )
                return ToolResult(
                    success=True,
                    output=content,
                    source="sandbox.read_file",
                )

            elif name == "grep":
                # Sandbox uses: grep(pattern, glob_pattern, ignore_case, max_results)
                glob_pattern = arguments.get("include_glob", "**/*")
                matches = self._sandbox.grep(
                    pattern=arguments["pattern"],
                    glob_pattern=glob_pattern,
                    max_results=arguments.get("max_results", 50),
                )
                output_lines = []
                for m in matches:
                    output_lines.append(f"{m.path}:{m.line_number}: {m.line_content}")
                return ToolResult(
                    success=True,
                    output="\n".join(output_lines) if output_lines else "No matches found",
                    data={"matches": len(matches)},
                    source="sandbox.grep",
                )

            elif name == "find_files":
                # Sandbox uses: find_files(glob_pattern, ignore_patterns)
                files = self._sandbox.find_files(
                    glob_pattern=arguments["pattern"],
                )
                # Apply max_results limit manually
                max_results = arguments.get("max_results", 100)
                files = files[:max_results]
                return ToolResult(
                    success=True,
                    output="\n".join(files) if files else "No files found",
                    data={"count": len(files)},
                    source="sandbox.find_files",
                )

            elif name == "get_structure":
                structure = self._sandbox.get_structure(
                    max_depth=arguments.get("max_depth", 3),
                    include_hidden=arguments.get("include_hidden", False),
                )
                return ToolResult(
                    success=True,
                    output=structure,
                    source="sandbox.get_structure",
                )

            elif name == "git_status":
                status = self._sandbox.git_status()
                lines = []
                if status.modified:
                    lines.append(f"Modified: {', '.join(status.modified)}")
                if status.staged:
                    lines.append(f"Staged: {', '.join(status.staged)}")
                if status.untracked:
                    lines.append(f"Untracked: {', '.join(status.untracked)}")
                return ToolResult(
                    success=True,
                    output="\n".join(lines) if lines else "Working tree clean",
                    data={
                        "modified": status.modified,
                        "staged": status.staged,
                        "untracked": status.untracked,
                    },
                    source="sandbox.git_status",
                )

            elif name == "git_diff":
                diff = self._sandbox.git_diff(staged=arguments.get("staged", False))
                return ToolResult(
                    success=True,
                    output=diff if diff else "No changes",
                    source="sandbox.git_diff",
                )

            elif name == "run_command":
                result = self._sandbox.run_command(
                    command=arguments["command"],
                    timeout=arguments.get("timeout", 30),
                )
                return ToolResult(
                    success=result.returncode == 0,
                    output=result.stdout,
                    error=result.stderr if result.returncode != 0 else None,
                    data={"returncode": result.returncode},
                    source="sandbox.run_command",
                )

            else:
                return ToolResult(
                    success=False,
                    output="",
                    error=f"Unknown tool: {name}",
                    source="sandbox",
                )

        except Exception as e:
            logger.exception("Tool call failed: %s", name)
            return ToolResult(
                success=False,
                output="",
                error=str(e),
                source=f"sandbox.{name}",
            )


# =============================================================================
# Composite Tool Provider - Combines Multiple Providers
# =============================================================================


class CompositeToolProvider:
    """Combines multiple tool providers into one.

    Tools are searched in order - first provider with a matching tool wins.

    Usage:
        provider = CompositeToolProvider([
            SandboxToolProvider(sandbox),
            WebToolProvider(),
            MCPBridgeProvider(db),
        ])
    """

    def __init__(self, providers: list[ToolProvider]) -> None:
        self._providers = providers

    def list_tools(self) -> list[ToolInfo]:
        """List all tools from all providers."""
        all_tools: list[ToolInfo] = []
        seen_names: set[str] = set()

        for provider in self._providers:
            for tool in provider.list_tools():
                if tool.name not in seen_names:
                    all_tools.append(tool)
                    seen_names.add(tool.name)

        return all_tools

    def has_tool(self, name: str) -> bool:
        """Check if any provider has this tool."""
        return any(p.has_tool(name) for p in self._providers)

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        """Call tool from first provider that has it."""
        for provider in self._providers:
            if provider.has_tool(name):
                return provider.call_tool(name, arguments)

        return ToolResult(
            success=False,
            output="",
            error=f"No provider has tool: {name}",
            source="composite",
        )

    def add_provider(self, provider: ToolProvider) -> None:
        """Add a provider to the composite."""
        self._providers.append(provider)


# =============================================================================
# Null Tool Provider - For when tools are disabled
# =============================================================================


class NullToolProvider:
    """A tool provider that has no tools.

    Use this when tools are disabled or not configured.
    """

    def list_tools(self) -> list[ToolInfo]:
        return []

    def has_tool(self, name: str) -> bool:
        return False

    def call_tool(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(
            success=False,
            output="",
            error="Tools are disabled",
            source="null",
        )


# =============================================================================
# Factory Function
# =============================================================================


def create_tool_provider(
    sandbox: "CodeSandbox | None" = None,
    enable_web: bool = False,
    enable_mcp: bool = False,
) -> ToolProvider:
    """Create a tool provider with the specified capabilities.

    Args:
        sandbox: CodeSandbox for repository operations
        enable_web: Enable web search/fetch tools
        enable_mcp: Enable MCP bridge tools (Phase 5 - not yet implemented)

    Returns:
        A configured ToolProvider
    """
    providers: list[ToolProvider] = []

    if sandbox is not None:
        providers.append(SandboxToolProvider(sandbox))

    # Phase 3: Web tools for search and documentation
    if enable_web:
        from .web_tools import WebToolProvider
        providers.append(WebToolProvider())

    # Phase 5: MCP bridge (future)
    # if enable_mcp:
    #     providers.append(MCPBridgeProvider(db))

    if not providers:
        return NullToolProvider()

    if len(providers) == 1:
        return providers[0]

    return CompositeToolProvider(providers)
