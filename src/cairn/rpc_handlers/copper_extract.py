"""System prompt extractor for Copper modelfile creation.

Reads from talkingrock.db to assemble a system prompt containing:
1. Identity context (who Cairn is)
2. Ecosystem summary (from README)
3. Your Story memories (approved, highest signal)
4. Active acts/scenes
"""
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Word budget for system prompt sections
_MAX_TOTAL_WORDS = 3500
_ECOSYSTEM_BUDGET = 500
_MEMORY_BUDGET = 2000
_ACTS_BUDGET = 500


def _truncate_to_words(text: str, max_words: int) -> tuple[str, bool]:
    """Truncate text to max_words. Returns (text, was_truncated)."""
    words = text.split()
    if len(words) <= max_words:
        return text, False
    return " ".join(words[:max_words]) + "\n[...truncated]", True


def _read_ecosystem_context() -> str:
    """Read key docs from Cairn to summarize the ecosystem."""
    cairn_root = Path(os.environ.get("CAIRN_ROOT", os.path.expanduser("~/dev/Cairn")))
    readme = cairn_root / "README.md"

    lines = []
    if readme.is_file():
        try:
            content = readme.read_text(encoding="utf-8")
            # Take first 150 lines for overview
            lines = content.splitlines()[:150]
        except Exception as exc:
            logger.warning("Failed to read Cairn README: %s", exc)

    if not lines:
        return "Cairn is a local-first personal attention minder. Part of the Talking Rock ecosystem."

    return "\n".join(lines)


def extract_system_prompt() -> dict[str, Any]:
    """Extract and assemble a system prompt from Talking Rock data.

    Reads directly from talkingrock.db (no HTTP call to Copper).
    Uses db_crypto.connect so encrypted databases are handled transparently.

    Returns:
        {
            "system_prompt": str,
            "word_count": int,
            "memory_count": int,
            "sources": list[str],
            "truncated": bool,
        }
    """
    sources: list[str] = []
    any_truncated = False
    sections: list[str] = []

    # --- Identity ---
    identity = (
        "Your name is Cairn. You are a personal attention minder.\n"
        "You run entirely locally with no cloud dependencies.\n"
        "You help your user focus on what they value without automating them.\n"
        "You verify intent before acting. You request permission before executing.\n"
        "All your learning is available for the user to audit and edit."
    )
    sections.append(f"[IDENTITY]\n{identity}")
    sources.append("Identity context")

    # --- Ecosystem ---
    eco_raw = _read_ecosystem_context()
    eco_text, eco_trunc = _truncate_to_words(eco_raw, _ECOSYSTEM_BUDGET)
    any_truncated = any_truncated or eco_trunc
    sections.append(f"[ECOSYSTEM CONTEXT]\n{eco_text}")
    sources.append("Cairn README")

    # --- Memories and Acts from talkingrock.db ---
    memory_count = 0
    try:
        from .. import db_crypto
        from ..settings import settings

        db_path = settings.data_dir / "talkingrock.db"

        if db_path.is_file():
            conn = db_crypto.connect(
                str(db_path),
                timeout=5.0,
                check_same_thread=False,
            )
            conn.row_factory = __import__("sqlite3").Row
            conn.execute("PRAGMA journal_mode=WAL")

            # Get approved/pending memories ordered by signal count (highest first)
            try:
                rows = conn.execute(
                    """SELECT narrative FROM memories
                       WHERE status IN ('approved', 'pending_review')
                       ORDER BY signal_count DESC, created_at DESC
                       LIMIT 50"""
                ).fetchall()

                if rows:
                    memory_texts = [r["narrative"] for r in rows if r["narrative"]]
                    memory_count = len(memory_texts)
                    memory_block = "\n\n".join(memory_texts)
                    memory_block, mem_trunc = _truncate_to_words(memory_block, _MEMORY_BUDGET)
                    any_truncated = any_truncated or mem_trunc
                    sections.append(f"[YOUR STORY]\n{memory_block}")
                    sources.append(f"{memory_count} memories")
            except Exception as exc:
                logger.warning("Failed to read memories: %s", exc)

            # Get active acts (active = 1, exclude system acts)
            try:
                act_rows = conn.execute(
                    """SELECT act_id, title FROM acts
                       WHERE active = 1 AND (system_role IS NULL OR system_role = '')
                       ORDER BY title ASC"""
                ).fetchall()

                if act_rows:
                    act_lines = [f"- {r['title']} (id: {r['act_id']})" for r in act_rows]
                    acts_block = "\n".join(act_lines)
                    acts_block, acts_trunc = _truncate_to_words(acts_block, _ACTS_BUDGET)
                    any_truncated = any_truncated or acts_trunc
                    sections.append(f"[ACTIVE ACTS]\n{acts_block}")
                    sources.append(f"{len(act_rows)} active acts")
            except Exception as exc:
                logger.warning("Failed to read acts: %s", exc)

            conn.close()
        else:
            logger.info("talkingrock.db not found at %s", db_path)
            sources.append("No talkingrock.db found")
    except Exception as exc:
        logger.warning("Failed to access talkingrock.db: %s", exc)
        sources.append(f"DB access error: {exc}")

    # Assemble
    system_prompt = "\n\n".join(sections)
    word_count = len(system_prompt.split())

    # Final truncation if over budget
    if word_count > _MAX_TOTAL_WORDS:
        system_prompt, _ = _truncate_to_words(system_prompt, _MAX_TOTAL_WORDS)
        any_truncated = True
        word_count = _MAX_TOTAL_WORDS

    return {
        "system_prompt": system_prompt,
        "word_count": word_count,
        "memory_count": memory_count,
        "sources": sources,
        "truncated": any_truncated,
    }
