"""CLI for the Cairn benchmark framework.

Usage:
    python -m benchmarks run --model qwen2.5:7b
    python -m benchmarks run --model qwen2.5:7b --tool cairn_list_acts
    python -m benchmarks run --all-models
    python -m benchmarks analyze [--model MODEL]
    python -m benchmarks list-tools
    python -m benchmarks list-cases [--tool TOOL] [--variant VARIANT]
    python -m benchmarks export --output FILE.csv

    python -m benchmarks run-memory --model qwen2.5:7b
    python -m benchmarks run-memory --all-models
    python -m benchmarks run-memory --model qwen2.5:7b --category positive
    python -m benchmarks run-memory --model qwen2.5:7b --memory-type commitment
    python -m benchmarks run-memory --model qwen2.5:7b --resume
    python -m benchmarks analyze-memory [--model MODEL]
    python -m benchmarks list-memory-cases [--category CATEGORY] [--type TYPE]
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

# Ensure benchmarks package is importable when run as __main__
BENCHMARKS_DIR = Path(__file__).parent
PROJECT_DIR = BENCHMARKS_DIR.parent
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))
if str(PROJECT_DIR / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR / "src"))


def cmd_run(args: argparse.Namespace) -> None:
    """Run benchmark cases."""
    from benchmarks.models import MODEL_MATRIX, is_anthropic_model
    from benchmarks.runner import BenchmarkRunner

    models = [args.model] if args.model else [m["name"] for m in MODEL_MATRIX]

    for model_name in models:
        runner = BenchmarkRunner(
            model_name=model_name,
            tool_filter=args.tool,
            variant_filter=args.variant,
            resume=args.resume,
            db_path=args.db,
            ollama_url=args.ollama_url,
            timeout=args.timeout,
            anthropic_key=args.anthropic_credential,
            corpus_file=Path(args.corpus) if args.corpus else None,
        )
        try:
            run_uuid = runner.run()
            print(f"Run complete: {run_uuid}")
        finally:
            runner.close()


def cmd_analyze(args: argparse.Namespace) -> None:
    """Analyze benchmark results."""
    from benchmarks.analysis import (
        print_failures,
        print_persona_breakdown,
        print_summary,
        print_tool_breakdown,
    )
    from benchmarks.db import init_db

    conn = init_db(args.db)

    print_summary(conn, model_name=args.model)

    if args.model:
        if args.tools:
            print_tool_breakdown(conn, args.model)
        if args.personas:
            print_persona_breakdown(conn, args.model)
        if args.failures:
            print_failures(conn, args.model, limit=args.failures)
    elif args.failures:
        print_failures(conn, limit=args.failures)

    conn.close()


def cmd_list_tools(args: argparse.Namespace) -> None:
    """List post-purge tool inventory with corpus coverage."""
    from benchmarks.corpus import check_corpus_coverage, load_corpus

    coverage = check_corpus_coverage()
    cases = load_corpus()

    # Count cases per tool
    tool_counts: dict[str, int] = {}
    for c in cases:
        tool_counts[c.tool_name] = tool_counts.get(c.tool_name, 0) + 1

    print(f"\nPost-purge tool inventory: {coverage['tools_total']} tools")
    print(f"Corpus coverage: {len(coverage['tools_covered'])}/{coverage['tools_total']}")
    print(f"Total cases: {coverage['cases_total']}")
    print()

    print(f"{'Tool':<40} {'Cases':>6}")
    print("-" * 48)

    for tool in sorted(coverage["tools_covered"]):
        print(f"  {tool:<38} {tool_counts.get(tool, 0):>6}")

    if coverage["tools_missing"]:
        print(f"\nMissing from corpus ({len(coverage['tools_missing'])}):")
        for tool in coverage["tools_missing"]:
            print(f"  {tool}")

    if coverage["orphan_cases"]:
        print(f"\nOrphan corpus entries (tool removed):")
        for tool in coverage["orphan_cases"]:
            print(f"  {tool}")

    print()


def cmd_list_cases(args: argparse.Namespace) -> None:
    """List corpus test cases."""
    from benchmarks.corpus import load_corpus

    cases = load_corpus(
        tool_name=args.tool,
        variant=args.variant,
    )

    print(f"\n{'Case ID':<45} {'Tool':<30} {'Variant':<12}")
    print("-" * 90)

    for c in cases:
        print(f"  {c.case_id:<43} {c.tool_name:<30} {c.variant:<12}")

    print(f"\nTotal: {len(cases)} cases")
    print()


def cmd_run_memory(args: argparse.Namespace) -> None:
    """Run memory benchmark cases through the memory pipeline."""
    from benchmarks.corpus import load_persona_profiles
    from benchmarks.memory_corpus import load_memory_corpus
    from benchmarks.models import MODEL_MATRIX

    models = [args.model] if args.model else [m["name"] for m in MODEL_MATRIX]

    cases = load_memory_corpus(
        category=args.category,
        memory_type=args.memory_type,
    )

    if not cases:
        print("No memory test cases match the specified filters.")
        return

    profiles = load_persona_profiles()
    if not profiles:
        print("No persona profiles found in tools/test_profiles/.")
        return

    print(f"Loaded {len(cases)} memory test cases, {len(profiles)} personas.")

    # Attempt to import the runner; it may not be implemented yet.
    try:
        from benchmarks.memory_runner import MemoryBenchmarkRunner
    except ImportError:
        print(
            "ERROR: benchmarks.memory_runner is not yet implemented.\n"
            "Create benchmarks/memory_runner.py with MemoryBenchmarkRunner before running."
        )
        return

    for model_name in models:
        runner = MemoryBenchmarkRunner(
            model_name=model_name,
            db_path=args.db,
            ollama_url=args.ollama_url,
            timeout=args.timeout,
        )
        try:
            run_uuid = runner.run(cases, profiles, resume=args.resume)
            print(f"Run complete: {run_uuid}")
        finally:
            runner.close()


def cmd_analyze_memory(args: argparse.Namespace) -> None:
    """Analyze memory benchmark results."""
    from benchmarks.db import init_db
    from benchmarks.memory_analysis import (
        print_memory_category_breakdown,
        print_memory_failures,
        print_memory_persona_breakdown,
        print_memory_summary,
        print_memory_type_breakdown,
    )

    conn = init_db(args.db)

    print_memory_summary(conn, model_name=args.model)

    if args.model:
        if args.types:
            print_memory_type_breakdown(conn, args.model)
        if args.categories:
            print_memory_category_breakdown(conn, args.model)
        if args.personas:
            print_memory_persona_breakdown(conn, args.model)
        if args.failures is not None:
            print_memory_failures(conn, args.model, limit=args.failures)
    else:
        if args.types:
            print_memory_type_breakdown(conn)
        if args.categories:
            print_memory_category_breakdown(conn)
        if args.personas:
            print_memory_persona_breakdown(conn)
        if args.failures is not None:
            print_memory_failures(conn, limit=args.failures)

    conn.close()


def cmd_list_memory_cases(args: argparse.Namespace) -> None:
    """List memory corpus test cases."""
    from benchmarks.memory_corpus import load_memory_corpus

    cases = load_memory_corpus(
        category=args.category,
        memory_type=args.type,
    )

    print(f"\n{'Case ID':<45} {'Cat':<12} {'Type':<14} {'Variant':<14} {'Expected':<10}")
    print("-" * 100)

    for c in cases:
        mem_type = c.memory_type or "—"
        print(
            f"  {c.case_id:<43} {c.category:<12} {mem_type:<14} "
            f"{c.variant:<14} {c.expected_detection:<10}"
        )

    print(f"\nTotal: {len(cases)} cases")
    print()


def cmd_export(args: argparse.Namespace) -> None:
    """Export results to CSV."""
    from benchmarks.db import init_db

    conn = init_db(args.db)

    rows = conn.execute(
        """
        SELECT
            r.model_name, r.model_param_count,
            br.case_id, br.persona_id, br.persona_style,
            br.prompt_used, br.tool_selected, br.tool_args,
            br.tool_execution_ok, br.tool_error, br.response_text,
            br.latency_ms, br.tokens_prompt, br.tokens_completion,
            br.pipeline_error,
            br.tool_match, br.args_match, br.execution_success,
            br.response_quality,
            tc.tool_name AS expected_tool_group, tc.variant,
            tc.expected_tool
        FROM benchmark_results br
        JOIN benchmark_runs r ON r.id = br.run_id
        JOIN test_cases tc ON tc.case_id = br.case_id
        ORDER BY r.model_name, br.case_id, br.persona_id
        """
    ).fetchall()

    if not rows:
        print("No results to export.")
        conn.close()
        return

    output = Path(args.output)
    with open(output, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([desc[0] for desc in conn.execute(
            "SELECT * FROM benchmark_results LIMIT 0"
        ).description])
        # Actually write from the join query
        writer.writerow(rows[0].keys())
        for row in rows:
            writer.writerow(tuple(row))

    print(f"Exported {len(rows)} rows to {output}")
    conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="benchmarks",
        description="Cairn MCP tool benchmark framework",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    p_run = sub.add_parser("run", help="Run benchmark cases")
    p_run.add_argument("--model", help="Model name (e.g. qwen2.5:7b)")
    p_run.add_argument("--all-models", action="store_true", help="Run all models")
    p_run.add_argument("--tool", help="Restrict to one tool")
    p_run.add_argument("--variant", help="Restrict to one variant type")
    p_run.add_argument("--resume", action="store_true", help="Skip completed cases")
    p_run.add_argument("--timeout", type=int, default=120, help="Per-case timeout (s)")
    p_run.add_argument("--db", help="Database path override")
    p_run.add_argument("--ollama-url", default="http://localhost:11434")
    p_run.add_argument("--anthropic-credential", help="Anthropic API key")
    p_run.add_argument("--corpus", help="Corpus file path override")

    # --- analyze ---
    p_analyze = sub.add_parser("analyze", help="Analyze results")
    p_analyze.add_argument("--model", help="Focus on specific model")
    p_analyze.add_argument("--tools", action="store_true", help="Show per-tool breakdown")
    p_analyze.add_argument("--personas", action="store_true", help="Show per-persona breakdown")
    p_analyze.add_argument("--failures", type=int, nargs="?", const=20, help="Show failures")
    p_analyze.add_argument("--db", help="Database path override")

    # --- list-tools ---
    sub.add_parser("list-tools", help="Show tool inventory and corpus coverage")

    # --- list-cases ---
    p_cases = sub.add_parser("list-cases", help="List corpus test cases")
    p_cases.add_argument("--tool", help="Filter by tool name")
    p_cases.add_argument("--variant", help="Filter by variant type")

    # --- run-memory ---
    p_run_mem = sub.add_parser("run-memory", help="Run memory benchmark cases")
    _mem_model_group = p_run_mem.add_mutually_exclusive_group()
    _mem_model_group.add_argument("--model", help="Model name (e.g. qwen2.5:7b)")
    _mem_model_group.add_argument("--all-models", action="store_true", help="Run all models")
    p_run_mem.add_argument(
        "--category",
        choices=["positive", "negative", "edge", "regression"],
        help="Restrict to one corpus category",
    )
    p_run_mem.add_argument(
        "--memory-type",
        dest="memory_type",
        choices=["fact", "preference", "priority", "commitment", "relationship"],
        help="Restrict to one memory type",
    )
    p_run_mem.add_argument("--resume", action="store_true", help="Skip already-completed cases")
    p_run_mem.add_argument("--timeout", type=int, default=120, help="Per-case timeout (s)")
    p_run_mem.add_argument("--db", help="Database path override")
    p_run_mem.add_argument("--ollama-url", default="http://localhost:11434")

    # --- analyze-memory ---
    p_analyze_mem = sub.add_parser("analyze-memory", help="Analyze memory benchmark results")
    p_analyze_mem.add_argument("--model", help="Focus on specific model")
    p_analyze_mem.add_argument("--types", action="store_true", help="Show per-type breakdown")
    p_analyze_mem.add_argument(
        "--categories", action="store_true", help="Show positive/negative/edge/regression breakdown"
    )
    p_analyze_mem.add_argument("--personas", action="store_true", help="Show per-persona breakdown")
    p_analyze_mem.add_argument(
        "--failures", type=int, nargs="?", const=20, help="Show failures (default 20)"
    )
    p_analyze_mem.add_argument("--db", help="Database path override")

    # --- list-memory-cases ---
    p_list_mem = sub.add_parser("list-memory-cases", help="List memory corpus test cases")
    p_list_mem.add_argument(
        "--category",
        choices=["positive", "negative", "edge", "regression"],
        help="Filter by category",
    )
    p_list_mem.add_argument(
        "--type",
        choices=["fact", "preference", "priority", "commitment", "relationship"],
        help="Filter by memory type",
    )

    # --- export ---
    p_export = sub.add_parser("export", help="Export results to CSV")
    p_export.add_argument("--output", required=True, help="Output CSV file path")
    p_export.add_argument("--db", help="Database path override")

    args = parser.parse_args()

    if args.command == "run":
        if not args.model and not args.all_models:
            parser.error("Specify --model or --all-models")
        cmd_run(args)
    elif args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "list-tools":
        cmd_list_tools(args)
    elif args.command == "list-cases":
        cmd_list_cases(args)
    elif args.command == "export":
        cmd_export(args)
    elif args.command == "run-memory":
        if not args.model and not args.all_models:
            parser.error("Specify --model or --all-models")
        cmd_run_memory(args)
    elif args.command == "analyze-memory":
        cmd_analyze_memory(args)
    elif args.command == "list-memory-cases":
        cmd_list_memory_cases(args)


if __name__ == "__main__":
    main()
