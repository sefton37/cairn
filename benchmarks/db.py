"""SQLite schema for the Cairn benchmark framework.

Database: ~/.talkingrock/cairn_benchmark.db

Tables:
    benchmark_runs    — one row per invocation of the runner
    test_cases        — the corpus (tool × variant combinations)
    benchmark_results — one row per (run × case × persona)

Views:
    v_model_accuracy   — overall accuracy per model
    v_tool_accuracy    — accuracy per tool per model
    v_persona_accuracy — accuracy by persona style
    v_mismatches       — failure patterns (tool mismatches)
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path.home() / ".talkingrock" / "cairn_benchmark.db"


def init_db(db_path: str | Path | None = None) -> sqlite3.Connection:
    """Initialize the benchmark database with schema and views.

    Creates the database file if it doesn't exist. Schema creation
    is idempotent (IF NOT EXISTS everywhere).

    Args:
        db_path: Path to the SQLite database. Defaults to
            ~/.talkingrock/cairn_benchmark.db

    Returns:
        sqlite3.Connection with WAL mode and foreign keys enabled.
    """
    path = Path(db_path) if db_path else DEFAULT_DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    _create_tables(conn)
    _create_views(conn)

    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- One row per invocation of the runner
        CREATE TABLE IF NOT EXISTS benchmark_runs (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_uuid            TEXT    NOT NULL UNIQUE,
            started_at          INTEGER NOT NULL,
            completed_at        INTEGER,
            model_name          TEXT    NOT NULL,
            model_family        TEXT,
            model_param_count   TEXT,
            ollama_url          TEXT,
            temperature         REAL    NOT NULL DEFAULT 0.0,
            corpus_version      TEXT,
            host_info           TEXT,
            notes               TEXT
        );

        -- The corpus: one row per (tool, variant) combination
        CREATE TABLE IF NOT EXISTS test_cases (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id             TEXT    NOT NULL UNIQUE,
            tool_name           TEXT    NOT NULL,
            question_template   TEXT    NOT NULL,
            variant             TEXT    NOT NULL CHECK (
                variant IN ('basic', 'edge', 'regression', 'off_topic', 'ambiguous')
            ),
            expected_tool       TEXT    NOT NULL,
            expected_args_schema TEXT,
            notes               TEXT
        );

        -- One row per (run × case × persona)
        CREATE TABLE IF NOT EXISTS benchmark_results (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id              INTEGER NOT NULL REFERENCES benchmark_runs(id),
            case_id             TEXT    NOT NULL REFERENCES test_cases(case_id),
            executed_at         INTEGER NOT NULL,

            -- Persona context
            persona_id          TEXT    NOT NULL,
            persona_style       TEXT    NOT NULL,
            prompt_used         TEXT    NOT NULL,

            -- Pipeline outcome
            tool_selected       TEXT,
            tool_args           TEXT,
            tool_execution_ok   INTEGER,
            tool_error          TEXT,
            response_text       TEXT,

            -- Latency
            latency_ms          INTEGER,

            -- Token counts
            tokens_prompt       INTEGER,
            tokens_completion   INTEGER,

            -- Pipeline error (exception outside tool call)
            pipeline_error      TEXT,

            -- Accuracy scoring
            tool_match          INTEGER,
            args_match          INTEGER,
            execution_success   INTEGER,
            response_quality    TEXT,

            UNIQUE (run_id, case_id, persona_id)
        );

        -- Indexes
        CREATE INDEX IF NOT EXISTS idx_results_run
            ON benchmark_results (run_id);
        CREATE INDEX IF NOT EXISTS idx_results_case
            ON benchmark_results (case_id);
        CREATE INDEX IF NOT EXISTS idx_results_tool
            ON benchmark_results (tool_selected);
        CREATE INDEX IF NOT EXISTS idx_results_persona
            ON benchmark_results (persona_id);
        CREATE INDEX IF NOT EXISTS idx_cases_tool
            ON test_cases (tool_name);
        CREATE INDEX IF NOT EXISTS idx_runs_model
            ON benchmark_runs (model_name);

        -- Memory benchmark: one row per test case in the memory corpus
        CREATE TABLE IF NOT EXISTS memory_test_cases (
            id                INTEGER PRIMARY KEY AUTOINCREMENT,
            case_id           TEXT NOT NULL UNIQUE,
            category          TEXT NOT NULL CHECK (
                category IN ('positive', 'negative', 'edge', 'regression')
            ),
            memory_type       TEXT CHECK (
                memory_type IN ('fact','preference','relationship','commitment','priority')
                OR memory_type IS NULL
            ),
            variant           TEXT NOT NULL,
            user_message      TEXT NOT NULL,
            cairn_response    TEXT NOT NULL,
            expected_detection TEXT NOT NULL CHECK (
                expected_detection IN ('CREATE', 'NO_CHANGE')
            ),
            expected_type     TEXT CHECK (
                expected_type IN ('fact','preference','relationship','commitment','priority')
                OR expected_type IS NULL
            ),
            expected_act_hint TEXT,
            narrative_required_phrases TEXT,  -- JSON array of strings
            notes             TEXT
        );

        -- Memory benchmark: one row per (run × memory case × persona)
        CREATE TABLE IF NOT EXISTS memory_benchmark_results (
            id                    INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id                INTEGER NOT NULL REFERENCES benchmark_runs(id),
            case_id               TEXT NOT NULL REFERENCES memory_test_cases(case_id),
            executed_at           INTEGER NOT NULL,

            -- Persona context
            persona_id            TEXT NOT NULL,
            persona_style         TEXT NOT NULL,
            styled_user_message   TEXT NOT NULL,

            -- Pipeline outputs
            detection_result      TEXT,  -- 'CREATE' | 'NO_CHANGE' | null on error
            detected_type         TEXT,
            destination_act_id    TEXT,
            destination_act_title TEXT,  -- denormalized for readability
            narrative_produced    TEXT,
            what_summary          TEXT,

            -- Latency in ms
            latency_detection_ms  INTEGER,
            latency_compression_ms INTEGER,
            latency_type_ms       INTEGER,
            latency_routing_ms    INTEGER,
            latency_total_ms      INTEGER,

            -- Pipeline error
            pipeline_error        TEXT,

            -- Accuracy scores (0 or 1, NULL means not applicable to this case)
            detection_correct     INTEGER,
            type_correct          INTEGER,
            routing_correct       INTEGER,
            narrative_quality     INTEGER,
            auto_approve_correct  INTEGER,

            UNIQUE (run_id, case_id, persona_id)
        );

        -- Indexes for memory benchmark tables
        CREATE INDEX IF NOT EXISTS idx_mem_results_run
            ON memory_benchmark_results (run_id);
        CREATE INDEX IF NOT EXISTS idx_mem_results_case
            ON memory_benchmark_results (case_id);
        CREATE INDEX IF NOT EXISTS idx_mem_results_persona
            ON memory_benchmark_results (persona_id);
        CREATE INDEX IF NOT EXISTS idx_mem_cases_category
            ON memory_test_cases (category);
        CREATE INDEX IF NOT EXISTS idx_mem_cases_type
            ON memory_test_cases (memory_type);
        """
    )


def _create_views(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        -- Overall accuracy per model
        CREATE VIEW IF NOT EXISTS v_model_accuracy AS
        SELECT
            r.model_name,
            r.model_param_count,
            COUNT(br.id)                                                AS total,
            ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)  AS tool_match_pct,
            ROUND(100.0 * SUM(br.args_match)      / COUNT(br.id), 1)  AS args_match_pct,
            ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1) AS execution_pct,
            ROUND(AVG(br.latency_ms), 0)                               AS avg_latency_ms
        FROM benchmark_runs r
        JOIN benchmark_results br ON br.run_id = r.id
        GROUP BY r.model_name, r.model_param_count
        ORDER BY tool_match_pct DESC;

        -- Accuracy per tool per model
        CREATE VIEW IF NOT EXISTS v_tool_accuracy AS
        SELECT
            r.model_name,
            tc.tool_name,
            tc.variant,
            COUNT(br.id)                                                AS total,
            ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)  AS tool_match_pct,
            ROUND(100.0 * SUM(br.args_match)      / COUNT(br.id), 1)  AS args_match_pct,
            ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1) AS execution_pct
        FROM benchmark_runs r
        JOIN benchmark_results br ON br.run_id = r.id
        JOIN test_cases tc         ON tc.case_id = br.case_id
        GROUP BY r.model_name, tc.tool_name, tc.variant
        ORDER BY r.model_name, tc.tool_name;

        -- Accuracy by persona style
        CREATE VIEW IF NOT EXISTS v_persona_accuracy AS
        SELECT
            r.model_name,
            br.persona_style,
            COUNT(br.id)                                                AS total,
            ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)  AS tool_match_pct,
            ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1) AS execution_pct
        FROM benchmark_runs r
        JOIN benchmark_results br ON br.run_id = r.id
        GROUP BY r.model_name, br.persona_style
        ORDER BY r.model_name, br.persona_style;

        -- Failure patterns: tool mismatches
        CREATE VIEW IF NOT EXISTS v_mismatches AS
        SELECT
            r.model_name,
            tc.tool_name         AS expected_tool,
            br.tool_selected     AS actual_tool,
            tc.variant,
            br.persona_style,
            br.prompt_used,
            br.tool_error,
            br.pipeline_error
        FROM benchmark_runs r
        JOIN benchmark_results br ON br.run_id = r.id
        JOIN test_cases tc         ON tc.case_id = br.case_id
        WHERE br.tool_match = 0
        ORDER BY r.model_name, tc.tool_name;

        -- Memory: overall accuracy per model across all 5 scoring dimensions
        CREATE VIEW IF NOT EXISTS v_mem_model_accuracy AS
        SELECT
            r.model_name,
            r.model_param_count,
            COUNT(mr.id)                                                           AS total,
            ROUND(100.0 * SUM(mr.detection_correct) / COUNT(mr.id), 1)            AS detection_pct,
            ROUND(100.0 * SUM(mr.type_correct) FILTER (WHERE mr.detection_correct = 1)
                  / NULLIF(SUM(mr.detection_correct), 0), 1)                       AS type_pct,
            ROUND(100.0 * SUM(mr.routing_correct) FILTER (WHERE mr.routing_correct IS NOT NULL)
                  / NULLIF(COUNT(mr.routing_correct) FILTER (WHERE mr.routing_correct IS NOT NULL), 0), 1)
                                                                                   AS routing_pct,
            ROUND(100.0 * SUM(mr.narrative_quality) FILTER (WHERE mr.narrative_quality IS NOT NULL)
                  / NULLIF(COUNT(mr.narrative_quality) FILTER (WHERE mr.narrative_quality IS NOT NULL), 0), 1)
                                                                                   AS narrative_pct,
            ROUND(100.0 * SUM(mr.auto_approve_correct) FILTER (WHERE mr.auto_approve_correct IS NOT NULL)
                  / NULLIF(COUNT(mr.auto_approve_correct) FILTER (WHERE mr.auto_approve_correct IS NOT NULL), 0), 1)
                                                                                   AS auto_approve_pct,
            ROUND(AVG(mr.latency_total_ms), 0)                                     AS avg_latency_ms
        FROM benchmark_runs r
        JOIN memory_benchmark_results mr ON mr.run_id = r.id
        GROUP BY r.model_name, r.model_param_count
        ORDER BY detection_pct DESC;

        -- Memory: detection and type accuracy broken down by expected_type
        CREATE VIEW IF NOT EXISTS v_mem_type_accuracy AS
        SELECT
            r.model_name,
            mtc.memory_type                                                        AS expected_type,
            COUNT(mr.id)                                                           AS total,
            ROUND(100.0 * SUM(mr.detection_correct) / COUNT(mr.id), 1)            AS detection_pct,
            ROUND(100.0 * SUM(mr.type_correct) FILTER (WHERE mr.detection_correct = 1)
                  / NULLIF(SUM(mr.detection_correct), 0), 1)                       AS type_pct
        FROM benchmark_runs r
        JOIN memory_benchmark_results mr  ON mr.run_id = r.id
        JOIN memory_test_cases mtc        ON mtc.case_id = mr.case_id
        GROUP BY r.model_name, mtc.memory_type
        ORDER BY r.model_name, mtc.memory_type;

        -- Memory: accuracy by category (positive/negative/edge/regression)
        CREATE VIEW IF NOT EXISTS v_mem_category_accuracy AS
        SELECT
            r.model_name,
            mtc.category,
            COUNT(mr.id)                                                           AS total,
            ROUND(100.0 * SUM(mr.detection_correct) / COUNT(mr.id), 1)            AS detection_pct,
            ROUND(100.0 * SUM(mr.type_correct) FILTER (WHERE mr.type_correct IS NOT NULL)
                  / NULLIF(COUNT(mr.type_correct) FILTER (WHERE mr.type_correct IS NOT NULL), 0), 1)
                                                                                   AS type_pct
        FROM benchmark_runs r
        JOIN memory_benchmark_results mr  ON mr.run_id = r.id
        JOIN memory_test_cases mtc        ON mtc.case_id = mr.case_id
        GROUP BY r.model_name, mtc.category
        ORDER BY r.model_name, mtc.category;

        -- Memory: rows where detection or type classification failed
        CREATE VIEW IF NOT EXISTS v_mem_failures AS
        SELECT
            r.model_name,
            mr.case_id,
            mtc.category,
            mtc.memory_type                AS expected_type,
            mr.detection_result            AS actual_detection,
            mtc.expected_detection,
            mr.detected_type               AS actual_type,
            mr.persona_style,
            mr.styled_user_message,
            mr.pipeline_error,
            mr.detection_correct,
            mr.type_correct
        FROM benchmark_runs r
        JOIN memory_benchmark_results mr  ON mr.run_id = r.id
        JOIN memory_test_cases mtc        ON mtc.case_id = mr.case_id
        WHERE mr.detection_correct = 0 OR mr.type_correct = 0
        ORDER BY r.model_name, mtc.category, mr.case_id;

        -- Memory: accuracy by persona style
        CREATE VIEW IF NOT EXISTS v_mem_persona_accuracy AS
        SELECT
            r.model_name,
            mr.persona_style,
            COUNT(mr.id)                                                           AS total,
            ROUND(100.0 * SUM(mr.detection_correct) / COUNT(mr.id), 1)            AS detection_pct,
            ROUND(100.0 * SUM(mr.type_correct) FILTER (WHERE mr.type_correct IS NOT NULL)
                  / NULLIF(COUNT(mr.type_correct) FILTER (WHERE mr.type_correct IS NOT NULL), 0), 1)
                                                                                   AS type_pct,
            ROUND(AVG(mr.latency_total_ms), 0)                                     AS avg_latency_ms
        FROM benchmark_runs r
        JOIN memory_benchmark_results mr ON mr.run_id = r.id
        GROUP BY r.model_name, mr.persona_style
        ORDER BY r.model_name, mr.persona_style;
        """
    )


def upsert_test_cases(conn: sqlite3.Connection, cases: list[dict]) -> int:
    """Insert or update test cases from corpus data.

    Args:
        conn: Database connection.
        cases: List of test case dicts with keys matching test_cases columns.

    Returns:
        Number of cases upserted.
    """
    count = 0
    for case in cases:
        conn.execute(
            """
            INSERT INTO test_cases (case_id, tool_name, question_template, variant,
                                    expected_tool, expected_args_schema, notes)
            VALUES (:case_id, :tool_name, :question_template, :variant,
                    :expected_tool, :expected_args_schema, :notes)
            ON CONFLICT (case_id) DO UPDATE SET
                tool_name = excluded.tool_name,
                question_template = excluded.question_template,
                variant = excluded.variant,
                expected_tool = excluded.expected_tool,
                expected_args_schema = excluded.expected_args_schema,
                notes = excluded.notes
            """,
            case,
        )
        count += 1
    conn.commit()
    return count


def get_completed_cases(
    conn: sqlite3.Connection, model_name: str
) -> set[tuple[str, str]]:
    """Get (case_id, persona_id) pairs already completed for a model.

    Used for --resume support.
    """
    rows = conn.execute(
        """
        SELECT br.case_id, br.persona_id
        FROM benchmark_results br
        JOIN benchmark_runs r ON r.id = br.run_id
        WHERE r.model_name = ?
        """,
        (model_name,),
    ).fetchall()
    return {(row["case_id"], row["persona_id"]) for row in rows}
