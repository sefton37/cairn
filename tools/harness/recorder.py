"""Result recording for harness runs — SQLite + JSONL."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

RESULTS_DIR = Path(__file__).parent.parent / "harness_results"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    model_name TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    profiles_requested TEXT,  -- JSON array of profile IDs
    total_questions INTEGER DEFAULT 0,
    completed_questions INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS results (
    result_id TEXT PRIMARY KEY,  -- model::question_id
    run_id TEXT NOT NULL,
    model_name TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    query_type TEXT NOT NULL,
    question_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',

    -- Profile metadata
    personality TEXT,
    department TEXT,
    role TEXT,

    -- Response
    response_text TEXT,

    -- Classification
    classification_domain TEXT,
    classification_action TEXT,
    classification_confident INTEGER,
    classification_reasoning TEXT,
    behavior_mode TEXT,

    -- Tool execution
    tool_called TEXT,
    tool_args TEXT,
    tool_result_summary TEXT,

    -- Verification
    verification_passed INTEGER,
    needs_approval INTEGER,

    -- Timing
    started_at TEXT,
    completed_at TEXT,
    total_ms INTEGER,

    -- Consciousness trace
    consciousness_events TEXT,  -- JSON array

    -- Errors
    error TEXT
);

CREATE INDEX IF NOT EXISTS idx_results_run ON results(run_id);
CREATE INDEX IF NOT EXISTS idx_results_model ON results(model_name);
CREATE INDEX IF NOT EXISTS idx_results_profile ON results(profile_id);
CREATE INDEX IF NOT EXISTS idx_results_type ON results(query_type);
CREATE INDEX IF NOT EXISTS idx_results_domain ON results(classification_domain);
CREATE INDEX IF NOT EXISTS idx_results_personality ON results(personality);
CREATE INDEX IF NOT EXISTS idx_results_department ON results(department);
"""


class Recorder:
    """Records harness run results to SQLite and JSONL."""

    def __init__(self, run_id: str, model_name: str):
        self.run_id = run_id
        self.model_name = model_name
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)

        self.db_path = RESULTS_DIR / "harness.db"
        self.jsonl_path = RESULTS_DIR / f"{run_id}.jsonl"

        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def _result_id(self, question_id: str) -> str:
        """Unique key scoped to model + question."""
        return f"{self.model_name}::{question_id}"

    def start_run(self, profile_ids: list[str], total_questions: int):
        """Record run start."""
        now = datetime.now().isoformat()
        self.conn.execute(
            """INSERT OR REPLACE INTO runs
               (run_id, model_name, started_at, profiles_requested,
                total_questions, completed_questions)
               VALUES (?, ?, ?, ?, ?, 0)""",
            (self.run_id, self.model_name, now,
             json.dumps(profile_ids), total_questions),
        )
        self.conn.commit()

    def is_complete(self, question_id: str) -> bool:
        """Check if a question has already been completed for this model."""
        rid = self._result_id(question_id)
        row = self.conn.execute(
            "SELECT status FROM results WHERE result_id = ?",
            (rid,),
        ).fetchone()
        return row is not None and row[0] == "complete"

    def mark_started(self, question: dict, profile_meta: dict):
        """Mark a question as started (for resumability)."""
        now = datetime.now().isoformat()
        rid = self._result_id(question["question_id"])
        self.conn.execute(
            """INSERT OR REPLACE INTO results
               (result_id, run_id, model_name, profile_id, query_type,
                question_text, personality, department, role,
                status, started_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'running', ?)""",
            (rid, self.run_id, self.model_name,
             question["profile_id"], question["query_type"], question["text"],
             profile_meta.get("personality"),
             profile_meta.get("department"),
             profile_meta.get("role"),
             now),
        )
        self.conn.commit()

    def record_result(self, question_id: str, result: dict):
        """Record a completed question result."""
        now = datetime.now().isoformat()
        rid = self._result_id(question_id)
        self.conn.execute(
            """UPDATE results SET
               status = 'complete',
               response_text = ?,
               classification_domain = ?,
               classification_action = ?,
               classification_confident = ?,
               classification_reasoning = ?,
               behavior_mode = ?,
               tool_called = ?,
               tool_args = ?,
               tool_result_summary = ?,
               verification_passed = ?,
               needs_approval = ?,
               completed_at = ?,
               total_ms = ?,
               consciousness_events = ?,
               error = ?
               WHERE result_id = ?""",
            (
                result.get("response_text"),
                result.get("classification_domain"),
                result.get("classification_action"),
                result.get("classification_confident"),
                result.get("classification_reasoning"),
                result.get("behavior_mode"),
                result.get("tool_called"),
                json.dumps(result.get("tool_args")) if result.get("tool_args") else None,
                result.get("tool_result_summary"),
                result.get("verification_passed"),
                result.get("needs_approval"),
                now,
                result.get("total_ms"),
                json.dumps(result.get("consciousness_events")),
                result.get("error"),
                rid,
            ),
        )

        # Update run counter
        self.conn.execute(
            "UPDATE runs SET completed_questions = completed_questions + 1 WHERE run_id = ?",
            (self.run_id,),
        )
        self.conn.commit()

        # Append to JSONL (include model for traceability)
        record = {**result, "model_name": self.model_name, "question_id": question_id}
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def record_error(self, question_id: str, error: str):
        """Record an error for a question."""
        now = datetime.now().isoformat()
        rid = self._result_id(question_id)
        self.conn.execute(
            """UPDATE results SET status = 'error', error = ?, completed_at = ?
               WHERE result_id = ?""",
            (error, now, rid),
        )
        self.conn.commit()

    def finish_run(self):
        """Mark run as complete."""
        now = datetime.now().isoformat()
        self.conn.execute(
            "UPDATE runs SET completed_at = ? WHERE run_id = ?",
            (now, self.run_id),
        )
        self.conn.commit()

    def close(self):
        self.conn.close()

    def print_summary(self):
        """Print a summary table of results for this run."""
        rows = self.conn.execute(
            """SELECT profile_id, query_type, status, personality,
                      classification_domain, tool_called, total_ms, error
               FROM results WHERE run_id = ? ORDER BY profile_id, query_type""",
            (self.run_id,),
        ).fetchall()

        if not rows:
            print("No results recorded.")
            return

        print(f"\n{'Profile':<25} {'Type':<15} {'Pers.':<10} {'Domain':<12} "
              f"{'Tool':<25} {'ms':>6} {'St':<4}")
        print("-" * 100)
        for row in rows:
            profile, qtype, status, pers, domain, tool, ms, error = row
            domain = domain or "-"
            tool = tool or "-"
            pers = pers or "-"
            ms_str = str(ms) if ms else "-"
            status_str = "ERR" if status == "error" else "OK"
            print(f"{profile:<25} {qtype:<15} {pers:<10} {domain:<12} "
                  f"{tool:<25} {ms_str:>6} {status_str:<4}")

        # Aggregate stats
        total = len(rows)
        ok = sum(1 for r in rows if r[2] == "complete")
        err = sum(1 for r in rows if r[2] == "error")
        avg_ms = sum(r[6] or 0 for r in rows if r[6]) / max(1, sum(1 for r in rows if r[6]))
        print(f"\nModel: {self.model_name}  Total: {total}  OK: {ok}  "
              f"Errors: {err}  Avg time: {avg_ms:.0f}ms")
