from __future__ import annotations

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture
def isolated_db_singleton(tmp_path: Path) -> Iterator[Path]:
    """Ensure tests do not write to the real database.

    This fixture swaps the global DB singleton to a temp file DB.
    It yields the db path for convenience.
    """

    import cairn.db as db_mod

    db_path = tmp_path / "cairn-test.db"
    db_mod._db_instance = db_mod.Database(db_path=db_path)
    db_mod._db_instance.migrate()
    try:
        yield db_path
    finally:
        if db_mod._db_instance is not None:
            db_mod._db_instance.close()
        db_mod._db_instance = None


def run_git(repo: Path, args: list[str]) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Create a temporary git repo with minimal charter/roadmap committed."""

    repo = tmp_path / "repo"
    repo.mkdir(parents=True, exist_ok=True)

    run_git(repo, ["init"])
    run_git(repo, ["config", "user.email", "test@example.com"])
    run_git(repo, ["config", "user.name", "Cairn Test"])

    (repo / "docs").mkdir(parents=True, exist_ok=True)
    (repo / "docs" / "tech-roadmap.md").write_text(
        """# Roadmap\n\nMention: src/cairn/example.py\n""",
        encoding="utf-8",
    )
    (repo / "charter.md").write_text(
        """# Charter\n\nMention: src/cairn/example.py\n""",
        encoding="utf-8",
    )
    (repo / "src" / "cairn").mkdir(parents=True, exist_ok=True)
    (repo / "src" / "cairn" / "example.py").write_text(
        """def hello() -> str:\n    return \"hello\"\n""",
        encoding="utf-8",
    )

    run_git(repo, ["add", "."])
    run_git(repo, ["commit", "-m", "initial"])
    return repo


@pytest.fixture
def configured_repo(
    temp_git_repo: Path,
    isolated_db_singleton: Path,
) -> Path:
    """Configure the temp git repo as the active repo for tools."""

    from cairn.db import get_db

    db = get_db()
    db.set_state(key="repo_path", value=str(temp_git_repo))
    return temp_git_repo


# =============================================================================
# E2E Test Fixtures - Real LLM Integration
# =============================================================================


def _check_ollama_available() -> tuple[bool, str | None, str | None]:
    """Check if Ollama is running and has a model available.

    Returns:
        Tuple of (is_available, base_url, model_name)
    """
    import requests

    # Try common Ollama URLs
    urls_to_try = [
        "http://localhost:11434",
        "http://127.0.0.1:11434",
    ]

    for base_url in urls_to_try:
        try:
            # Check if Ollama is running
            response = requests.get(f"{base_url}/api/tags", timeout=2)
            if response.status_code == 200:
                data = response.json()
                models = data.get("models", [])
                if models:
                    # Prefer smaller/faster models for tests
                    preferred_order = [
                        "llama3.2:1b", "llama3.2:3b", "llama3.2",
                        "qwen2.5:0.5b", "qwen2.5:1.5b", "qwen2.5:3b",
                        "phi3:mini", "gemma2:2b",
                        "mistral",  # 7B - fallback if tiny models not installed
                        "llama3.1:8b",  # 8B - another reasonable fallback
                    ]
                    for preferred in preferred_order:
                        for model in models:
                            if preferred in model.get("name", ""):
                                return True, base_url, model["name"]
                    # Fall back to first available model
                    return True, base_url, models[0]["name"]
        except Exception:
            continue

    return False, None, None


# Cache the Ollama check result
_ollama_check_cache: tuple[bool, str | None, str | None] | None = None


def get_ollama_for_tests() -> tuple[bool, str | None, str | None]:
    """Get cached Ollama availability check."""
    global _ollama_check_cache
    if _ollama_check_cache is None:
        _ollama_check_cache = _check_ollama_available()
    return _ollama_check_cache


# Markers for E2E tests
requires_ollama = pytest.mark.skipif(
    not get_ollama_for_tests()[0],
    reason="Ollama not available - install and run Ollama with a model for E2E tests"
)


@pytest.fixture
def real_llm() -> Iterator:
    """Get real Ollama LLM provider for E2E testing.

    Skips test if Ollama is not available.
    """
    available, base_url, model = get_ollama_for_tests()
    if not available:
        pytest.skip("Ollama not available for E2E tests")

    from cairn.ollama import OllamaClient
    client = OllamaClient(url=base_url, model=model)

    yield client


# e2e_executor_real_llm and session_log_dir fixtures removed.
# They imported reos.code_mode (RIVA), which no longer lives in Talking Rock.
# See /home/kellogg/dev/RIVA/tests/ for the moved tests that used them.
