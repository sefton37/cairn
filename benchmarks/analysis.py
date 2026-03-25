"""Analysis and reporting for Cairn benchmark results.

Named query wrappers around the pre-built views, plus human-readable
print functions for CLI output.
"""

from __future__ import annotations

import sqlite3
from typing import Any


def model_accuracy_summary(conn: sqlite3.Connection) -> list[dict]:
    """Per-model accuracy metrics from v_model_accuracy view."""
    rows = conn.execute("SELECT * FROM v_model_accuracy").fetchall()
    return [dict(row) for row in rows]


def tool_accuracy(
    conn: sqlite3.Connection, model_name: str | None = None
) -> list[dict]:
    """Per-tool accuracy breakdown."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_tool_accuracy WHERE model_name = ?", (model_name,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v_tool_accuracy").fetchall()
    return [dict(row) for row in rows]


def persona_accuracy(
    conn: sqlite3.Connection, model_name: str | None = None
) -> list[dict]:
    """Accuracy by persona style."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_persona_accuracy WHERE model_name = ?", (model_name,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v_persona_accuracy").fetchall()
    return [dict(row) for row in rows]


def failure_patterns(
    conn: sqlite3.Connection, model_name: str | None = None, limit: int = 20
) -> list[dict]:
    """Tool mismatch patterns."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_mismatches WHERE model_name = ? LIMIT ?",
            (model_name, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM v_mismatches LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def print_summary(conn: sqlite3.Connection, model_name: str | None = None) -> None:
    """Print human-readable model accuracy summary."""
    rows = model_accuracy_summary(conn)
    if model_name:
        rows = [r for r in rows if r["model_name"] == model_name]

    if not rows:
        print("No results found.")
        return

    # Header
    print(f"\n{'Model':<35} {'Params':<8} {'N':>5} "
          f"{'Tool%':>7} {'Args%':>7} {'Exec%':>7} {'Lat(ms)':>8}")
    print("-" * 85)

    for r in rows:
        print(
            f"{r['model_name']:<35} {r['model_param_count'] or '?':<8} "
            f"{r['total']:>5} "
            f"{r['tool_match_pct']:>6.1f}% "
            f"{r['args_match_pct']:>6.1f}% "
            f"{r['execution_pct']:>6.1f}% "
            f"{r['avg_latency_ms']:>7.0f}"
        )
    print()


def print_tool_breakdown(
    conn: sqlite3.Connection, model_name: str
) -> None:
    """Print per-tool accuracy for a model."""
    rows = tool_accuracy(conn, model_name)
    if not rows:
        print(f"No results for {model_name}.")
        return

    print(f"\n{'Tool':<35} {'Variant':<12} {'N':>4} "
          f"{'Tool%':>7} {'Args%':>7} {'Exec%':>7}")
    print("-" * 80)

    for r in rows:
        print(
            f"{r['tool_name']:<35} {r['variant']:<12} {r['total']:>4} "
            f"{r['tool_match_pct']:>6.1f}% "
            f"{r['args_match_pct']:>6.1f}% "
            f"{r['execution_pct']:>6.1f}%"
        )
    print()


def print_persona_breakdown(
    conn: sqlite3.Connection, model_name: str
) -> None:
    """Print per-persona-style accuracy for a model."""
    rows = persona_accuracy(conn, model_name)
    if not rows:
        print(f"No results for {model_name}.")
        return

    print(f"\n{'Style':<15} {'N':>5} {'Tool%':>7} {'Exec%':>7}")
    print("-" * 40)

    for r in rows:
        print(
            f"{r['persona_style']:<15} {r['total']:>5} "
            f"{r['tool_match_pct']:>6.1f}% "
            f"{r['execution_pct']:>6.1f}%"
        )
    print()


def print_failures(
    conn: sqlite3.Connection, model_name: str | None = None, limit: int = 20
) -> None:
    """Print tool mismatch details."""
    rows = failure_patterns(conn, model_name, limit)
    if not rows:
        print("No mismatches found.")
        return

    print(f"\n{'Expected':<30} {'Actual':<30} {'Style':<12} {'Prompt':<40}")
    print("-" * 115)

    for r in rows:
        prompt = (r["prompt_used"] or "")[:38]
        actual = r["actual_tool"] or "(none)"
        print(
            f"{r['expected_tool']:<30} {actual:<30} "
            f"{r['persona_style']:<12} {prompt}"
        )
    print()
