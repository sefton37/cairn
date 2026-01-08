#!/usr/bin/env python3
"""Test harness for RIVA code execution.

Run with: python scripts/test_riva_harness.py [prompt]

Examples:
    # Without LLM (heuristics only)
    python scripts/test_riva_harness.py "Create a hello.py with a greet function"

    # With Ollama
    python scripts/test_riva_harness.py --ollama "Add type hints to src/reos/models.py"

    # With Anthropic
    python scripts/test_riva_harness.py --anthropic "Fix the bug in calculator.py"

    # List recent sessions
    python scripts/test_riva_harness.py --list-sessions

    # Show session details
    python scripts/test_riva_harness.py --show-session exec-abc123
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from reos.code_mode import (
    CodeExecutor,
    CodeSandbox,
    SessionLogger,
    list_sessions,
    get_session_log,
)
from reos.code_mode.streaming import ExecutionObserver
from reos.play_fs import Act


class VerboseObserver(ExecutionObserver):
    """Observer that prints all activity to stdout."""

    def __init__(self) -> None:
        self.start_time = datetime.now(timezone.utc)

    def _elapsed(self) -> str:
        delta = datetime.now(timezone.utc) - self.start_time
        return f"[{delta.total_seconds():.1f}s]"

    def on_phase_change(self, phase: Any, **kwargs: Any) -> None:
        # phase might be LoopStatus enum or string
        phase_str = phase.value if hasattr(phase, 'value') else str(phase)
        print(f"\n{'='*60}")
        print(f"{self._elapsed()} PHASE: {phase_str.upper()}")
        print(f"{'='*60}")

    def on_activity(self, message: str, module: str = "", **kwargs: Any) -> None:
        prefix = f"[{module}]" if module else ""
        print(f"{self._elapsed()} {prefix} {message}")

    def on_step_start(self, step_id: str, description: str, **kwargs: Any) -> None:
        print(f"\n{self._elapsed()} STEP: {description}")
        print(f"  ID: {step_id}")

    def on_step_complete(
        self, step_id: str, success: bool, output: str = "", **kwargs: Any
    ) -> None:
        status = "✓" if success else "✗"
        print(f"{self._elapsed()} {status} Step complete")
        if output:
            # Truncate long output
            lines = output.strip().split("\n")
            if len(lines) > 5:
                for line in lines[:3]:
                    print(f"    {line[:100]}")
                print(f"    ... ({len(lines) - 3} more lines)")
            else:
                for line in lines:
                    print(f"    {line[:100]}")

    def on_iteration_start(self, iteration: int, **kwargs: Any) -> None:
        print(f"\n{self._elapsed()} --- Iteration {iteration} ---")

    def on_iteration_complete(
        self, iteration: int, status: str, **kwargs: Any
    ) -> None:
        print(f"{self._elapsed()} Iteration {iteration} complete: {status}")

    def on_error(self, error: str, **kwargs: Any) -> None:
        print(f"\n{self._elapsed()} ERROR: {error}")

    def on_complete(self, success: bool, message: str = "", **kwargs: Any) -> None:
        status = "SUCCESS" if success else "FAILED"
        print(f"\n{'='*60}")
        print(f"{self._elapsed()} COMPLETE: {status}")
        if message:
            print(f"  {message}")
        print(f"{'='*60}\n")


def get_ollama_provider(
    url: str | None = None,
    model: str | None = None,
) -> Any:
    """Create an Ollama provider using ReOS settings if not specified."""
    from reos.db import get_db
    from reos.providers.ollama import OllamaProvider
    from reos.settings import settings

    db = get_db()

    # Use ReOS settings if not explicitly provided
    if url is None:
        url = settings.ollama_url or "http://localhost:11434"
    if model is None:
        stored_model = db.get_state(key="ollama_model")
        model = stored_model if isinstance(stored_model, str) else None

    print(f"Connecting to Ollama at {url}...")
    provider = OllamaProvider(url=url, model=model)

    # Test connection
    try:
        health = provider.check_health()
        if health.reachable:
            print(f"  Connected! Model: {health.current_model or model}")
            if health.model_count:
                print(f"  Available models: {health.model_count}")
        else:
            print(f"  Warning: {health.error}")
    except Exception as e:
        print(f"  Connection error: {e}")
        return None

    return provider


def get_anthropic_provider(
    model: str = "claude-sonnet-4-20250514",
    api_key: str | None = None,
) -> Any:
    """Create an Anthropic provider."""
    from reos.providers.anthropic import AnthropicProvider
    from reos.providers.secrets import get_api_key

    # Get API key from keyring or environment
    key = api_key or os.environ.get("ANTHROPIC_API_KEY") or get_api_key("anthropic")

    if not key:
        print("Error: No Anthropic API key found.")
        print("  Set ANTHROPIC_API_KEY environment variable or store in keyring.")
        return None

    print(f"Connecting to Anthropic with model {model}...")
    provider = AnthropicProvider(api_key=key, model=model)

    # Test connection
    try:
        health = provider.check_health()
        if health.reachable:
            print(f"  Connected! Model: {health.current_model or model}")
        else:
            print(f"  Warning: {health.error}")
    except Exception as e:
        print(f"  Connection error: {e}")
        return None

    return provider


def run_riva_test(
    prompt: str,
    repo_path: Path,
    use_riva: bool = True,
    max_iterations: int = 3,
    llm: Any = None,
    llm_name: str = "none",
) -> None:
    """Run a RIVA test with the given prompt."""
    print(f"\n{'#'*60}")
    print(f"# RIVA Test Harness")
    print(f"{'#'*60}")
    print(f"Prompt: {prompt}")
    print(f"Repo: {repo_path}")
    print(f"RIVA Mode: {use_riva}")
    print(f"Max Iterations: {max_iterations}")
    print(f"LLM: {llm_name}")
    print()

    # Create sandbox
    sandbox = CodeSandbox(repo_path)

    # Create observer
    observer = VerboseObserver()

    # Create executor
    executor = CodeExecutor(
        sandbox=sandbox,
        llm=llm,
        observer=observer,
    )

    # Create a test Act
    act = Act(
        act_id="riva-test",
        title="RIVA Test Act",
        notes="Testing RIVA execution",
        repo_path=str(repo_path),
    )

    # Run execution
    print("Starting execution...")
    result = executor.execute(
        prompt=prompt,
        act=act,
        max_iterations=max_iterations,
        use_riva=use_riva,
    )

    # Print result
    print(f"\n{'='*60}")
    print("RESULT")
    print(f"{'='*60}")
    print(f"Success: {result.success}")
    print(f"Message: {result.message}")
    print(f"Iterations: {result.total_iterations}")
    print(f"Files changed: {result.files_changed}")
    if result.state:
        print(f"Final status: {result.state.status.value}")

    # Show session log location
    if hasattr(executor, "_session_logger") and executor._session_logger:
        logger = executor._session_logger
        print(f"\nSession Logs:")
        print(f"  Log file: {logger.log_file}")
        print(f"  JSON file: {logger.json_file}")

        # Print summary of log entries
        if logger.json_file.exists():
            with open(logger.json_file) as f:
                data = json.load(f)
            print(f"\nLog Summary ({len(data.get('entries', []))} entries):")

            # Count by level
            levels = {}
            for entry in data.get("entries", []):
                level = entry.get("level", "INFO")
                levels[level] = levels.get(level, 0) + 1
            print(f"  Levels: {dict(levels)}")

            # Show errors if any
            errors = [e for e in data.get("entries", []) if e.get("level") == "ERROR"]
            if errors:
                print(f"\n  ERRORS ({len(errors)}):")
                for err in errors[:5]:
                    print(f"    - {err.get('module', '?')}/{err.get('action', '?')}: {err.get('message', '')[:60]}")

            # Show LLM calls if any
            llm_calls = [e for e in data.get("entries", []) if "llm" in e.get("action", "").lower()]
            if llm_calls:
                print(f"\n  LLM Calls ({len(llm_calls)}):")
                for call in llm_calls[:3]:
                    model = call.get("data", {}).get("model", "?")
                    print(f"    - {call.get('action', '?')} (model: {model})")

    # Show files changed
    if result.files_changed:
        print(f"\nFiles Changed ({len(result.files_changed)}):")
        for f in result.files_changed[:10]:
            file_path = repo_path / f
            if file_path.exists():
                size = file_path.stat().st_size
                print(f"  {f} ({size} bytes)")
                # Show first few lines of content
                try:
                    content = file_path.read_text()
                    lines = content.split("\n")[:5]
                    for line in lines:
                        print(f"    | {line[:70]}")
                    if len(content.split("\n")) > 5:
                        print(f"    | ... ({len(content.split(chr(10))) - 5} more lines)")
                except Exception:
                    pass


def show_recent_sessions(limit: int = 5) -> None:
    """Show recent session logs."""
    print(f"\n{'='*60}")
    print("RECENT SESSIONS")
    print(f"{'='*60}")

    sessions = list_sessions(limit=limit)
    if not sessions:
        print("No sessions found.")
        return

    for session in sessions:
        print(f"\nSession: {session.get('session_id', '?')[:20]}...")
        print(f"  Prompt: {session.get('prompt', '?')[:50]}...")
        print(f"  Started: {session.get('started_at', '?')}")
        print(f"  Outcome: {session.get('outcome', '?')}")
        print(f"  Entries: {session.get('entry_count', 0)}")


def show_session_detail(session_id: str) -> None:
    """Show detailed session log."""
    data = get_session_log(session_id)
    if not data:
        print(f"Session not found: {session_id}")
        return

    print(f"\n{'='*60}")
    print(f"SESSION: {data.get('session_id', '?')}")
    print(f"{'='*60}")
    print(f"Prompt: {data.get('prompt', '?')}")
    print(f"Started: {data.get('started_at', '?')}")
    print(f"Duration: {data.get('duration_seconds', 0):.1f}s")
    print(f"Outcome: {data.get('outcome', '?')}")

    print(f"\nEntries ({len(data.get('entries', []))}):")
    for entry in data.get("entries", []):
        ts = entry.get("timestamp", "")
        level = entry.get("level", "INFO")
        module = entry.get("module", "?")
        action = entry.get("action", "?")
        msg = entry.get("message", "")

        # Color coding for levels
        level_str = f"[{level}]".ljust(7)
        print(f"  {ts} {level_str} {module}/{action}")
        if msg:
            print(f"           {msg[:80]}")

        # Show data for errors
        if level == "ERROR" and entry.get("data"):
            for k, v in entry["data"].items():
                print(f"             {k}: {str(v)[:60]}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Test harness for RIVA code execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "prompt",
        nargs="?",
        default="Create a file called hello.py with a function greet() that returns 'Hello, World!'",
        help="The coding task prompt",
    )
    parser.add_argument(
        "--repo",
        type=Path,
        default=Path(__file__).parent.parent,
        help="Repository path (default: ReOS repo)",
    )
    parser.add_argument(
        "--no-riva",
        action="store_true",
        help="Disable RIVA mode (use standard execution)",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=3,
        help="Maximum iterations (default: 3)",
    )

    # LLM options
    llm_group = parser.add_mutually_exclusive_group()
    llm_group.add_argument(
        "--ollama",
        nargs="?",
        const="__use_settings__",
        metavar="MODEL",
        help="Use Ollama with specified model (default: from ReOS settings)",
    )
    llm_group.add_argument(
        "--anthropic",
        nargs="?",
        const="__use_settings__",
        metavar="MODEL",
        help="Use Anthropic with specified model (default: from ReOS settings)",
    )

    parser.add_argument(
        "--ollama-url",
        default=None,
        help="Ollama server URL (default: from ReOS settings)",
    )

    # Session management
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        help="List recent sessions instead of running",
    )
    parser.add_argument(
        "--show-session",
        type=str,
        help="Show details for a specific session ID",
    )

    args = parser.parse_args()

    if args.list_sessions:
        show_recent_sessions()
        return

    if args.show_session:
        show_session_detail(args.show_session)
        return

    # Set up LLM
    llm = None
    llm_name = "none (heuristics)"

    if args.ollama:
        # Use settings if sentinel value, otherwise use provided model
        model = None if args.ollama == "__use_settings__" else args.ollama
        llm = get_ollama_provider(url=args.ollama_url, model=model)
        if llm:
            # Get actual model name from provider
            health = llm.check_health()
            actual_model = health.current_model or model or "auto"
            llm_name = f"Ollama ({actual_model})"
        else:
            print("\nFalling back to heuristics mode.")

    elif args.anthropic:
        model = None if args.anthropic == "__use_settings__" else args.anthropic
        llm = get_anthropic_provider(model=model)
        if llm:
            llm_name = f"Anthropic ({model or 'default'})"
        else:
            print("\nFalling back to heuristics mode.")

    # Run test
    run_riva_test(
        prompt=args.prompt,
        repo_path=args.repo,
        use_riva=not args.no_riva,
        max_iterations=args.max_iterations,
        llm=llm,
        llm_name=llm_name,
    )


if __name__ == "__main__":
    main()
