"""Shared tool implementations for ReOS MCP + internal agent.

These tools are repo-scoped.

Repo selection is repo-first:
- If `REOS_REPO_PATH` is set, tools run against that repo.
- Otherwise, tools fall back to the workspace root if it is a git repo.

The MCP server wraps these results into MCP's `content` envelope.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .alignment import get_git_summary, is_git_repo
from .bash_executor import (
    approve_proposal,
    build_command_from_template,
    create_proposal,
    execute_proposal,
    get_proposal,
    suggest_command_from_intent,
)
from .db import Database
from .repo_discovery import discover_git_repos
from .repo_sandbox import RepoSandboxError, safe_repo_path
from .settings import settings

_JSON = dict[str, Any]


class ToolError(RuntimeError):
    def __init__(self, code: str, message: str, data: Any | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.data = data


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]


def list_tools() -> list[Tool]:
    return [
        Tool(
            name="reos_repo_discover",
            description="Discover git repos on disk (bounded scan) and store them in SQLite.",
            input_schema={"type": "object", "properties": {}},
        ),
        Tool(
            name="reos_git_summary",
            description=(
                "Return git summary for the current repo. Metadata-only by default; "
                "include_diff must be explicitly set true."
            ),
            input_schema={"type": "object", "properties": {"include_diff": {"type": "boolean"}}},
        ),
        Tool(
            name="reos_repo_grep",
            description="Search text within the current repo (bounded).",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "include_glob": {"type": "string", "description": "Glob like src/**/*.py"},
                    "max_results": {"type": "number"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="reos_repo_read_file",
            description="Read a file within the current repo (bounded) by line range.",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "start_line": {"type": "number"},
                    "end_line": {"type": "number"},
                },
                "required": ["path", "start_line", "end_line"],
            },
        ),
        Tool(
            name="reos_repo_list_files",
            description="List files within the current repo using a glob.",
            input_schema={
                "type": "object",
                "properties": {"glob": {"type": "string"}},
                "required": ["glob"],
            },
        ),
        Tool(
            name="reos_bash_suggest",
            description=(
                "Suggest a bash command from natural language intent. "
                "Returns a command template that may need parameters filled in."
            ),
            input_schema={
                "type": "object",
                "properties": {"intent": {"type": "string", "description": "Natural language description of what to do"}},
                "required": ["intent"],
            },
        ),
        Tool(
            name="reos_bash_propose",
            description=(
                "Propose a bash command for user approval. The command will be analyzed for risk "
                "and the user must approve before execution. Returns a proposal_id."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "The bash command to execute"},
                    "description": {"type": "string", "description": "Human-readable description of what the command does"},
                },
                "required": ["command", "description"],
            },
        ),
        Tool(
            name="reos_bash_execute",
            description=(
                "Execute an approved bash command. Requires a valid proposal_id that has been approved by the user."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "proposal_id": {"type": "string", "description": "The ID of the approved proposal"},
                    "timeout": {"type": "number", "description": "Timeout in seconds (default 30)"},
                },
                "required": ["proposal_id"],
            },
        ),
    ]


def _repo_root(db: Database) -> Path:
    state_repo_path = db.get_state(key="repo_path")
    if isinstance(state_repo_path, str) and state_repo_path.strip():
        candidate = Path(state_repo_path).resolve()
        if is_git_repo(candidate):
            return candidate

    if settings.repo_path is not None and is_git_repo(settings.repo_path):
        return settings.repo_path.resolve()

    if is_git_repo(settings.root_dir):
        return settings.root_dir.resolve()

    raise ToolError(
        code="no_repo_detected",
        message="No git repo detected.",
        data={"hint": "Set REOS_REPO_PATH or run ReOS inside a git repo."},
    )


def call_tool(db: Database, *, name: str, arguments: dict[str, Any] | None) -> Any:
    args = arguments or {}

    if name == "reos_repo_discover":
        repos = discover_git_repos()
        import uuid

        for repo_path in repos:
            db.upsert_repo(repo_id=str(uuid.uuid4()), path=str(repo_path))
        return {"discovered": len(repos)}

    if name == "reos_git_summary":
        include_diff = bool(args.get("include_diff", False))
        repo_root = _repo_root(db)
        summary = get_git_summary(repo_root, include_diff=include_diff)
        return {
            "repo": str(summary.repo_path),
            "branch": summary.branch,
            "changed_files": summary.changed_files,
            "diff_stat": summary.diff_stat,
            "status_porcelain": summary.status_porcelain,
            "diff": summary.diff_text if include_diff else None,
        }

    if name == "reos_repo_list_files":
        glob = args.get("glob")
        if not isinstance(glob, str) or not glob:
            raise ToolError(code="invalid_args", message="glob is required")
        repo_root = _repo_root(db)
        return sorted(
            [
                str(p.relative_to(repo_root))
                for p in repo_root.glob(glob)
                if p.is_file()
            ]
        )

    if name == "reos_repo_read_file":
        repo_root = _repo_root(db)
        path = args.get("path")
        start = args.get("start_line")
        end = args.get("end_line")

        if not isinstance(path, str) or not path:
            raise ToolError(code="invalid_args", message="path is required")
        if not isinstance(start, int | float) or not isinstance(end, int | float):
            raise ToolError(code="invalid_args", message="start_line/end_line must be numbers")

        start_i = int(start)
        end_i = int(end)
        if start_i < 1 or end_i < start_i:
            raise ToolError(code="invalid_args", message="Invalid line range")

        try:
            full_path = safe_repo_path(repo_root, path)
        except RepoSandboxError as exc:
            raise ToolError(code="path_escape", message=str(exc), data={"path": path}) from exc

        if not full_path.exists() or not full_path.is_file():
            raise ToolError(code="file_not_found", message="File not found", data={"path": path})

        max_lines = 400
        if end_i - start_i + 1 > max_lines:
            raise ToolError(code="range_too_large", message="Requested range too large", data={"max_lines": max_lines})

        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        return "\n".join(lines[start_i - 1 : end_i])

    if name == "reos_repo_grep":
        repo_root = _repo_root(db)
        query = args.get("query")
        include_glob = args.get("include_glob", "**/*.py")
        max_results = int(args.get("max_results", 50))

        if not isinstance(query, str) or not query:
            raise ToolError(code="invalid_args", message="query is required")
        if not isinstance(include_glob, str) or not include_glob:
            raise ToolError(code="invalid_args", message="include_glob must be a string")
        if max_results < 1 or max_results > 500:
            raise ToolError(code="invalid_args", message="max_results must be between 1 and 500")

        pattern = re.compile(re.escape(query), flags=re.IGNORECASE)
        results: list[_JSON] = []

        for file_path in repo_root.glob(include_glob):
            if not file_path.is_file():
                continue
            try:
                text = file_path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            for idx, line in enumerate(text.splitlines(), start=1):
                if pattern.search(line):
                    results.append(
                        {
                            "path": str(file_path.relative_to(repo_root)),
                            "line": idx,
                            "text": line[:400],
                        }
                    )
                    if len(results) >= max_results:
                        return results

        return results

    if name == "reos_bash_suggest":
        intent = args.get("intent")
        if not isinstance(intent, str) or not intent.strip():
            raise ToolError(code="invalid_args", message="intent is required")

        suggestion = suggest_command_from_intent(intent)
        if suggestion:
            return {
                "found": True,
                "template_name": suggestion["template_name"],
                "command_template": suggestion["command"],
                "description": suggestion["description"],
                "requires_params": suggestion["requires"],
                "optional_params": suggestion.get("optional", {}),
            }
        return {
            "found": False,
            "message": "No matching command template found. You can still propose a custom command.",
        }

    if name == "reos_bash_propose":
        command = args.get("command")
        description = args.get("description")

        if not isinstance(command, str) or not command.strip():
            raise ToolError(code="invalid_args", message="command is required")
        if not isinstance(description, str) or not description.strip():
            raise ToolError(code="invalid_args", message="description is required")

        proposal = create_proposal(command=command.strip(), description=description.strip())
        return proposal.to_dict()

    if name == "reos_bash_execute":
        proposal_id = args.get("proposal_id")
        timeout = int(args.get("timeout", 30))

        if not isinstance(proposal_id, str) or not proposal_id:
            raise ToolError(code="invalid_args", message="proposal_id is required")

        if timeout < 1 or timeout > 300:
            raise ToolError(code="invalid_args", message="timeout must be between 1 and 300 seconds")

        proposal = get_proposal(proposal_id)
        if not proposal:
            raise ToolError(code="proposal_not_found", message="Proposal not found or expired")

        if not proposal.approved:
            raise ToolError(
                code="not_approved",
                message="Command has not been approved by user. Wait for user to click 'Approve' button.",
            )

        if proposal.executed:
            raise ToolError(code="already_executed", message="This command has already been executed")

        result = execute_proposal(proposal_id, timeout=timeout)
        if not result:
            raise ToolError(code="execution_failed", message="Failed to execute command")

        return result.to_dict()

    raise ToolError(code="unknown_tool", message=f"Unknown tool: {name}")


def render_tool_result(result: Any) -> str:
    if result is None:
        return "null"
    if isinstance(result, str):
        return result
    return json.dumps(result, indent=2, ensure_ascii=False)
