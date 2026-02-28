"""Repo sandbox: restrict file operations to a configured repo root.

Prevents path traversal attacks in MCP file tools by ensuring all
resolved paths remain within the declared repo root.
"""

from __future__ import annotations

from pathlib import Path


class RepoSandboxError(ValueError):
    """Raised when a path escapes the repo root."""


def safe_repo_path(repo_root: Path, rel_path: str) -> Path:
    """Resolve *rel_path* relative to *repo_root*, rejecting path traversal.

    Args:
        repo_root: Absolute path to the allowed repo root directory.
        rel_path: Relative path supplied by the caller (e.g. from MCP args).

    Returns:
        Absolute resolved path guaranteed to be inside *repo_root*.

    Raises:
        RepoSandboxError: If the resolved path escapes the repo root.
    """
    resolved = (repo_root / rel_path).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise RepoSandboxError(
            f"Path {rel_path!r} escapes the repo root {repo_root}"
        ) from None
    return resolved


__all__ = ["RepoSandboxError", "safe_repo_path"]
