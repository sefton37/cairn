from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "y", "on"}:
        return True
    if val in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _env(name: str, default: str) -> str:
    return os.environ.get(name) or default


@dataclass(frozen=True)
class Settings:
    """Static settings for the local service.

    Keep defaults local and auditable; no network endpoints beyond localhost.
    All env vars use the TALKINGROCK_ prefix.
    """

    root_dir: Path = Path(__file__).resolve().parents[2]
    data_dir: Path = Path(_env("TALKINGROCK_DATA_DIR", str(Path.home() / ".talkingrock")))
    events_path: Path = data_dir / "events.jsonl"
    audit_path: Path = data_dir / "audit.log"
    log_path: Path = data_dir / "cairn.log"
    log_level: str = _env("TALKINGROCK_LOG_LEVEL", "INFO")
    log_max_bytes: int = int(_env("TALKINGROCK_LOG_MAX_BYTES", "1000000"))
    log_backup_count: int = int(_env("TALKINGROCK_LOG_BACKUP_COUNT", "3"))
    host: str = _env("TALKINGROCK_HOST", "127.0.0.1")
    port: int = int(_env("TALKINGROCK_PORT", "8010"))
    ollama_url: str = _env("TALKINGROCK_OLLAMA_URL", "http://127.0.0.1:11434")

    def __post_init__(self) -> None:
        """Validate settings that must be constrained for zero-trust."""
        from urllib.parse import urlparse
        parsed = urlparse(self.ollama_url)
        if parsed.hostname not in ("localhost", "127.0.0.1", "::1", None):
            raise ValueError(
                f"TALKINGROCK_OLLAMA_URL must point to localhost (got {parsed.hostname!r}). "
                "Cairn is local-only — remote LLM endpoints are not allowed."
            )
    ollama_model: str | None = os.environ.get("TALKINGROCK_OLLAMA_MODEL")

    # =========================================================================
    # Git Integration (OPTIONAL - M5 Roadmap Feature)
    # =========================================================================
    git_integration_enabled: bool = _env_bool("TALKINGROCK_GIT_INTEGRATION_ENABLED", False)
    auto_review_commits: bool = _env_bool("TALKINGROCK_AUTO_REVIEW_COMMITS", False)
    auto_review_commits_include_diff: bool = _env_bool(
        "TALKINGROCK_AUTO_REVIEW_COMMITS_INCLUDE_DIFF", False
    )
    auto_review_commits_cooldown_seconds: int = int(
        _env("TALKINGROCK_AUTO_REVIEW_COMMITS_COOLDOWN_SECONDS", "5")
    )
    repo_path: Path | None = (
        Path(os.environ["TALKINGROCK_REPO_PATH"])
        if os.environ.get("TALKINGROCK_REPO_PATH")
        else None
    )

    # LLM context budgeting
    llm_context_tokens: int = int(_env("TALKINGROCK_LLM_CONTEXT_TOKENS", "8192"))
    review_trigger_ratio: float = float(_env("TALKINGROCK_REVIEW_TRIGGER_RATIO", "0.8"))
    review_trigger_cooldown_minutes: int = int(
        _env("TALKINGROCK_REVIEW_TRIGGER_COOLDOWN_MINUTES", "15")
    )

    # Estimation knobs (heuristics)
    review_overhead_tokens: int = int(_env("TALKINGROCK_REVIEW_OVERHEAD_TOKENS", "800"))
    tokens_per_changed_line: int = int(_env("TALKINGROCK_TOKENS_PER_CHANGED_LINE", "6"))
    tokens_per_changed_file: int = int(_env("TALKINGROCK_TOKENS_PER_CHANGED_FILE", "40"))


settings = Settings()

# Ensure data directories exist at import time (local-only side effect).
# Use 0o700 to prevent group/other access to user data.
settings.data_dir.mkdir(parents=True, exist_ok=True)
settings.data_dir.chmod(0o700)
