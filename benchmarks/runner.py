"""Benchmark runner for Cairn MCP tools.

Exercises the full Cairn agent pipeline (NL → tool selection → tool call →
response) per (test_case × persona × model) and records results to SQLite.

Mirrors ReOS/benchmarks/runner.py structure adapted for Cairn's multi-step
tool call pipeline.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import signal
import sqlite3
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

# Ensure Cairn src is importable
CAIRN_SRC = Path(__file__).parent.parent / "src"
if str(CAIRN_SRC) not in sys.path:
    sys.path.insert(0, str(CAIRN_SRC))

# Ensure tools/ is importable (for harness.mock_thunderbird)
TOOLS_DIR = Path(__file__).parent.parent / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from benchmarks.corpus import (
    TestCase,
    PersonaProfile,
    expand_with_personas,
    load_corpus,
    load_persona_profiles,
)
from benchmarks.db import get_completed_cases, init_db, upsert_test_cases
from benchmarks.matching import score_result
from benchmarks.models import get_model_info, is_anthropic_model


def _host_info() -> str:
    """Collect host information as JSON string."""
    info = {
        "hostname": platform.node(),
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "unknown",
    }
    # Try to get RAM
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    info["ram_gb"] = round(kb / 1024 / 1024, 1)
                    break
    except Exception:
        pass
    return json.dumps(info)


def _extract_tool_call(events: list) -> dict[str, Any]:
    """Extract tool call data from ConsciousnessObserver events.

    Returns dict with tool_selected, tool_args, tool_execution_ok, tool_error.
    """
    result: dict[str, Any] = {
        "tool_selected": None,
        "tool_args": None,
        "tool_execution_ok": None,
        "tool_error": None,
    }
    for ev in events:
        name = ev.event_type.name

        if name == "TOOL_CALL_START":
            result["tool_selected"] = ev.metadata.get("tool")
            args = ev.metadata.get("args")
            result["tool_args"] = json.dumps(args) if args else None

        elif name == "TOOL_CALL_COMPLETE":
            result["tool_execution_ok"] = 1

        elif name == "TOOL_CALL_ERROR":
            result["tool_execution_ok"] = 0
            result["tool_error"] = ev.metadata.get("error") or ev.content[:500]

    # If we saw a start but no complete/error, mark as failed
    if result["tool_selected"] and result["tool_execution_ok"] is None:
        result["tool_execution_ok"] = 0
        result["tool_error"] = "Tool call started but never completed"

    return result


@contextmanager
def _timeout_context(seconds: int):
    """Context manager that raises TimeoutError after N seconds.

    Uses SIGALRM on Linux/macOS (main thread only).
    Falls back to no-op on Windows or in threads.
    """
    if not hasattr(signal, "SIGALRM"):
        yield
        return

    def handler(signum, frame):
        raise TimeoutError(f"Timeout after {seconds}s")

    old = signal.signal(signal.SIGALRM, handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


class BenchmarkRunner:
    """Runs benchmark cases through the Cairn agent pipeline."""

    def __init__(
        self,
        model_name: str,
        tool_filter: str | None = None,
        variant_filter: str | None = None,
        resume: bool = False,
        db_path: str | None = None,
        ollama_url: str | None = None,
        timeout: int = 120,
        anthropic_key: str | None = None,
        corpus_file: Path | None = None,
    ) -> None:
        self.model_name = model_name
        self.tool_filter = tool_filter
        self.variant_filter = variant_filter
        self.resume = resume
        self.db_path = db_path
        self.ollama_url = ollama_url or "http://localhost:11434"
        self.timeout = timeout
        self.anthropic_key = anthropic_key
        self.corpus_file = corpus_file

        self._conn: sqlite3.Connection | None = None
        self._run_id: int | None = None
        self._run_uuid: str | None = None
        self._is_anthropic = is_anthropic_model(model_name)

    def run(self) -> str:
        """Run the benchmark. Returns run_uuid."""
        self._conn = init_db(self.db_path)
        self._run_uuid = str(uuid.uuid4())

        # Load corpus and personas
        cases = load_corpus(
            tool_name=self.tool_filter,
            variant=self.variant_filter,
            corpus_file=self.corpus_file,
        )
        profiles = load_persona_profiles()

        if not cases:
            print("No test cases match filters.")
            return self._run_uuid
        if not profiles:
            print("No persona profiles found.")
            return self._run_uuid

        # Upsert test cases to DB
        upsert_test_cases(self._conn, [c.to_db_dict() for c in cases])

        # Expand with personas
        triples = expand_with_personas(cases, profiles)

        # Get already-completed for resume
        done = set()
        if self.resume:
            done = get_completed_cases(self._conn, self.model_name)

        # Filter out completed
        remaining = [
            (c, p, s) for c, p, s in triples if (c.case_id, p.persona_id) not in done
        ]

        if not remaining:
            print("All cases already completed for this model.")
            return self._run_uuid

        # Create run record
        model_info = get_model_info(self.model_name) or {}
        self._run_id = self._create_run(model_info)

        total = len(remaining)
        skipped = len(triples) - len(remaining)

        print(f"\n{'=' * 60}")
        print(f"Cairn Benchmark")
        print(f"Model:    {self.model_name}")
        print(f"Run:      {self._run_uuid}")
        print(f"Cases:    {len(cases)} base × {len(profiles)} personas = {len(triples)} total")
        if skipped:
            print(f"Skipped:  {skipped} (already completed)")
        print(f"Running:  {total}")
        print(f"Timeout:  {self.timeout}s per case")
        print(f"{'=' * 60}\n")

        completed = 0
        errors = 0

        for i, (case, profile, styled_prompt) in enumerate(remaining):
            prefix = f"[{i + 1}/{total}] {case.case_id} ({profile.persona_id})"
            print(f"  {prefix:<70} ", end="", flush=True)

            try:
                result = self._run_case(case, profile, styled_prompt)
                self._write_result(case, profile, styled_prompt, result)
                completed += 1

                tool = result.get("tool_selected") or "-"
                ms = result.get("latency_ms", 0)
                match_str = "MATCH" if result.get("tool_match") else "MISS"
                print(f"{ms:>5}ms {tool:<30} {match_str}")

            except Exception as e:
                errors += 1
                self._write_error(case, profile, styled_prompt, str(e))
                print(f"ERR: {e}")

        # Finalize
        self._conn.execute(
            "UPDATE benchmark_runs SET completed_at = ? WHERE id = ?",
            (int(time.time() * 1000), self._run_id),
        )
        self._conn.commit()

        print(f"\n{'=' * 60}")
        print(f"Complete: {completed}  Errors: {errors}  Skipped: {skipped}")
        print(f"{'=' * 60}\n")

        return self._run_uuid

    def _create_run(self, model_info: dict) -> int:
        """Create a benchmark_runs row and return its id."""
        cur = self._conn.execute(
            """
            INSERT INTO benchmark_runs
                (run_uuid, started_at, model_name, model_family, model_param_count,
                 ollama_url, temperature, host_info)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_uuid,
                int(time.time() * 1000),
                self.model_name,
                model_info.get("family"),
                model_info.get("params"),
                self.ollama_url if not self._is_anthropic else "anthropic-api",
                0.0,
                _host_info(),
            ),
        )
        self._conn.commit()
        return cur.lastrowid

    def _run_case(
        self, case: TestCase, profile: PersonaProfile, styled_prompt: str
    ) -> dict[str, Any]:
        """Run a single (case, persona) through the Cairn pipeline.

        Returns dict with all result fields.
        """
        # Copy profile DB for isolation
        tmp_dir = tempfile.mkdtemp(prefix=f"bench_{profile.persona_id}_")
        tmp_db = os.path.join(tmp_dir, "talkingrock.db")
        shutil.copy2(profile.db_path, tmp_db)

        try:
            # Set environment
            os.environ["TALKINGROCK_DATA_DIR"] = tmp_dir
            os.environ["TALKINGROCK_OLLAMA_MODEL"] = self.model_name

            # Install mock Thunderbird
            from harness.mock_thunderbird import install_mock

            install_mock(tmp_db)

            # Patch provider for Anthropic if needed
            if self._is_anthropic:
                self._patch_anthropic_provider()

            # Import agent components
            from cairn.agent import ChatAgent
            from cairn.cairn.consciousness_stream import ConsciousnessObserver
            from cairn.db import Database

            db = Database(tmp_db)
            db.migrate()
            agent = ChatAgent(db=db)
            observer = ConsciousnessObserver.get_instance()

            t0 = time.time()

            with _timeout_context(self.timeout):
                observer.start_session()

                response = agent.respond(styled_prompt, agent_type="cairn")

                # Auto-approve pending actions
                if response.pending_approval_id:
                    observer.end_session()
                    observer.start_session()
                    response = agent.respond(
                        styled_prompt, agent_type="cairn", force_approve=True
                    )

                events = observer.get_all()
                observer.end_session()

            elapsed_ms = int((time.time() - t0) * 1000)

            # Extract tool call data
            tool_data = _extract_tool_call(events)

            # Score
            scores = score_result(
                tool_selected=tool_data["tool_selected"],
                tool_args=tool_data["tool_args"],
                tool_execution_ok=tool_data["tool_execution_ok"],
                tool_error=tool_data["tool_error"],
                response_text=response.answer,
                expected_tool=case.expected_tool,
                expected_args_schema=(
                    json.dumps(case.expected_args_schema)
                    if case.expected_args_schema
                    else None
                ),
            )

            result = {
                "response_text": response.answer,
                "latency_ms": elapsed_ms,
                **tool_data,
                **scores,
            }

            db.close()
            return result

        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _patch_anthropic_provider(self) -> None:
        """Monkey-patch the Cairn provider factory to return Anthropic provider.

        Replaces get_provider() so the agent's LLM calls go through
        the Anthropic API instead of Ollama.
        """
        from benchmarks.anthropic_provider import InstrumentedAnthropicProvider
        from cairn.providers import factory

        provider = InstrumentedAnthropicProvider(
            credential=self.anthropic_key, model=self.model_name
        )

        def patched_get_provider(db):
            return provider

        factory.get_provider = patched_get_provider
        factory.get_provider_or_none = lambda db: provider

    def _write_result(
        self,
        case: TestCase,
        profile: PersonaProfile,
        styled_prompt: str,
        result: dict[str, Any],
    ) -> None:
        """Write a benchmark_results row."""
        self._conn.execute(
            """
            INSERT INTO benchmark_results
                (run_id, case_id, executed_at,
                 persona_id, persona_style, prompt_used,
                 tool_selected, tool_args, tool_execution_ok, tool_error,
                 response_text, latency_ms,
                 tool_match, args_match, execution_success, response_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                self._run_id,
                case.case_id,
                int(time.time() * 1000),
                profile.persona_id,
                profile.personality,
                styled_prompt,
                result.get("tool_selected"),
                result.get("tool_args"),
                result.get("tool_execution_ok"),
                result.get("tool_error"),
                result.get("response_text"),
                result.get("latency_ms"),
                result.get("tool_match"),
                result.get("args_match"),
                result.get("execution_success"),
                result.get("response_quality"),
            ),
        )
        self._conn.commit()

    def _write_error(
        self,
        case: TestCase,
        profile: PersonaProfile,
        styled_prompt: str,
        error: str,
    ) -> None:
        """Write an error result row."""
        self._conn.execute(
            """
            INSERT INTO benchmark_results
                (run_id, case_id, executed_at,
                 persona_id, persona_style, prompt_used,
                 pipeline_error, latency_ms,
                 tool_match, args_match, execution_success, response_quality)
            VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0, 0, 0, 'wrong')
            """,
            (
                self._run_id,
                case.case_id,
                int(time.time() * 1000),
                profile.persona_id,
                profile.personality,
                styled_prompt,
                error,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None
