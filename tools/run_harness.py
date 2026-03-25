#!/usr/bin/env python3
"""Run the E2E testing harness for Cairn across multiple models.

Usage:
    python3 tools/run_harness.py                          # all profiles, all models ≤20B
    python3 tools/run_harness.py priya_chandrasekaran      # one profile, all models
    python3 tools/run_harness.py --dry-run                 # show questions only
    python3 tools/run_harness.py --resume run-xxx-model     # resume a specific run
    python3 tools/run_harness.py --limit 3                 # 3 questions/profile
    python3 tools/run_harness.py --report run-xxx-model     # analyze a prior run
    python3 tools/run_harness.py --compare                 # cross-model comparison
    python3 tools/run_harness.py --models mistral qwen2.5:3b  # specific models only
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

# Add tools/ to path so harness package is importable
TOOLS_DIR = Path(__file__).parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# Add src/ to path for cairn imports
CAIRN_SRC = TOOLS_DIR.parent / "src"
if str(CAIRN_SRC) not in sys.path:
    sys.path.insert(0, str(CAIRN_SRC))

PROFILES_DIR = TOOLS_DIR / "test_profiles"

# Models to test (≤20B parameters), ordered small → large
DEFAULT_MODELS = [
    "llama3.2:1b",
    "qwen2.5:3b",
    "phi3:mini-128k",
    "mistral:latest",
    "CognitiveComputations/dolphin-llama3.1:8b",
    "llama3.1:8b-instruct-q5_K_M",
    "qwen2.5:14b",
    "magistral:24b",
]


def _model_slug(model_name: str) -> str:
    """Convert model name to a filesystem/ID-safe slug."""
    return model_name.replace("/", "_").replace(":", "-").replace(".", "")


def discover_profiles(filter_ids: list[str] | None = None) -> dict[str, str]:
    """Discover generated profile directories."""
    if not PROFILES_DIR.exists():
        print(f"ERROR: No profiles directory at {PROFILES_DIR}")
        print("Run 'python3 tools/generate_test_profiles.py' first.")
        sys.exit(1)

    profiles: dict[str, str] = {}
    for entry in sorted(PROFILES_DIR.iterdir()):
        if entry.is_dir() and (entry / "talkingrock.db").exists():
            pid = entry.name
            if filter_ids is None or pid in filter_ids:
                profiles[pid] = str(entry)

    if not profiles:
        if filter_ids:
            print(f"ERROR: No matching profiles found for: {filter_ids}")
            available = [e.name for e in PROFILES_DIR.iterdir() if e.is_dir()]
            print(f"Available: {available}")
        else:
            print("ERROR: No profiles with talkingrock.db found.")
        sys.exit(1)

    return profiles


def main():
    parser = argparse.ArgumentParser(
        description="E2E testing harness for Cairn (multi-model)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--profiles",
        nargs="*",
        default=None,
        help="Profile IDs to test (default: all)",
    )
    parser.add_argument(
        "--models",
        nargs="*",
        default=None,
        help=f"Ollama models to test (default: all {len(DEFAULT_MODELS)} models ≤20B)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print questions without calling LLM",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Max questions per profile (default: 8)",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Resume a previous run by run_id (single model run)",
    )
    parser.add_argument(
        "--report",
        type=str,
        default=None,
        help="Print analysis report for a prior run_id",
    )
    parser.add_argument(
        "--compare",
        action="store_true",
        help="Print cross-model comparison of all results",
    )
    parser.add_argument(
        "--list-runs",
        action="store_true",
        help="List all prior harness runs",
    )

    args = parser.parse_args()

    # ── Analysis-only modes ──

    if args.list_runs:
        from harness.analysis import list_runs

        runs = list_runs()
        if not runs:
            print("No prior runs found.")
            return
        print(f"\n{'Run ID':<45} {'Model':<35} {'Started':<22} {'Q':>4} {'OK':>4}")
        print("-" * 115)
        for r in runs:
            print(
                f"{r['run_id']:<45} {r['model_name']:<35} "
                f"{r['started_at'][:19]:<22} "
                f"{r['total_questions']:>4} {r['completed_questions']:>4}"
            )
        return

    if args.report:
        from harness.analysis import print_full_report

        print_full_report(args.report)
        return

    if args.compare:
        from harness.analysis import compare_models, compare_models_by_department

        compare_models()
        compare_models_by_department()
        return

    # ── Single-run resume ──

    if args.resume:
        # Resuming requires knowing the model — extract from the run record
        from harness.analysis import list_runs

        runs = list_runs()
        run_match = next((r for r in runs if r["run_id"] == args.resume), None)
        if not run_match:
            print(f"ERROR: No run found with id '{args.resume}'")
            return

        model = run_match["model_name"]
        filter_ids = args.profiles if args.profiles else None
        profile_dirs = discover_profiles(filter_ids)

        from harness.runner import run_harness

        run_harness(
            profile_dirs,
            args.resume,
            model,
            limit=args.limit,
            dry_run=args.dry_run,
            resume=True,
        )
        return

    # ── Full execution: loop over models ──

    models = args.models or DEFAULT_MODELS
    filter_ids = args.profiles if args.profiles else None
    profile_dirs = discover_profiles(filter_ids)

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    total_models = len(models)
    total_calls = total_models * len(profile_dirs) * (args.limit or 8)

    print(f"\n{'#' * 60}")
    print(f"CAIRN E2E HARNESS — MULTI-MODEL RUN")
    print(f"{'#' * 60}")
    print(f"Models:    {total_models}")
    print(f"Profiles:  {len(profile_dirs)}")
    print(f"Questions: {args.limit or 8} per profile")
    print(f"Total LLM calls: {total_calls}")
    print(f"Models: {', '.join(models)}")
    print(f"{'#' * 60}\n")

    from harness.runner import run_harness

    for m_idx, model in enumerate(models, 1):
        slug = _model_slug(model)
        run_id = f"run-{timestamp}-{slug}"

        print(f"\n{'#' * 60}")
        print(f"MODEL {m_idx}/{total_models}: {model}")
        print(f"{'#' * 60}")

        run_harness(
            profile_dirs,
            run_id,
            model,
            limit=args.limit,
            dry_run=args.dry_run,
        )

    # Print cross-model comparison at the end
    if not args.dry_run:
        print(f"\n\n{'#' * 60}")
        print("CROSS-MODEL COMPARISON")
        print(f"{'#' * 60}")

        from harness.analysis import compare_models

        compare_models()


if __name__ == "__main__":
    main()
