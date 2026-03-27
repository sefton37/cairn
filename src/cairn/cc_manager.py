"""Claude Code process manager — shared infrastructure for Talking Rock projects.

Manages Claude Code CLI processes: spawning, output parsing, event buffering,
and conversation history persistence. Used by Helm (Phase 2) and Cairn Tauri
(Phase 2.5) to run Claude Code sessions through Cairn's service layer.

Agent state persists in the host project's database (cc_agents, cc_history tables).
Process state is in-memory — processes are lost on application restart.

Database access and Cairn-specific callbacks are injected at construction time
via the CCDatabase protocol and optional callback parameters, removing all direct
dependencies on Cairn internals.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from cairn.cc_db import CCDatabase
from cairn.errors import RpcError

logger = logging.getLogger(__name__)

WORKSPACE_ROOT = Path.home() / "dev" / "talkingrock" / "agents"
MAX_EVENTS = 10_000


def _slugify(name: str) -> str:
    """Convert a name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9-]", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")
    return slug


@dataclass
class AgentProcess:
    """In-memory state for a running Claude Code process."""

    agent_id: str
    proc: asyncio.subprocess.Process | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    busy: bool = False
    partial_text: str = ""
    _read_task: asyncio.Task[None] | None = field(default=None, repr=False)


class CCManager:
    """Manages Claude Code agent lifecycle and process spawning.

    Database operations use the injected CCDatabase adapter (cc_agents, cc_history tables).
    Process state is in-memory (dict of AgentProcess).

    Optional callbacks for Cairn-specific behavior:
    - on_session_complete: called after each assistant response with session data
    - context_injector: called to prepend context (e.g. memories) to user messages
    """

    def __init__(
        self,
        db: CCDatabase,
        *,
        on_session_complete: Callable[..., None] | None = None,
        context_injector: Callable[[str], str] | None = None,
    ) -> None:
        self._db = db
        self._procs: dict[str, AgentProcess] = {}
        self._clean_env = {
            k: v
            for k, v in os.environ.items()
            if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")
        }
        self._on_session_complete = on_session_complete
        self._context_injector = context_injector

    # --- Agent CRUD (database) ---

    def list_agents(self, username: str) -> list[dict[str, Any]]:
        """List all agents for a user."""
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT id, name, slug, purpose, cwd FROM cc_agents WHERE username = ? ORDER BY created_at",
            (username,),
        ).fetchall()
        result = []
        for row in rows:
            agent_id = row["id"]
            ap = self._procs.get(agent_id)
            result.append(
                {
                    "id": agent_id,
                    "name": row["name"],
                    "slug": row["slug"],
                    "purpose": row["purpose"] or "",
                    "busy": ap.busy if ap else False,
                }
            )
        return result

    def create_agent(self, username: str, name: str, purpose: str = "") -> dict[str, Any]:
        """Create a new agent with workspace directory."""
        slug = _slugify(name)
        if not slug:
            raise RpcError(code=-32000, message="Invalid agent name")

        agent_id = uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        cwd = str(WORKSPACE_ROOT / slug)

        with self._db.transaction() as conn:
            try:
                conn.execute(
                    """INSERT INTO cc_agents (id, username, name, slug, purpose, cwd, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (agent_id, username, name, slug, purpose, cwd, now, now),
                )
            except Exception as exc:
                if "UNIQUE" in str(exc):
                    raise RpcError(
                        code=-32000, message=f'Agent with slug "{slug}" already exists'
                    ) from exc
                raise

        # Create synthetic conversation as FK target for memories (Phase 4)
        self._create_synthetic_conversation(agent_id)

        # Set up workspace directory
        self._setup_workspace(name, slug, purpose, cwd)

        return {
            "id": agent_id,
            "name": name,
            "slug": slug,
            "purpose": purpose,
            "cwd": cwd,
        }

    def delete_agent(self, agent_id: str) -> dict[str, Any]:
        """Delete an agent. Kills running process. Preserves workspace on disk."""
        conn = self._db.get_connection()
        row = conn.execute("SELECT id FROM cc_agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            raise RpcError(code=-32003, message="Agent not found")

        # Kill process if running
        ap = self._procs.pop(agent_id, None)
        if ap and ap.proc and ap.proc.returncode is None:
            ap.proc.terminate()

        with self._db.transaction() as conn:
            conn.execute("DELETE FROM cc_agents WHERE id = ?", (agent_id,))

        return {"ok": True}

    # --- Session (process management) ---

    async def send_message(self, agent_id: str, text: str) -> dict[str, Any]:
        """Send a message to an agent. Spawns a Claude Code process."""
        conn = self._db.get_connection()
        row = conn.execute(
            "SELECT id, cwd, session_id FROM cc_agents WHERE id = ?", (agent_id,)
        ).fetchone()
        if not row:
            raise RpcError(code=-32003, message="Agent not found")

        ap = self._procs.get(agent_id)
        if ap is None:
            ap = AgentProcess(agent_id=agent_id)
            self._procs[agent_id] = ap

        if ap.busy:
            raise RpcError(code=-32000, message="Agent is busy")

        # Inject relevant context (e.g. approved memories) into the prompt
        text = self._inject_context(text)

        # Record user message
        ap.events.append({"type": "user", "text": text})
        self._persist_history(agent_id, "user", text)

        # Spawn process
        ap.busy = True
        ap.partial_text = ""

        args = [
            "claude",
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--include-partial-messages",
            "--permission-mode",
            "acceptEdits",
        ]

        session_id = row["session_id"]
        if session_id:
            args.extend(["--resume", session_id])

        args.append(text)

        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                cwd=row["cwd"],
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._clean_env,
            )
        except Exception as exc:
            ap.busy = False
            ap.events.append({"type": "error", "text": f"Failed to start claude: {exc}"})
            ap.events.append({"type": "done"})
            raise RpcError(code=-32000, message=f"Failed to spawn claude: {exc}") from exc

        ap.proc = proc
        ap._read_task = asyncio.create_task(self._read_output(agent_id, proc))

        return {"agent_id": agent_id, "status": "accepted"}

    def poll_events(self, agent_id: str, since: int = 0) -> dict[str, Any]:
        """Return events since index. Non-blocking."""
        ap = self._procs.get(agent_id)
        if ap is None:
            return {"events": [], "next_index": since, "busy": False}

        events = ap.events[since:]
        # Prune if buffer too large
        if len(ap.events) > MAX_EVENTS:
            ap.events = ap.events[-MAX_EVENTS:]

        return {
            "events": events,
            "next_index": len(ap.events),
            "busy": ap.busy,
        }

    async def stop_session(self, agent_id: str) -> dict[str, Any]:
        """Kill a running process. SIGTERM then SIGKILL after 5s."""
        ap = self._procs.get(agent_id)
        if ap and ap.proc and ap.proc.returncode is None:
            ap.proc.terminate()
            try:
                await asyncio.wait_for(ap.proc.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                ap.proc.kill()
            ap.busy = False
            ap.events.append({"type": "done"})
        return {"ok": True}

    def get_history(self, agent_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Return conversation history from cc_history table."""
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT role, content, created_at FROM cc_history WHERE agent_id = ? ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        # Return in chronological order
        return [
            {"role": r["role"], "content": r["content"], "created_at": r["created_at"]}
            for r in reversed(rows)
        ]

    # --- Streaming (for SSE) ---

    async def stream_events(self, agent_id: str, since: int = 0) -> Any:
        """Async generator yielding events as they arrive. For SSE endpoint."""
        idx = since
        while True:
            ap = self._procs.get(agent_id)
            if ap is None:
                return

            if idx < len(ap.events):
                for event in ap.events[idx:]:
                    yield event
                    idx += 1
                    if event.get("type") == "done":
                        return
            elif not ap.busy:
                return
            else:
                await asyncio.sleep(0.15)

    # --- Internal helpers ---

    async def _read_output(self, agent_id: str, proc: asyncio.subprocess.Process) -> None:
        """Background task: read stdout line-by-line, parse stream-json, buffer events."""
        ap = self._procs.get(agent_id)
        if not ap:
            return

        assistant_text = ""
        current_partial = ""
        stderr_buf = ""

        # Read stderr in background
        async def _drain_stderr() -> None:
            nonlocal stderr_buf
            assert proc.stderr is not None
            while True:
                chunk = await proc.stderr.read(4096)
                if not chunk:
                    break
                if len(stderr_buf) < 65536:
                    stderr_buf += chunk.decode(errors="replace")

        stderr_task = asyncio.create_task(_drain_stderr())

        try:
            assert proc.stdout is not None
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break

                try:
                    msg = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue

                if msg.get("type") == "assistant" and msg.get("message", {}).get("content"):
                    for block in msg["message"]["content"]:
                        if block.get("type") == "text" and block.get("text"):
                            new_text = block["text"][len(current_partial):]
                            if new_text:
                                current_partial = block["text"]
                                ap.partial_text = block["text"]
                                ap.events.append(
                                    {"type": "assistant_delta", "text": new_text}
                                )

                        elif block.get("type") == "tool_use":
                            ap.events.append(
                                {
                                    "type": "tool_use",
                                    "tool": block.get("name", ""),
                                    "input": _summarize_tool_input(
                                        block.get("name", ""), block.get("input")
                                    ),
                                }
                            )

                        elif block.get("type") == "tool_result":
                            content = block.get("content", "")
                            if not isinstance(content, str):
                                content = json.dumps(content)
                            ap.events.append(
                                {
                                    "type": "tool_result",
                                    "text": content[:500],
                                    "is_error": block.get("is_error", False),
                                }
                            )

                elif msg.get("type") == "result":
                    session_id = msg.get("session_id")
                    if session_id:
                        self._update_session_id(agent_id, session_id)
                    result_text = msg.get("result", "")
                    if result_text:
                        remaining = result_text[len(current_partial):]
                        if remaining:
                            ap.events.append({"type": "assistant_delta", "text": remaining})
                        assistant_text = result_text
                        ap.partial_text = result_text

        except Exception as exc:
            logger.exception("Error reading claude output for agent %s", agent_id)
            ap.events.append({"type": "error", "text": str(exc)})

        # Wait for process exit and stderr drain
        await proc.wait()
        await stderr_task

        # Persist assistant response or error
        if assistant_text:
            self._persist_history(agent_id, "assistant", assistant_text)
        elif stderr_buf.strip():
            err_msg = f"Error: {stderr_buf.strip()}"
            self._persist_history(agent_id, "error", err_msg)
            ap.events.append({"type": "error", "text": err_msg})

        ap.partial_text = ""
        ap.busy = False
        ap.proc = None
        ap.events.append({"type": "done"})

        # Submit completed session to callback (e.g. session observer in Cairn)
        if assistant_text:
            self._submit_to_observer(agent_id)

    def _persist_history(self, agent_id: str, role: str, content: str) -> None:
        """Save a message to cc_history."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "INSERT INTO cc_history (agent_id, role, content, created_at) VALUES (?, ?, ?, ?)",
                    (agent_id, role, content, now),
                )
        except Exception:
            logger.exception("Failed to persist cc_history for agent %s", agent_id)

    def _update_session_id(self, agent_id: str, session_id: str) -> None:
        """Update the Claude Code session_id for resume support."""
        now = datetime.now(timezone.utc).isoformat()
        try:
            with self._db.transaction() as conn:
                conn.execute(
                    "UPDATE cc_agents SET session_id = ?, updated_at = ? WHERE id = ?",
                    (session_id, now, agent_id),
                )
        except Exception:
            logger.exception("Failed to update session_id for agent %s", agent_id)

    def _build_session_transcript(
        self, agent_id: str, limit: int = 50
    ) -> tuple[str, dict[str, Any]]:
        """Build a condensed transcript and stats for post-session analysis.

        Reads from cc_history (persistent), not ap.events (ephemeral).
        Only includes user and assistant turns — errors and tool output are excluded.

        Returns:
            (transcript_text, stats_dict)
        """
        conn = self._db.get_connection()
        rows = conn.execute(
            "SELECT role, content FROM cc_history WHERE agent_id = ? AND role IN ('user', 'assistant') "
            "ORDER BY id DESC LIMIT ?",
            (agent_id, limit),
        ).fetchall()
        rows = list(reversed(rows))

        parts = []
        user_count = 0
        assistant_count = 0
        for row in rows:
            role = row["role"]
            parts.append(f"[{role}]: {row['content']}")
            if role == "user":
                user_count += 1
            elif role == "assistant":
                assistant_count += 1

        transcript = "\n\n".join(parts)
        stats = {
            "user_messages": user_count,
            "assistant_messages": assistant_count,
            "files_touched": [],  # populated by _submit_to_observer from ap.events
        }
        return transcript, stats

    def _submit_to_observer(self, agent_id: str) -> None:
        """Build session context and notify the on_session_complete callback.

        Fire-and-forget: all exceptions are swallowed. The observer must never
        affect the session completion path.

        Builds the transcript and stats, then calls on_session_complete with
        keyword arguments: agent_id, agent_name, agent_purpose, transcript, stats.
        """
        if not self._on_session_complete:
            return
        try:
            conn = self._db.get_connection()
            row = conn.execute(
                "SELECT name, purpose FROM cc_agents WHERE id = ?", (agent_id,)
            ).fetchone()
            if not row:
                return

            transcript, stats = self._build_session_transcript(agent_id)
            if not transcript.strip():
                return

            # Supplement with in-memory file list before buffer is pruned
            ap = self._procs.get(agent_id)
            if ap:
                files = [
                    e["input"]
                    for e in ap.events
                    if e.get("type") == "tool_use"
                    and e.get("tool") in ("Read", "Write", "Edit")
                    and e.get("input")
                ]
                stats["files_touched"] = list(dict.fromkeys(files))[:20]

            self._on_session_complete(
                agent_id=agent_id,
                agent_name=row["name"],
                agent_purpose=row["purpose"] or "",
                transcript=transcript,
                stats=stats,
            )
        except Exception:
            logger.exception("Failed to submit agent %s to session observer", agent_id)

    def _inject_context(self, text: str) -> str:
        """Prepend context to the prompt via the context_injector callback.

        Only invoked if a context_injector was provided at construction time.
        Returns original text unchanged if injection fails or is not configured.
        """
        if self._context_injector:
            try:
                return self._context_injector(text)
            except Exception:
                logger.warning("Context injection failed, proceeding without")
        return text

    def _create_synthetic_conversation(self, agent_id: str) -> None:
        """Create a synthetic archived conversation as FK target for cc memories.

        Same pattern as _create_system_signals_conversation in play_db.py.
        """
        try:
            conv_id = f"cc-{agent_id}"
            block_id = f"block-cc-{agent_id}"
            now = datetime.now(timezone.utc).isoformat()
            with self._db.transaction() as conn:
                conn.execute(
                    """INSERT INTO blocks (id, type, act_id, parent_id, page_id, scene_id,
                       position, created_at, updated_at)
                       VALUES (?, 'conversation', ?, NULL, NULL, NULL, 0, ?, ?)""",
                    (block_id, "archived-conversations", now, now),
                )
                conn.execute(
                    """INSERT INTO conversations (id, block_id, status, started_at, archived_at)
                       VALUES (?, ?, 'archived', ?, ?)""",
                    (conv_id, block_id, now, now),
                )
        except Exception:
            logger.exception("Failed to create synthetic conversation for agent %s", agent_id)

    def _setup_workspace(self, name: str, slug: str, purpose: str, cwd: str) -> None:
        """Create agent workspace directory with CLAUDE.md, README.md, .gitignore, git init."""
        workspace = Path(cwd)
        workspace.mkdir(parents=True, exist_ok=True)

        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        claude_md = f"""# {name}

## Purpose

{purpose or 'General-purpose Claude Code agent.'}

## Workspace

Talking Rock agent workspace, created via Cairn on {date}.
Work within this directory. Reference sibling projects in /home/kellogg/dev/
as needed but do not modify them without explicit approval.

## Conventions

- Global CLAUDE.md workflow applies (loaded automatically by Claude Code)
- Commit meaningful checkpoints with clear messages
- Update this file if scope or purpose evolves
"""

        readme_md = f"""# {name}

**Purpose:** {purpose or 'General-purpose Claude Code agent.'}

**Created:** {date}
**Workspace:** `{cwd}`
"""

        gitignore = """node_modules/
__pycache__/
.env
*.pyc
.DS_Store
"""

        (workspace / "CLAUDE.md").write_text(claude_md, encoding="utf-8")
        (workspace / "README.md").write_text(readme_md, encoding="utf-8")
        (workspace / ".gitignore").write_text(gitignore, encoding="utf-8")

        try:
            import subprocess

            subprocess.run(
                ["git", "init"],
                cwd=cwd,
                capture_output=True,
                check=False,
            )
            subprocess.run(
                ["git", "add", "-A"],
                cwd=cwd,
                capture_output=True,
                check=False,
            )
            subprocess.run(
                ["git", "commit", "-m", "chore: workspace created by Cairn"],
                cwd=cwd,
                capture_output=True,
                check=False,
            )
        except Exception:
            pass  # Git not available


def _summarize_tool_input(tool: str, tool_input: Any) -> str:
    """Summarize tool inputs for display."""
    if not tool_input:
        return ""
    if isinstance(tool_input, dict):
        match tool:
            case "Bash":
                return tool_input.get("command", "")
            case "Read" | "Write" | "Edit":
                return tool_input.get("file_path", "")
            case "Glob":
                return tool_input.get("pattern", "")
            case "Grep":
                return f"{tool_input.get('pattern', '')} {tool_input.get('path', '')}".strip()
            case "WebFetch":
                return tool_input.get("url", "")
            case "WebSearch":
                return tool_input.get("query", "")
            case _:
                return json.dumps(tool_input)[:120]
    return str(tool_input)[:120]
