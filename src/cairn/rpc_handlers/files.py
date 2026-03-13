"""RPC handlers for browsing and editing markdown files on the local filesystem.

Three methods enabling the Helm Android app to list, read, and write .md files:
- files/list  — recursive walk under a root directory, newest-first, capped at 500
- files/read  — read a single .md file, capped at 1 MB
- files/write — write a single .md file, capped at 1 MB, creates parent dirs

Security invariants (enforced in every method):
- Resolved absolute path must start with the allowed base directory (/home/kellogg/dev)
- Path may not contain '..' segments
- Only .md files are accepted for read/write
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cairn.db import Database
from cairn.rpc_handlers import RpcError

logger = logging.getLogger(__name__)

# The one directory tree Helm is permitted to touch.
_BASE_DIR = "/home/kellogg/dev"

# Directories skipped during recursive walk.
_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        "__pycache__",
        ".git",
        "venv",
        ".venv",
        "build",
        "dist",
    }
)

_MAX_FILES = 500
_MAX_BYTES = 1 * 1024 * 1024  # 1 MB


def _guard(path_str: str) -> Path:
    """Resolve *path_str* and verify it is inside _BASE_DIR.

    Raises RpcError with code -32602 (invalid params) if:
    - The path contains '..' segments
    - The resolved path escapes the base directory
    - The path does not end in '.md'
    """
    if ".." in Path(path_str).parts:
        raise RpcError(code=-32602, message="Path traversal rejected: '..' segment detected")

    resolved = Path(path_str).expanduser().resolve()
    if not str(resolved).startswith(_BASE_DIR):
        raise RpcError(
            code=-32602,
            message=f"Path traversal rejected: path must be under {_BASE_DIR}",
        )
    return resolved


def _guard_md(path_str: str) -> Path:
    """Like _guard but also enforces the .md extension."""
    resolved = _guard(path_str)
    if resolved.suffix.lower() != ".md":
        raise RpcError(code=-32602, message="Only .md files are permitted")
    return resolved


def handle_files_list(
    db: Database,  # noqa: ARG001 — kept for uniform handler signature
    *,
    root: str | None = None,
) -> dict[str, Any]:
    """Recursively list .md files under *root* (default: /home/kellogg/dev).

    Returns up to 500 files, sorted newest-first by modification time.
    Hidden directories and common noise directories are skipped.
    """
    root_str = root if root is not None else _BASE_DIR

    # Validate the root itself before walking it.
    if ".." in Path(root_str).parts:
        raise RpcError(code=-32602, message="Path traversal rejected: '..' segment detected")

    resolved_root = Path(root_str).expanduser().resolve()
    if not str(resolved_root).startswith(_BASE_DIR):
        raise RpcError(
            code=-32602,
            message=f"Root must be under {_BASE_DIR}",
        )
    if not resolved_root.is_dir():
        raise RpcError(code=-32602, message=f"Root is not a directory: {resolved_root}")

    logger.info("files/list root=%s", resolved_root)

    files: list[dict[str, Any]] = []

    def _walk(directory: Path) -> None:
        if len(files) >= _MAX_FILES:
            return
        try:
            entries = sorted(directory.iterdir(), key=lambda p: p.name)
        except PermissionError:
            return
        for entry in entries:
            if len(files) >= _MAX_FILES:
                break
            if entry.is_dir():
                # Skip hidden directories and known noise dirs.
                if entry.name.startswith(".") or entry.name in _SKIP_DIRS:
                    continue
                _walk(entry)
            elif entry.is_file() and entry.suffix.lower() == ".md":
                try:
                    stat = entry.stat()
                    files.append(
                        {
                            "path": str(entry),
                            "name": entry.name,
                            "size": stat.st_size,
                            "modified": stat.st_mtime,
                        }
                    )
                except OSError:
                    pass

    _walk(resolved_root)

    # Sort newest-first by modification time.
    files.sort(key=lambda f: f["modified"], reverse=True)

    return {"files": files}


def handle_files_read(
    db: Database,  # noqa: ARG001
    *,
    path: str,
) -> dict[str, Any]:
    """Read a single .md file and return its UTF-8 content.

    Enforces path traversal guard, .md-only restriction, and 1 MB size cap.
    """
    resolved = _guard_md(path)

    if not resolved.is_file():
        raise RpcError(code=-32003, message=f"File not found: {path}")

    size = resolved.stat().st_size
    if size > _MAX_BYTES:
        raise RpcError(
            code=-32602,
            message=f"File too large: {size} bytes (limit {_MAX_BYTES})",
        )

    logger.info("files/read path=%s size=%d", resolved, size)

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RpcError(code=-32603, message=f"File is not valid UTF-8: {exc}") from exc
    except OSError as exc:
        raise RpcError(code=-32603, message=f"Cannot read file: {exc}") from exc

    return {"path": str(resolved), "content": content}


def handle_files_write(
    db: Database,  # noqa: ARG001
    *,
    path: str,
    content: str,
) -> dict[str, Any]:
    """Write *content* to a .md file, creating parent directories as needed.

    Enforces path traversal guard, .md-only restriction, and 1 MB content cap.
    """
    resolved = _guard_md(path)

    encoded = content.encode("utf-8")
    if len(encoded) > _MAX_BYTES:
        raise RpcError(
            code=-32602,
            message=f"Content too large: {len(encoded)} bytes (limit {_MAX_BYTES})",
        )

    logger.info("files/write path=%s bytes=%d", resolved, len(encoded))

    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise RpcError(code=-32603, message=f"Cannot write file: {exc}") from exc

    return {"success": True, "path": str(resolved)}
