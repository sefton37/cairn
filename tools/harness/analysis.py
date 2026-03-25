"""Post-run analysis queries for harness results."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from harness.recorder import RESULTS_DIR

DEFAULT_DB = RESULTS_DIR / "harness.db"


def _connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = str(db_path or DEFAULT_DB)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def list_runs(db_path: Path | str | None = None) -> list[dict]:
    """List all harness runs."""
    conn = _connect(db_path)
    rows = conn.execute(
        "SELECT run_id, model_name, started_at, completed_at, "
        "total_questions, completed_questions "
        "FROM runs ORDER BY started_at DESC"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Single-run queries ──────────────────────────────────────────────


def query_by_type(run_id: str, db_path: Path | str | None = None) -> None:
    """Print classification accuracy: did each query_type route to the expected tool?"""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT query_type,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as ok,
                  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                  GROUP_CONCAT(DISTINCT tool_called) as tools_used,
                  ROUND(AVG(total_ms)) as avg_ms
           FROM results WHERE run_id = ?
           GROUP BY query_type ORDER BY query_type""",
        (run_id,),
    ).fetchall()
    conn.close()

    if not rows:
        print("No results found.")
        return

    print(f"\n{'Query Type':<15} {'Total':>5} {'OK':>4} {'Err':>4} {'Avg ms':>7}  Tools Used")
    print("-" * 75)
    for r in rows:
        tools = r["tools_used"] or "-"
        avg = int(r["avg_ms"]) if r["avg_ms"] else "-"
        print(f"{r['query_type']:<15} {r['total']:>5} {r['ok']:>4} "
              f"{r['errors']:>4} {str(avg):>7}  {tools}")


def query_failures(run_id: str, db_path: Path | str | None = None) -> None:
    """Print all failed or error results."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT result_id, profile_id, query_type, status, error,
                  tool_called, total_ms
           FROM results WHERE run_id = ? AND (status = 'error' OR verification_passed = 0)
           ORDER BY profile_id, query_type""",
        (run_id,),
    ).fetchall()
    conn.close()

    if not rows:
        print("No failures found.")
        return

    print(f"\n{'Profile':<22} {'Type':<15} {'Tool':<20} {'Error'}")
    print("-" * 90)
    for r in rows:
        err = (r["error"] or "verification failed")[:40]
        tool = r["tool_called"] or "-"
        print(f"{r['profile_id']:<22} {r['query_type']:<15} {tool:<20} {err}")


def query_tool_dispatch(run_id: str, db_path: Path | str | None = None) -> None:
    """Print pivot table: query_type x tool_called counts."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT query_type, COALESCE(tool_called, '(none)') as tool, COUNT(*) as cnt
           FROM results WHERE run_id = ?
           GROUP BY query_type, tool ORDER BY query_type, cnt DESC""",
        (run_id,),
    ).fetchall()
    conn.close()

    if not rows:
        print("No results found.")
        return

    print(f"\n{'Query Type':<15} {'Tool Called':<30} {'Count':>5}")
    print("-" * 55)
    for r in rows:
        print(f"{r['query_type']:<15} {r['tool']:<30} {r['cnt']:>5}")


def query_timing(run_id: str, db_path: Path | str | None = None) -> None:
    """Print timing stats by query type and profile."""
    conn = _connect(db_path)

    rows = conn.execute(
        """SELECT query_type, COUNT(*) as n,
                  MIN(total_ms) as min_ms,
                  MAX(total_ms) as max_ms,
                  ROUND(AVG(total_ms)) as avg_ms
           FROM results WHERE run_id = ? AND total_ms IS NOT NULL
           GROUP BY query_type ORDER BY avg_ms DESC""",
        (run_id,),
    ).fetchall()

    print(f"\n--- Timing by Query Type ---")
    print(f"{'Type':<15} {'N':>4} {'Min':>7} {'Avg':>7} {'Max':>7}")
    print("-" * 45)
    for r in rows:
        print(
            f"{r['query_type']:<15} {r['n']:>4} {r['min_ms']:>7} "
            f"{int(r['avg_ms']):>7} {r['max_ms']:>7}"
        )

    rows = conn.execute(
        """SELECT profile_id, COUNT(*) as n,
                  ROUND(AVG(total_ms)) as avg_ms,
                  MAX(total_ms) as max_ms
           FROM results WHERE run_id = ? AND total_ms IS NOT NULL
           GROUP BY profile_id ORDER BY avg_ms DESC""",
        (run_id,),
    ).fetchall()

    print(f"\n--- Timing by Profile ---")
    print(f"{'Profile':<25} {'N':>4} {'Avg ms':>7} {'Max ms':>7}")
    print("-" * 48)
    for r in rows:
        print(f"{r['profile_id']:<25} {r['n']:>4} {int(r['avg_ms']):>7} {r['max_ms']:>7}")

    conn.close()


def query_per_profile(
    run_id: str, profile_id: str, db_path: Path | str | None = None
) -> None:
    """Print full trace for one profile."""
    conn = _connect(db_path)
    rows = conn.execute(
        """SELECT result_id, query_type, status,
                  classification_domain, classification_action,
                  tool_called, total_ms, error,
                  response_text
           FROM results WHERE run_id = ? AND profile_id = ?
           ORDER BY result_id""",
        (run_id, profile_id),
    ).fetchall()
    conn.close()

    if not rows:
        print(f"No results for profile '{profile_id}'.")
        return

    for r in rows:
        status = "ERR" if r["status"] == "error" else "OK"
        ms = r["total_ms"] or 0
        print(f"\n{'=' * 70}")
        print(f"Q: {r['result_id']}")
        print(f"Type: {r['query_type']}  Domain: {r['classification_domain'] or '-'}  "
              f"Action: {r['classification_action'] or '-'}")
        print(f"Tool: {r['tool_called'] or '-'}  Time: {ms}ms  Status: {status}")
        if r["error"]:
            print(f"Error: {r['error']}")
        if r["response_text"]:
            text = r["response_text"][:300]
            if len(r["response_text"]) > 300:
                text += "..."
            print(f"Response: {text}")


def print_full_report(run_id: str, db_path: Path | str | None = None) -> None:
    """Print a comprehensive report for a single run."""
    conn = _connect(db_path)
    run = conn.execute(
        "SELECT model_name FROM runs WHERE run_id = ?", (run_id,)
    ).fetchone()
    conn.close()

    model = run["model_name"] if run else "unknown"
    print(f"\n{'=' * 70}")
    print(f"HARNESS REPORT: {run_id}  (model: {model})")
    print(f"{'=' * 70}")

    query_by_type(run_id, db_path)
    query_tool_dispatch(run_id, db_path)
    query_timing(run_id, db_path)
    query_failures(run_id, db_path)


# ── Cross-model comparison queries ──────────────────────────────────


def compare_models(db_path: Path | str | None = None) -> None:
    """Compare all models across all runs: success rate, timing, tool dispatch."""
    conn = _connect(db_path)

    # Overall stats per model
    rows = conn.execute(
        """SELECT model_name,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as ok,
                  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                  ROUND(AVG(total_ms)) as avg_ms,
                  MIN(total_ms) as min_ms,
                  MAX(total_ms) as max_ms
           FROM results
           GROUP BY model_name ORDER BY avg_ms"""
    ).fetchall()

    if not rows:
        print("No results found.")
        conn.close()
        return

    print(f"\n{'=' * 70}")
    print("MODEL COMPARISON")
    print(f"{'=' * 70}")

    print(f"\n--- Overall ---")
    print(f"{'Model':<40} {'Total':>5} {'OK':>4} {'Err':>4} "
          f"{'Avg ms':>7} {'Min':>7} {'Max':>7}")
    print("-" * 85)
    for r in rows:
        avg = int(r["avg_ms"]) if r["avg_ms"] else 0
        print(f"{r['model_name']:<40} {r['total']:>5} {r['ok']:>4} "
              f"{r['errors']:>4} {avg:>7} {r['min_ms'] or 0:>7} "
              f"{r['max_ms'] or 0:>7}")

    # Tool dispatch accuracy per model per query type
    rows = conn.execute(
        """SELECT model_name, query_type,
                  GROUP_CONCAT(DISTINCT COALESCE(tool_called, '(none)')) as tools,
                  COUNT(*) as cnt,
                  ROUND(AVG(total_ms)) as avg_ms
           FROM results WHERE status = 'complete'
           GROUP BY model_name, query_type
           ORDER BY query_type, model_name"""
    ).fetchall()

    print(f"\n--- Tool Dispatch by Model x Query Type ---")
    print(f"{'Model':<40} {'Query Type':<15} {'N':>4} {'Avg ms':>7}  Tools")
    print("-" * 90)
    for r in rows:
        avg = int(r["avg_ms"]) if r["avg_ms"] else 0
        print(f"{r['model_name']:<40} {r['query_type']:<15} "
              f"{r['cnt']:>4} {avg:>7}  {r['tools']}")

    # Personality breakdown per model
    rows = conn.execute(
        """SELECT model_name, personality,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as ok,
                  ROUND(AVG(total_ms)) as avg_ms
           FROM results
           GROUP BY model_name, personality
           ORDER BY model_name, personality"""
    ).fetchall()

    print(f"\n--- Success by Model x Personality ---")
    print(f"{'Model':<40} {'Personality':<12} {'Total':>5} {'OK':>4} {'Avg ms':>7}")
    print("-" * 75)
    for r in rows:
        avg = int(r["avg_ms"]) if r["avg_ms"] else 0
        pers = r["personality"] or "-"
        print(f"{r['model_name']:<40} {pers:<12} {r['total']:>5} "
              f"{r['ok']:>4} {avg:>7}")

    conn.close()


def compare_models_by_department(db_path: Path | str | None = None) -> None:
    """Compare model performance by department."""
    conn = _connect(db_path)

    rows = conn.execute(
        """SELECT model_name, department,
                  COUNT(*) as total,
                  SUM(CASE WHEN status = 'complete' THEN 1 ELSE 0 END) as ok,
                  SUM(CASE WHEN status = 'error' THEN 1 ELSE 0 END) as errors,
                  ROUND(AVG(total_ms)) as avg_ms
           FROM results
           GROUP BY model_name, department
           ORDER BY department, model_name"""
    ).fetchall()
    conn.close()

    if not rows:
        print("No results found.")
        return

    print(f"\n--- Performance by Model x Department ---")
    print(f"{'Model':<40} {'Department':<20} {'Total':>5} {'OK':>4} "
          f"{'Err':>4} {'Avg ms':>7}")
    print("-" * 85)
    for r in rows:
        avg = int(r["avg_ms"]) if r["avg_ms"] else 0
        dept = r["department"] or "-"
        print(f"{r['model_name']:<40} {dept:<20} {r['total']:>5} "
              f"{r['ok']:>4} {r['errors']:>4} {avg:>7}")
