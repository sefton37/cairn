"""Analysis and reporting for Cairn memory benchmark results.

Named query wrappers around the pre-built memory views, plus human-readable
print functions for CLI output.
"""

from __future__ import annotations

import sqlite3


def memory_model_summary(conn: sqlite3.Connection) -> list[dict]:
    """Per-model accuracy across all 5 memory scoring dimensions from v_mem_model_accuracy."""
    rows = conn.execute("SELECT * FROM v_mem_model_accuracy").fetchall()
    return [dict(row) for row in rows]


def memory_type_accuracy(
    conn: sqlite3.Connection, model_name: str | None = None
) -> list[dict]:
    """Detection and type accuracy broken down by expected memory type."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_mem_type_accuracy WHERE model_name = ?", (model_name,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v_mem_type_accuracy").fetchall()
    return [dict(row) for row in rows]


def memory_category_accuracy(
    conn: sqlite3.Connection, model_name: str | None = None
) -> list[dict]:
    """Accuracy broken down by corpus category (positive/negative/edge/regression)."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_mem_category_accuracy WHERE model_name = ?", (model_name,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v_mem_category_accuracy").fetchall()
    return [dict(row) for row in rows]


def memory_persona_accuracy(
    conn: sqlite3.Connection, model_name: str | None = None
) -> list[dict]:
    """Accuracy broken down by persona style."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_mem_persona_accuracy WHERE model_name = ?", (model_name,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM v_mem_persona_accuracy").fetchall()
    return [dict(row) for row in rows]


def memory_failures(
    conn: sqlite3.Connection, model_name: str | None = None, limit: int = 20
) -> list[dict]:
    """Rows where detection or type classification failed."""
    if model_name:
        rows = conn.execute(
            "SELECT * FROM v_mem_failures WHERE model_name = ? LIMIT ?",
            (model_name, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM v_mem_failures LIMIT ?", (limit,)
        ).fetchall()
    return [dict(row) for row in rows]


def print_memory_summary(conn: sqlite3.Connection, model_name: str | None = None) -> None:
    """Print human-readable memory model accuracy summary.

    Columns: model, params, N, detect%, type%, route%, narrative%, gate%, avg_latency_ms
    """
    rows = memory_model_summary(conn)
    if model_name:
        rows = [r for r in rows if r["model_name"] == model_name]

    if not rows:
        print("No memory benchmark results found.")
        return

    print(
        f"\n{'Model':<35} {'Params':<8} {'N':>5} "
        f"{'Detect%':>8} {'Type%':>7} {'Route%':>7} "
        f"{'Narr%':>6} {'Gate%':>6} {'Lat(ms)':>8}"
    )
    print("-" * 100)

    for r in rows:
        detect = r["detection_pct"]
        type_p = r["type_pct"]
        route = r["routing_pct"]
        narr = r["narrative_pct"]
        gate = r["auto_approve_pct"]
        lat = r["avg_latency_ms"]

        print(
            f"{r['model_name']:<35} {r['model_param_count'] or '?':<8} "
            f"{r['total']:>5} "
            f"{detect if detect is not None else '—':>7}% "
            f"{(f'{type_p:.1f}%') if type_p is not None else '—':>7} "
            f"{(f'{route:.1f}%') if route is not None else '—':>7} "
            f"{(f'{narr:.1f}%') if narr is not None else '—':>6} "
            f"{(f'{gate:.1f}%') if gate is not None else '—':>6} "
            f"{int(lat) if lat is not None else '—':>8}"
        )
    print()


def print_memory_type_breakdown(
    conn: sqlite3.Connection, model_name: str | None = None
) -> None:
    """Print per-memory-type detection and classification accuracy."""
    rows = memory_type_accuracy(conn, model_name)
    if not rows:
        label = f" for {model_name}" if model_name else ""
        print(f"No memory type results found{label}.")
        return

    print(f"\n{'Model':<35} {'Type':<14} {'N':>5} {'Detect%':>8} {'Type%':>7}")
    print("-" * 75)

    for r in rows:
        type_p = r["type_pct"]
        print(
            f"{r['model_name']:<35} {r['expected_type'] or '(none)':<14} {r['total']:>5} "
            f"{r['detection_pct']:>7.1f}% "
            f"{(f'{type_p:.1f}%') if type_p is not None else '—':>7}"
        )
    print()


def print_memory_category_breakdown(
    conn: sqlite3.Connection, model_name: str | None = None
) -> None:
    """Print accuracy by corpus category: positive/negative/edge/regression."""
    rows = memory_category_accuracy(conn, model_name)
    if not rows:
        label = f" for {model_name}" if model_name else ""
        print(f"No memory category results found{label}.")
        return

    print(f"\n{'Model':<35} {'Category':<12} {'N':>5} {'Detect%':>8} {'Type%':>7}")
    print("-" * 73)

    for r in rows:
        type_p = r["type_pct"]
        print(
            f"{r['model_name']:<35} {r['category']:<12} {r['total']:>5} "
            f"{r['detection_pct']:>7.1f}% "
            f"{(f'{type_p:.1f}%') if type_p is not None else '—':>7}"
        )
    print()


def print_memory_persona_breakdown(
    conn: sqlite3.Connection, model_name: str | None = None
) -> None:
    """Print per-persona-style detection accuracy and latency."""
    rows = memory_persona_accuracy(conn, model_name)
    if not rows:
        label = f" for {model_name}" if model_name else ""
        print(f"No memory persona results found{label}.")
        return

    print(f"\n{'Model':<35} {'Style':<15} {'N':>5} {'Detect%':>8} {'Type%':>7} {'Lat(ms)':>8}")
    print("-" * 83)

    for r in rows:
        type_p = r["type_pct"]
        lat = r["avg_latency_ms"]
        print(
            f"{r['model_name']:<35} {r['persona_style']:<15} {r['total']:>5} "
            f"{r['detection_pct']:>7.1f}% "
            f"{(f'{type_p:.1f}%') if type_p is not None else '—':>7} "
            f"{int(lat) if lat is not None else '—':>8}"
        )
    print()


def print_memory_failures(
    conn: sqlite3.Connection, model_name: str | None = None, limit: int = 20
) -> None:
    """Print memory pipeline failure details with prompt preview."""
    rows = memory_failures(conn, model_name, limit)
    if not rows:
        print("No memory failures found.")
        return

    print(
        f"\n{'Model':<25} {'Case':<35} {'Cat':<10} "
        f"{'Exp Det':<9} {'Act Det':<9} {'Exp Type':<12} {'Act Type':<12} {'Prompt':<35}"
    )
    print("-" * 150)

    for r in rows:
        prompt = (r["styled_user_message"] or "")[:33]
        actual_det = r["actual_detection"] or "(none)"
        actual_type = r["actual_type"] or "(none)"
        exp_type = r["expected_type"] or "—"
        error_flag = " [ERR]" if r["pipeline_error"] else ""
        print(
            f"{r['model_name']:<25} {r['case_id']:<35} {r['category']:<10} "
            f"{r['expected_detection']:<9} {actual_det:<9} "
            f"{exp_type:<12} {actual_type:<12} {prompt}{error_flag}"
        )
    print()
