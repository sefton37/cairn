"""Memory benchmark runner for Cairn.

Exercises the TurnDeltaAssessor pipeline (detection → compression →
type classification → act routing) per (test_case × persona × model)
and records results to the memory_benchmark_results table.

Mirrors runner.py structure but calls TurnDeltaAssessor.assess_turn()
directly rather than going through ChatAgent.respond(). This isolates
the memory pipeline from tool selection and produces directly
interpretable per-stage scores.
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
from pathlib import Path
from typing import Any

# Ensure Cairn src is importable
CAIRN_SRC = Path(__file__).parent.parent / "src"
if str(CAIRN_SRC) not in sys.path:
    sys.path.insert(0, str(CAIRN_SRC))

from benchmarks.corpus import load_persona_profiles
from benchmarks.db import init_db
from benchmarks.memory_corpus import (
    MemoryTestCase,
    expand_memory_with_personas,
    load_memory_corpus,
    upsert_memory_test_cases,
)
from benchmarks.memory_matching import (
    score_auto_approve,
    score_detection,
    score_narrative,
    score_routing,
    score_type,
)
from benchmarks.models import get_model_info, is_anthropic_model


def _host_info() -> str:
    """Collect host information as JSON string."""
    info = {
        "hostname": platform.node(),
        "python": platform.python_version(),
        "os": f"{platform.system()} {platform.release()}",
        "cpu": platform.processor() or "unknown",
    }
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


def _get_completed_memory_cases(
    conn: sqlite3.Connection, model_name: str
) -> set[tuple[str, str]]:
    """Get (case_id, persona_id) pairs already completed for a model.

    Queries memory_benchmark_results joined to benchmark_runs.
    Used for --resume support.
    """
    rows = conn.execute(
        """
        SELECT mr.case_id, mr.persona_id
        FROM memory_benchmark_results mr
        JOIN benchmark_runs r ON r.id = mr.run_id
        WHERE r.model_name = ?
        """,
        (model_name,),
    ).fetchall()
    return {(row["case_id"], row["persona_id"]) for row in rows}


def _score_label(value: int | None, positive_label: str = "+") -> str:
    """Convert a score (0/1/None) to a display symbol.

    None → '?' (not applicable), 1 → positive_label, 0 → '-'.
    """
    if value is None:
        return "?"
    return positive_label if value == 1 else "-"


def _format_score_line(
    detection_correct: int,
    type_correct: int | None,
    routing_correct: int | None,
    narrative_quality: int | None,
    auto_approve_correct: int | None,
) -> str:
    """Build the compact score string shown on each progress line.

    Format: D+ T+ R? N+ G+
    D = detection, T = type, R = routing, N = narrative, G = auto-approve gate
    """
    d = "D" + _score_label(detection_correct)
    t = "T" + _score_label(type_correct)
    r = "R" + _score_label(routing_correct)
    n = "N" + _score_label(narrative_quality)
    g = "G" + _score_label(auto_approve_correct)
    return f"{d} {t} {r} {n} {g}"


def _timeout_context(seconds: int):
    """Context manager that raises TimeoutError after N seconds.

    Uses SIGALRM on Linux/macOS (main thread only).
    Falls back to no-op on Windows or in threads.
    """
    import contextlib

    if not hasattr(signal, "SIGALRM"):

        @contextlib.contextmanager
        def _noop():
            yield

        return _noop()

    @contextlib.contextmanager
    def _ctx():
        def handler(signum, frame):
            raise TimeoutError(f"Timeout after {seconds}s")

        old = signal.signal(signal.SIGALRM, handler)
        signal.alarm(seconds)
        try:
            yield
        finally:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, old)

    return _ctx()


class MemoryBenchmarkRunner:
    """Runs memory benchmark cases through the TurnDeltaAssessor pipeline.

    Each (case, persona) pair is run in isolation: the persona's talkingrock.db
    is copied to a temp directory, TALKINGROCK_DATA_DIR is pointed there, and
    a fresh TurnDeltaAssessor is constructed with a real OllamaProvider targeting
    the benchmark model. Results are written to memory_benchmark_results.

    Usage:
        runner = MemoryBenchmarkRunner(model_name="qwen2.5:7b")
        runner.run(cases, profiles)
    """

    def __init__(
        self,
        model_name: str,
        db_path: str | None = None,
        ollama_url: str | None = None,
        timeout: int = 120,
        anthropic_key: str | None = None,
    ) -> None:
        self.model_name = model_name
        self.db_path = db_path
        self.ollama_url = ollama_url or "http://localhost:11434"
        self.timeout = timeout
        self.anthropic_key = anthropic_key

        self._conn: sqlite3.Connection | None = None
        self._run_id: int | None = None
        self._run_uuid: str | None = None
        self._is_anthropic = is_anthropic_model(model_name)

    def run(
        self,
        cases: list[MemoryTestCase] | None = None,
        profiles: list[Any] | None = None,
        resume: bool = False,
    ) -> str:
        """Run all (case, persona) pairs. Main entry point.

        Args:
            cases: Memory test cases to run. If None, loads from memory_corpus.json.
            profiles: Persona profiles to expand with. If None, loads from test_profiles/.
            resume: If True, skip (case, persona) pairs already in the database.

        Returns:
            The run UUID string.
        """
        self._conn = init_db(self.db_path)
        self._run_uuid = str(uuid.uuid4())

        if cases is None:
            cases = load_memory_corpus()
        if profiles is None:
            profiles = load_persona_profiles()

        if not cases:
            print("No memory test cases found.")
            return self._run_uuid
        if not profiles:
            print("No persona profiles found.")
            return self._run_uuid

        # Upsert test cases to benchmark DB
        upsert_memory_test_cases(self._conn, cases)

        # Expand cases × personas
        triples = expand_memory_with_personas(cases, profiles)

        # Resume: collect already-done (case_id, persona_id) pairs
        done: set[tuple[str, str]] = set()
        if resume:
            done = _get_completed_memory_cases(self._conn, self.model_name)

        remaining = [
            (c, p, s) for c, p, s in triples if (c.case_id, p.persona_id) not in done
        ]

        if not remaining:
            print("All cases already completed for this model.")
            return self._run_uuid

        # Create the benchmark_runs row
        model_info = get_model_info(self.model_name) or {}
        self._run_id = self._create_run(model_info)

        total = len(remaining)
        skipped = len(triples) - len(remaining)

        print(f"\n{'=' * 65}")
        print("Cairn Memory Benchmark")
        print(f"Model:    {self.model_name}")
        print(f"Run:      {self._run_uuid}")
        print(
            f"Cases:    {len(cases)} base × {len(profiles)} personas"
            f" = {len(triples)} total"
        )
        if skipped:
            print(f"Skipped:  {skipped} (already completed)")
        print(f"Running:  {total}")
        print(f"Timeout:  {self.timeout}s per case")
        print(f"{'=' * 65}\n")

        completed = 0
        errors = 0

        for i, (case, profile, styled_message) in enumerate(remaining):
            prefix = f"[{i + 1}/{total}] {case.case_id} ({profile.persona_id})"
            print(f"  {prefix:<72} ", end="", flush=True)

            try:
                result = self._run_case(case, profile, styled_message)
                self._write_result(result)
                completed += 1

                detection = result.get("detection_result") or "-"
                detected_type = result.get("detected_type") or "-"
                ms = result.get("latency_total_ms") or 0
                scores = _format_score_line(
                    result.get("detection_correct", 0),
                    result.get("type_correct"),
                    result.get("routing_correct"),
                    result.get("narrative_quality"),
                    result.get("auto_approve_correct"),
                )
                print(f"{detection:<10} {detected_type:<14} {ms:>6}ms  {scores}")

            except Exception as e:
                errors += 1
                self._write_error(case, profile, styled_message, str(e))
                print(f"ERR: {e}")

        # Mark run complete
        assert self._conn is not None
        self._conn.execute(
            "UPDATE benchmark_runs SET completed_at = ? WHERE id = ?",
            (int(time.time() * 1000), self._run_id),
        )
        self._conn.commit()

        print(f"\n{'=' * 65}")
        print(f"Complete: {completed}  Errors: {errors}  Skipped: {skipped}")
        print(f"{'=' * 65}\n")

        return self._run_uuid

    def _create_run(self, model_info: dict) -> int:
        """Create a benchmark_runs row and return its id."""
        assert self._conn is not None
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
        return cur.lastrowid  # type: ignore[return-value]

    def _run_case(
        self, case: MemoryTestCase, profile: Any, styled_message: str
    ) -> dict[str, Any]:
        """Execute one memory assessment case in isolation.

        Copies the persona's DB to a temp directory, sets TALKINGROCK_DATA_DIR,
        resets the play_db thread-local connection, initialises the schema,
        then calls TurnDeltaAssessor.assess_turn() with the synthetic inputs.

        After the call returns, reads the created memory back from the DB (if
        any) to get type, status, destination_act_id, and narrative. Then scores
        all 5 dimensions.

        Returns:
            Dict matching the memory_benchmark_results column layout.
        """
        # 1. Create temp directory and copy persona DB
        tmp_dir = tempfile.mkdtemp(prefix=f"membench_{profile.persona_id}_")
        tmp_db = os.path.join(tmp_dir, "talkingrock.db")
        shutil.copy2(profile.db_path, tmp_db)

        try:
            # 2-3. Point play_db at the temp dir
            os.environ["TALKINGROCK_DATA_DIR"] = tmp_dir

            # 4. Reset the thread-local connection so play_db opens the new DB
            from cairn.play_db import close_connection, init_db as play_init_db

            close_connection()

            # 5. Migrate the temp DB to the current schema
            play_init_db()

            # 6. Build provider, services, assessor with injected provider
            from cairn.services.compression_pipeline import CompressionPipeline
            from cairn.services.memory_service import MemoryService
            from cairn.services.turn_delta_assessor import TurnDeltaAssessor

            if self._is_anthropic:
                from benchmarks.anthropic_provider import InstrumentedAnthropicProvider

                provider = InstrumentedAnthropicProvider(
                    credential=self.anthropic_key, model=self.model_name
                )
            else:
                from cairn.providers.ollama import OllamaProvider

                provider = OllamaProvider(
                    url=self.ollama_url,
                    model=self.model_name,
                )
            memory_service = MemoryService(provider=provider)
            compression_pipeline = CompressionPipeline(provider=provider)
            assessor = TurnDeltaAssessor(
                provider=provider,
                memory_service=memory_service,
                compression_pipeline=compression_pipeline,
            )

            # 7. Synthetic conversation ID — stable per (case, persona) pair
            #    Must exist in conversations table (FK constraint)
            conv_id = f"bench-{case.case_id}-{profile.persona_id}"
            from cairn.play_db import _get_connection as _play_conn

            pconn = _play_conn()
            # Create a minimal conversation row. Schema varies across persona DBs
            # so detect columns and insert accordingly.
            cols_info = pconn.execute("PRAGMA table_info(conversations)").fetchall()
            col_names = {row[1] for row in cols_info}
            if "block_id" in col_names:
                # Older schema: needs a block_id (create a dummy block first)
                block_id = f"blk-bench-{case.case_id[:20]}-{profile.persona_id[:10]}"
                your_story_row = pconn.execute(
                    "SELECT act_id FROM acts LIMIT 1"
                ).fetchone()
                act_id = your_story_row[0] if your_story_row else "your-story"
                pconn.execute(
                    """INSERT OR IGNORE INTO blocks (id, type, act_id, position, created_at, updated_at)
                       VALUES (?, 'conversation', ?, 0, datetime('now'), datetime('now'))""",
                    (block_id, act_id),
                )
                pconn.execute(
                    """INSERT OR IGNORE INTO conversations (id, block_id, status)
                       VALUES (?, ?, 'active')""",
                    (conv_id, block_id),
                )
            else:
                # Newer schema
                pconn.execute(
                    """INSERT OR IGNORE INTO conversations (id, created_at, conversation_state)
                       VALUES (?, datetime('now'), 'active')""",
                    (conv_id,),
                )
            pconn.commit()

            # 8. Time the full pipeline call
            t0 = time.time()
            with _timeout_context(self.timeout):
                result = assessor.assess_turn(
                    conversation_id=conv_id,
                    turn_position=1,
                    user_message=styled_message,
                    cairn_response=case.cairn_response,
                    relevant_memories=[],
                )
            latency_total_ms = int((time.time() - t0) * 1000)

            # 9-10. If a memory was created, read it back for scoring fields
            memory = None
            destination_act_title: str | None = None

            if result.memory_id:
                memory = memory_service.get_by_id(result.memory_id)
                if memory and memory.destination_act_id:
                    # Look up the Act title from the acts table
                    from cairn.play_db import _get_connection

                    conn = _get_connection()
                    row = conn.execute(
                        "SELECT title FROM acts WHERE act_id = ?",
                        (memory.destination_act_id,),
                    ).fetchone()
                    if row:
                        destination_act_title = row["title"]

            # 11. Score all 5 dimensions
            detection_result = result.assessment  # 'CREATE' or 'NO_CHANGE'
            detected_type = memory.memory_type if memory else None
            memory_status = memory.status if memory else None
            narrative_produced = memory.narrative if memory else None
            destination_act_id = memory.destination_act_id if memory else None

            detection_correct = score_detection(detection_result, case.expected_detection)
            type_correct = score_type(detected_type, case.expected_type, detection_correct)
            routing_correct = score_routing(
                destination_act_title, case.expected_act_hint, detection_correct
            )
            narrative_quality = score_narrative(
                narrative_produced,
                case.narrative_required_phrases,
                detection_correct,
            )
            auto_approve_correct = score_auto_approve(
                detected_type, memory_status, case.expected_detection
            )

            return {
                "case_id": case.case_id,
                "persona_id": profile.persona_id,
                "persona_style": profile.personality,
                "styled_user_message": styled_message,
                "detection_result": detection_result,
                "detected_type": detected_type,
                "destination_act_id": destination_act_id,
                "destination_act_title": destination_act_title,
                "narrative_produced": narrative_produced,
                "what_summary": result.what,
                "latency_total_ms": latency_total_ms,
                # Stage-level latency is not tracked individually by the assessor;
                # only the total is available from this call.
                "latency_detection_ms": None,
                "latency_compression_ms": None,
                "latency_type_ms": None,
                "latency_routing_ms": None,
                "pipeline_error": None,
                "detection_correct": detection_correct,
                "type_correct": type_correct,
                "routing_correct": routing_correct,
                "narrative_quality": narrative_quality,
                "auto_approve_correct": auto_approve_correct,
            }

        finally:
            # Always reset the thread-local connection before removing the temp dir
            from cairn.play_db import close_connection as _close

            _close()
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _write_result(self, result: dict[str, Any]) -> None:
        """Write a memory_benchmark_results row for a successful case."""
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT INTO memory_benchmark_results (
                run_id, case_id, executed_at,
                persona_id, persona_style, styled_user_message,
                detection_result, detected_type,
                destination_act_id, destination_act_title,
                narrative_produced, what_summary,
                latency_detection_ms, latency_compression_ms,
                latency_type_ms, latency_routing_ms, latency_total_ms,
                pipeline_error,
                detection_correct, type_correct, routing_correct,
                narrative_quality, auto_approve_correct
            ) VALUES (
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?,
                ?, ?, ?,
                ?,
                ?, ?, ?,
                ?, ?
            )
            """,
            (
                self._run_id,
                result["case_id"],
                int(time.time() * 1000),
                result["persona_id"],
                result["persona_style"],
                result["styled_user_message"],
                result.get("detection_result"),
                result.get("detected_type"),
                result.get("destination_act_id"),
                result.get("destination_act_title"),
                result.get("narrative_produced"),
                result.get("what_summary"),
                result.get("latency_detection_ms"),
                result.get("latency_compression_ms"),
                result.get("latency_type_ms"),
                result.get("latency_routing_ms"),
                result.get("latency_total_ms"),
                result.get("pipeline_error"),
                result.get("detection_correct"),
                result.get("type_correct"),
                result.get("routing_correct"),
                result.get("narrative_quality"),
                result.get("auto_approve_correct"),
            ),
        )
        self._conn.commit()

    def _write_error(
        self,
        case: MemoryTestCase,
        profile: Any,
        styled_message: str,
        error: str,
    ) -> None:
        """Write an error result row when _run_case raises an exception."""
        assert self._conn is not None
        self._conn.execute(
            """
            INSERT INTO memory_benchmark_results (
                run_id, case_id, executed_at,
                persona_id, persona_style, styled_user_message,
                pipeline_error,
                detection_correct, type_correct, routing_correct,
                narrative_quality, auto_approve_correct
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, NULL, NULL)
            """,
            (
                self._run_id,
                case.case_id,
                int(time.time() * 1000),
                profile.persona_id,
                profile.personality,
                styled_message,
                error,
            ),
        )
        self._conn.commit()

    def close(self) -> None:
        """Close the benchmark database connection."""
        if self._conn:
            self._conn.close()
