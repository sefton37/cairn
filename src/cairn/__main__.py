"""Cairn — local-first attention minder.

Talking Rock brings local-first AI to your personal life:
- Natural language conversation with CAIRN
- CAIRN: Your attention-aware knowledge companion
- Local-first, Ollama-powered, no cloud dependencies

Usage:
    cairn               Start the RPC server (default)
    cairn --help        Show this help message
    cairn-shell         Natural language terminal integration

Environment Variables:
    TALKINGROCK_HOST            Server host (default: 127.0.0.1)
    TALKINGROCK_PORT            Server port (default: 8010)
    TALKINGROCK_OLLAMA_URL      Ollama API URL (default: http://127.0.0.1:11434)
    TALKINGROCK_OLLAMA_MODEL    Default Ollama model to use
    TALKINGROCK_LOG_LEVEL       Logging level (default: INFO)
"""

from __future__ import annotations

import argparse
import sys

import uvicorn

from .logging_setup import configure_logging
from .settings import settings


def main() -> None:
    """Main entry point for Cairn server."""
    parser = argparse.ArgumentParser(
        prog="cairn",
        description="Cairn — local-first attention minder",
        epilog="""
Examples:
  cairn                    Start the RPC server on default port
  cairn --port 8020        Start on custom port
  cairn --no-reload        Disable auto-reload (production mode)

For natural language shell integration, use cairn-shell:
  cairn-shell "what files are here"
  cairn-shell --help
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--host",
        default=settings.host,
        help=f"Server host (default: {settings.host})",
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=settings.port,
        help=f"Server port (default: {settings.port})",
    )
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload (for production)",
    )
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default=settings.log_level,
        help=f"Logging level (default: {settings.log_level})",
    )
    parser.add_argument(
        "--version", "-V",
        action="version",
        version="%(prog)s 0.0.0a0 (Talking Rock)",
    )

    args = parser.parse_args()

    configure_logging()

    print(f"Starting Cairn server on {args.host}:{args.port}")
    print("Press Ctrl+C to stop\n")

    uvicorn.run(
        "cairn.app:app",
        host=args.host,
        port=args.port,
        reload=not args.no_reload,
        log_level=args.log_level.lower(),
    )


if __name__ == "__main__":
    main()
