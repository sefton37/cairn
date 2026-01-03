"""ReOS Shell CLI - Natural language terminal integration.

This module provides a CLI interface for handling natural language prompts
directly from the terminal, enabling shell integration via command_not_found_handle.

Usage:
    python -m reos.shell_cli "what files are in my home directory"
    python -m reos.shell_cli --execute "list all python files"
"""

from __future__ import annotations

import argparse
import sys
from typing import NoReturn

from .agent import ChatAgent
from .db import get_db
from .logging_setup import configure_logging


def colorize(text: str, color: str) -> str:
    """Apply ANSI color codes if stdout is a TTY."""
    if not sys.stdout.isatty():
        return text

    colors = {
        "cyan": "\033[36m",
        "green": "\033[32m",
        "yellow": "\033[33m",
        "red": "\033[31m",
        "bold": "\033[1m",
        "dim": "\033[2m",
        "reset": "\033[0m",
    }
    return f"{colors.get(color, '')}{text}{colors['reset']}"


def print_header() -> None:
    """Print a minimal ReOS header."""
    header = colorize("ReOS", "cyan") + colorize(" (natural language mode)", "dim")
    print(header, file=sys.stderr)


def print_thinking() -> None:
    """Show thinking indicator."""
    print(colorize("  Thinking...", "dim"), end="\r", file=sys.stderr)


def clear_thinking() -> None:
    """Clear the thinking indicator."""
    print(" " * 20, end="\r", file=sys.stderr)


def handle_prompt(prompt: str, *, verbose: bool = False) -> str:
    """Process a natural language prompt through ReOS.

    Args:
        prompt: The natural language query from the user.
        verbose: If True, show detailed progress.

    Returns:
        The agent's response text.
    """
    db = get_db()
    agent = ChatAgent(db=db)

    if verbose:
        print_thinking()

    try:
        response = agent.respond(prompt)
    finally:
        if verbose:
            clear_thinking()

    return response


def main() -> NoReturn:
    """Main entry point for shell CLI."""
    configure_logging()

    parser = argparse.ArgumentParser(
        prog="reos-shell",
        description="ReOS natural language terminal integration",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Natural language prompt to process",
    )
    parser.add_argument(
        "--quiet", "-q",
        action="store_true",
        help="Suppress header and progress indicators",
    )
    parser.add_argument(
        "--command-not-found",
        action="store_true",
        help="Mode for command_not_found_handle integration (shows prompt confirmation)",
    )

    args = parser.parse_args()

    # Join prompt words
    prompt = " ".join(args.prompt).strip()

    if not prompt:
        # Read from stdin if no prompt provided
        if not sys.stdin.isatty():
            prompt = sys.stdin.read().strip()

        if not prompt:
            print("Usage: reos-shell 'your natural language prompt'", file=sys.stderr)
            sys.exit(1)

    # In command-not-found mode, confirm before processing
    if args.command_not_found:
        print(colorize("ReOS:", "cyan"), f"'{prompt}' is not a command.", file=sys.stderr)
        print(colorize("      ", "cyan"), "Treat as natural language? [Y/n] ", end="", file=sys.stderr)

        try:
            response = input().strip().lower()
            if response and response not in ("y", "yes"):
                sys.exit(127)  # Standard exit code for command not found
        except (EOFError, KeyboardInterrupt):
            sys.exit(127)

    if not args.quiet:
        print_header()

    try:
        response = handle_prompt(prompt, verbose=not args.quiet)

        if not args.quiet:
            print()  # Blank line before response

        print(response)
        sys.exit(0)

    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(colorize(f"Error: {e}", "red"), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
