from __future__ import annotations

import difflib
import json
import logging
import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .settings import settings

logger = logging.getLogger(__name__)


def _get_crypto():
    """Return the active CryptoStorage, or None if not authenticated."""
    from cairn.crypto_storage import get_active_crypto

    return get_active_crypto()


def _write_text(path: Path, text: str) -> None:
    """Write text data, encrypting if CryptoStorage is active.

    When encryption is active and text is empty, writes an empty plaintext file
    instead of encrypting — avoids producing opaque binary that becomes mojibake
    if read without a crypto session.
    """
    crypto = _get_crypto()
    if crypto and text:
        path.write_bytes(crypto.encrypt(text.encode("utf-8")))
        os.chmod(path, 0o600)
    else:
        path.write_text(text, encoding="utf-8")


def _read_text(path: Path) -> str:
    """Read text data, decrypting if CryptoStorage is active.

    If decryption fails (e.g. crypto inactive but file was encrypted),
    returns empty string rather than raw binary as mojibake.
    """
    raw = path.read_bytes()

    # If crypto is active, try decryption first
    crypto = _get_crypto()
    if crypto:
        try:
            return crypto.decrypt(raw).decode("utf-8")
        except Exception:
            pass  # Fall through to plaintext attempt

    # Validate that the file looks like valid UTF-8 text, not encrypted binary.
    # AES-GCM output (nonce + ciphertext + tag) is not valid UTF-8 in most cases,
    # but errors="replace" would silently produce mojibake. Detect and reject.
    try:
        text = raw.decode("utf-8")  # strict — raises on invalid bytes
        return text
    except UnicodeDecodeError:
        import logging

        logging.getLogger(__name__).warning(
            "File %s contains non-UTF-8 data (%d bytes) — likely encrypted "
            "without an active crypto session. Returning empty string.",
            path,
            len(raw),
        )
        return ""


# =============================================================================
# Constants for "Your Story" Act and Stage Direction
# =============================================================================

YOUR_STORY_ACT_ID = "your-story"
STAGE_DIRECTION_SCENE_ID_PREFIX = "stage-direction-"


def _get_stage_direction_scene_id(act_id: str) -> str:
    """Get the Stage Direction scene ID for an Act."""
    return f"{STAGE_DIRECTION_SCENE_ID_PREFIX}{act_id[:12]}"


class SceneStage(Enum):
    """The stage/state of a Scene in The Play.

    Scenes progress through these stages:
    - PLANNING: No date set, still being organized
    - IN_PROGRESS: Has a date, actively working on it
    - AWAITING_DATA: Waiting for external input/data
    - COMPLETE: Done
    """

    PLANNING = "planning"
    IN_PROGRESS = "in_progress"
    AWAITING_DATA = "awaiting_data"
    COMPLETE = "complete"


# Color palette for Acts - visually distinct colors that work well in UI
# Each color is a tuple of (background_rgba, text_hex) for light theme compatibility
ACT_COLOR_PALETTE: list[str] = [
    "#8b5cf6",  # Purple (violet-500)
    "#3b82f6",  # Blue (blue-500)
    "#10b981",  # Green (emerald-500)
    "#f59e0b",  # Amber (amber-500)
    "#ef4444",  # Red (red-500)
    "#ec4899",  # Pink (pink-500)
    "#06b6d4",  # Cyan (cyan-500)
    "#84cc16",  # Lime (lime-500)
    "#f97316",  # Orange (orange-500)
    "#6366f1",  # Indigo (indigo-500)
    "#14b8a6",  # Teal (teal-500)
    "#a855f7",  # Fuchsia (purple-500)
]


@dataclass(frozen=True)
class Act:
    """An Act in The Play - a major phase or project.

    When repo_path is set, this Act is in "Code Mode" - ReOS will
    automatically detect code-related requests and provide agentic
    coding capabilities sandboxed to the assigned repository.
    """

    act_id: str
    title: str
    active: bool = False
    notes: str = ""
    color: str | None = None  # Hex color for UI display (e.g., "#8b5cf6")
    # Code Mode fields
    repo_path: str | None = None  # Absolute path to git repo
    artifact_type: str | None = None  # "python", "typescript", "rust", etc.
    code_config: dict[str, Any] | None = None  # Per-Act code configuration


@dataclass(frozen=True)
class Scene:
    """A Scene in The Play - an atomic task or event.

    Scenes can be linked to calendar events. For recurring events,
    ONE Scene represents the entire series (not expanded occurrences).

    Calendar integration fields:
    - calendar_event_id: Inbound sync - ID of the Thunderbird event this Scene reflects
    - thunderbird_event_id: Outbound sync - ID of the Thunderbird event created for this Scene

    Auto-complete behavior:
    - By default, non-recurring scenes auto-complete when their time passes
    - If disable_auto_complete=True, overdue scenes go to 'need_attention' instead
    """

    scene_id: str
    act_id: str  # Parent Act ID
    title: str
    stage: str  # SceneStage value
    notes: str
    link: str | None = None
    # Calendar integration fields
    calendar_event_id: str | None = None  # Inbound sync: TB event that Scene reflects
    recurrence_rule: str | None = None  # RRULE string if recurring
    thunderbird_event_id: str | None = None  # Outbound sync: TB event created for Scene
    # Auto-complete behavior (v9)
    disable_auto_complete: bool = False  # If True, overdue -> need_attention instead of complete


@dataclass(frozen=True)
class FileAttachment:
    """A file attachment reference (stores path only, not file content)."""

    attachment_id: str
    file_path: str  # Absolute path on disk
    file_name: str  # Display name
    file_type: str  # Extension (pdf, docx, etc.)
    added_at: str  # ISO timestamp
    page_id: str | None = None  # Set when attached to a knowledgebase page


def play_root() -> Path:
    """Return the on-disk root for the theatrical model.

    Always uses the canonical data directory (~/.talkingrock/play). This is a
    single-user system — the data directory does not vary per session. The
    CryptoStorage context (if active) provides encryption/decryption for file
    contents but does NOT change the storage location.
    """
    env_dir = os.environ.get("TALKINGROCK_DATA_DIR")
    base = Path(env_dir) if env_dir else settings.data_dir
    return base / "play"


def _acts_path() -> Path:
    return play_root() / "acts.json"


def _me_path() -> Path:
    return play_root() / "me.md"


def _act_dir(act_id: str) -> Path:
    return play_root() / "acts" / act_id


def _scenes_path(act_id: str) -> Path:
    return _act_dir(act_id) / "scenes.json"


_YOUR_STORY_DEFAULT = """\
# Your Story

Welcome to **The Play** — Cairn's knowledge base and life organizer.

## How It Works

The Play is structured as a two-tier system:

**Acts** are the ongoing narratives of your life — broad themes that span months \
or years. Examples: Career, Health, Family, Learning, a specific project. \
Create them from the sidebar with *+ New Act*.

**Scenes** are concrete events or tasks within an Act. Each Scene can link to a \
calendar event from Thunderbird, giving it a date and time. Scenes progress \
through stages: *planning* > *in progress* > *awaiting data* > *complete*.

## Your Story

This page — **Your Story** — is the root of your knowledge base. It's the \
autobiographical layer: who you are, what you value, what Cairn should know \
about you to be a good partner. This is read by Cairn when generating \
briefings and contextualizing your requests.

Use it to capture:
- Your background, role, and experience
- Core values and priorities
- Context that cuts across all your Acts

## Writing & Commands

This editor supports **Markdown** formatting. Type `/` to see available \
slash commands for quick actions.

Each Act and Scene also has its own knowledge base page — select one from the \
sidebar to write notes, plans, or reference material specific to that narrative.
"""


def ensure_play_skeleton() -> None:
    root = play_root()
    root.mkdir(parents=True, exist_ok=True)
    (root / "acts").mkdir(parents=True, exist_ok=True)

    # Legacy: me.md and acts.json are no longer sources of truth
    # (SQLite is truth), but we keep the directories for filesystem backup.


def _ensure_stage_direction_scene(act_id: str) -> None:
    """Ensure an Act has a Stage Direction scene as its first scene.

    DEPRECATED: With SQLite backend, this is handled automatically in play_db.
    Kept for backward compatibility.
    """
    pass  # No-op - SQLite backend handles this automatically


def ensure_your_story_act() -> tuple[list["Act"], str]:
    """Ensure 'Your Story' Act exists.

    'Your Story' is a special default Act that always exists. All other Acts
    relate to it conceptually (life projects vs. the story of your life).

    Returns:
        Tuple of (all acts, your_story_act_id).
    """
    from . import play_db

    acts_data, your_story_id = play_db.ensure_your_story_act()
    # Ensure directory exists for KB files
    _act_dir(YOUR_STORY_ACT_ID).mkdir(parents=True, exist_ok=True)
    return [_dict_to_act(d) for d in acts_data], your_story_id


def read_me_markdown() -> str:
    ensure_play_skeleton()
    return _read_text(_me_path())


def write_me_markdown(text: str) -> None:
    """Write the me.md file (Your Story / Play level content)."""
    ensure_play_skeleton()
    _write_text(_me_path(), text)


def _dict_to_act(d: dict[str, Any]) -> Act:
    """Convert a dict to an Act dataclass."""
    return Act(
        act_id=d.get("act_id", ""),
        title=d.get("title", ""),
        active=bool(d.get("active", False)),
        notes=d.get("notes", ""),
        color=d.get("color"),
        repo_path=d.get("repo_path"),
        artifact_type=d.get("artifact_type"),
        code_config=d.get("code_config"),
    )


def _dict_to_scene(d: dict[str, Any]) -> Scene:
    """Convert a dict to a Scene dataclass (v4 structure)."""
    return Scene(
        scene_id=d.get("scene_id", ""),
        act_id=d.get("act_id", ""),
        title=d.get("title", ""),
        stage=d.get("stage", SceneStage.PLANNING.value),
        notes=d.get("notes", ""),
        link=d.get("link"),
        calendar_event_id=d.get("calendar_event_id"),
        recurrence_rule=d.get("recurrence_rule"),
        thunderbird_event_id=d.get("thunderbird_event_id"),
        disable_auto_complete=bool(d.get("disable_auto_complete", False)),
    )


def list_acts() -> tuple[list[Act], str | None]:
    """List all Acts and return the active Act ID."""
    from . import play_db

    acts_data, active_id = play_db.list_acts()
    acts = [_dict_to_act(d) for d in acts_data]
    return acts, active_id


def set_active_act_id(*, act_id: str | None) -> tuple[list[Act], str | None]:
    """Set the active act, or clear it if act_id is None."""
    from . import play_db

    acts_data, active_id = play_db.set_active_act(act_id)
    acts = [_dict_to_act(d) for d in acts_data]
    return acts, active_id


def list_scenes(*, act_id: str) -> list[Scene]:
    """List all Scenes for an Act."""
    from . import play_db

    scenes_data = play_db.list_scenes(act_id)
    return [_dict_to_scene(d) for d in scenes_data]


def find_scene_location(scene_id: str) -> dict[str, str | None] | None:
    """Find the Act containing a Scene.

    This is the CANONICAL source for scene location - never cache this elsewhere.

    Args:
        scene_id: The Scene ID to find.

    Returns:
        Dict with act_id, act_title, scene_id, or None if not found.
    """
    from . import play_db

    return play_db.find_scene_location(scene_id)


def _validate_id(*, name: str, value: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string")
    if any(part in value for part in ("/", "\\", "..")):
        raise ValueError(f"invalid {name}")


def _pick_unused_color(existing_acts: list[Act]) -> str:
    """Pick a color from the palette that's not already in use.

    If all colors are used, returns the first color in the palette.
    Prefers colors that are most different from existing ones.
    """
    used_colors = {a.color for a in existing_acts if a.color}

    # Find unused colors
    unused = [c for c in ACT_COLOR_PALETTE if c not in used_colors]

    if unused:
        # Return the first unused color (maintains consistent assignment order)
        return unused[0]

    # All colors used - just return the first one
    return ACT_COLOR_PALETTE[0]


def create_act(*, title: str, notes: str = "", color: str | None = None) -> tuple[list[Act], str]:
    """Create a new Act.

    - Generates a stable act_id.
    - If no act is active yet, the new act becomes active.
    - Auto-assigns a color from the palette if not specified.
    """
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title is required")
    if not isinstance(notes, str):
        raise ValueError("notes must be a string")

    # Auto-assign color if not provided
    if color is None:
        existing_acts, _ = list_acts()
        color = _pick_unused_color(existing_acts)

    from . import play_db

    acts_data, act_id = play_db.create_act(title=title.strip(), notes=notes, color=color)
    acts = [_dict_to_act(d) for d in acts_data]
    # Create directory for KB files
    _act_dir(act_id).mkdir(parents=True, exist_ok=True)
    return acts, act_id


def update_act(
    *,
    act_id: str,
    title: str | None = None,
    notes: str | None = None,
    color: str | None = None,
) -> tuple[list[Act], str | None]:
    """Update an Act's user-editable fields including color."""
    _validate_id(name="act_id", value=act_id)

    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ValueError("title must be a non-empty string")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be a string")
    if color is not None and not isinstance(color, str):
        raise ValueError("color must be a string")

    from . import play_db

    acts_data, active_id = play_db.update_act(act_id=act_id, title=title, notes=notes, color=color)
    acts = [_dict_to_act(d) for d in acts_data]
    return acts, active_id


def delete_act(*, act_id: str) -> tuple[list[Act], str | None]:
    """Delete an Act and all its Scenes.

    IMPORTANT: The "Your Story" act (act_id="your-story") cannot be deleted.

    Args:
        act_id: The Act ID to delete.

    Returns:
        Tuple of (remaining acts list, active_act_id or None).

    Raises:
        ValueError: If act_id is "your-story" or not found.
    """
    _validate_id(name="act_id", value=act_id)

    # Protect "Your Story" act from deletion
    if act_id == YOUR_STORY_ACT_ID:
        raise ValueError("Cannot delete 'Your Story' act - it is a protected system act")

    from . import play_db
    import shutil

    # Delete from SQLite (cascades to scenes/beats)
    acts_data, active_id = play_db.delete_act(act_id)
    # Also delete the act's directory (KB files)
    act_dir = _act_dir(act_id)
    if act_dir.exists():
        shutil.rmtree(act_dir)
    return [_dict_to_act(d) for d in acts_data], active_id


def assign_repo_to_act(
    *,
    act_id: str,
    repo_path: str | None,
    artifact_type: str | None = None,
    code_config: dict[str, Any] | None = None,
) -> tuple[list[Act], str | None]:
    """Assign a repository to an Act, enabling Code Mode.

    Args:
        act_id: The Act to modify
        repo_path: Absolute path to git repository, or None to disable Code Mode
        artifact_type: Language/type hint (e.g., "python", "typescript")
        code_config: Per-Act code configuration

    Returns:
        Updated acts list and active_id
    """
    _validate_id(name="act_id", value=act_id)

    # Validate repo_path is a real git repo if provided
    if repo_path is not None:
        repo = Path(repo_path).resolve()
        if not repo.is_dir():
            raise ValueError(f"repo_path does not exist: {repo_path}")
        if not (repo / ".git").is_dir():
            raise ValueError(f"repo_path is not a git repository: {repo_path}")
        repo_path = str(repo)  # Normalize to absolute path

    from . import play_db

    acts_data, active_id = play_db.assign_repo_to_act(
        act_id=act_id,
        repo_path=repo_path,
        artifact_type=artifact_type,
        code_config=code_config,
    )
    return [_dict_to_act(d) for d in acts_data], active_id


def create_scene(
    *,
    act_id: str,
    title: str,
    stage: str = "",
    notes: str = "",
    link: str | None = None,
    calendar_event_id: str | None = None,
    recurrence_rule: str | None = None,
    thunderbird_event_id: str | None = None,
    disable_auto_complete: bool = False,
) -> tuple[list[Scene], str]:
    """Create a Scene under an Act.

    Args:
        act_id: The Act to add the Scene to.
        title: Scene title.
        stage: SceneStage value (planning, in_progress, awaiting_data, complete).
        notes: Optional notes.
        link: Optional external link.
        calendar_event_id: Optional calendar event ID this Scene is linked to (inbound sync).
        recurrence_rule: Optional RRULE string for recurring events.
        thunderbird_event_id: Optional Thunderbird event ID created for this Scene (outbound sync).
        disable_auto_complete: If True, overdue scenes go to need_attention instead of auto-completing.

    Returns:
        Tuple of (list of scenes in act, new scene_id).
    """
    _validate_id(name="act_id", value=act_id)
    if not isinstance(title, str) or not title.strip():
        raise ValueError("title is required")
    if not isinstance(stage, str):
        raise ValueError("stage must be a string")
    if not isinstance(notes, str):
        raise ValueError("notes must be a string")
    if link is not None and not isinstance(link, str):
        raise ValueError("link must be a string or null")
    if calendar_event_id is not None and not isinstance(calendar_event_id, str):
        raise ValueError("calendar_event_id must be a string or null")
    if recurrence_rule is not None and not isinstance(recurrence_rule, str):
        raise ValueError("recurrence_rule must be a string or null")
    if thunderbird_event_id is not None and not isinstance(thunderbird_event_id, str):
        raise ValueError("thunderbird_event_id must be a string or null")

    # Default stage to PLANNING if not specified
    if not stage:
        stage = SceneStage.PLANNING.value

    from . import play_db

    scenes_data, scene_id = play_db.create_scene(
        act_id=act_id,
        title=title.strip(),
        stage=stage,
        notes=notes,
        link=link,
        calendar_event_id=calendar_event_id,
        recurrence_rule=recurrence_rule,
        thunderbird_event_id=thunderbird_event_id,
        disable_auto_complete=disable_auto_complete,
    )
    return [_dict_to_scene(d) for d in scenes_data], scene_id


def update_scene(
    *,
    act_id: str,
    scene_id: str,
    title: str | None = None,
    stage: str | None = None,
    notes: str | None = None,
    link: str | None = None,
    calendar_event_id: str | None = None,
    recurrence_rule: str | None = None,
    thunderbird_event_id: str | None = None,
    disable_auto_complete: bool | None = None,
) -> list[Scene]:
    """Update a Scene's fields.

    Args:
        act_id: The Act containing the Scene.
        scene_id: The Scene to update.
        title: New title (optional).
        stage: New SceneStage value (optional).
        notes: New notes (optional).
        link: New external link (optional).
        calendar_event_id: New calendar event ID (optional).
        recurrence_rule: New recurrence rule (optional).
        thunderbird_event_id: New Thunderbird event ID (optional).
        disable_auto_complete: New auto-complete setting (optional).
    """
    _validate_id(name="act_id", value=act_id)
    _validate_id(name="scene_id", value=scene_id)
    if title is not None and (not isinstance(title, str) or not title.strip()):
        raise ValueError("title must be a non-empty string")
    if stage is not None and not isinstance(stage, str):
        raise ValueError("stage must be a string")
    if notes is not None and not isinstance(notes, str):
        raise ValueError("notes must be a string")
    if link is not None and not isinstance(link, str):
        raise ValueError("link must be a string or null")

    from . import play_db

    scenes_data = play_db.update_scene(
        act_id=act_id,
        scene_id=scene_id,
        title=title.strip() if title else None,
        stage=stage,
        notes=notes,
        link=link,
        calendar_event_id=calendar_event_id,
        recurrence_rule=recurrence_rule,
        thunderbird_event_id=thunderbird_event_id,
        disable_auto_complete=disable_auto_complete,
    )
    return [_dict_to_scene(d) for d in scenes_data]


def delete_scene(*, act_id: str, scene_id: str) -> list[Scene]:
    """Delete a Scene.

    IMPORTANT: Stage Direction scenes cannot be deleted.

    Args:
        act_id: The parent Act ID.
        scene_id: The Scene ID to delete.

    Returns:
        List of remaining Scene objects in the act.

    Raises:
        ValueError: If scene is Stage Direction or not found.
    """
    _validate_id(name="act_id", value=act_id)
    _validate_id(name="scene_id", value=scene_id)

    # Protect Stage Direction scenes from deletion
    stage_direction_id = _get_stage_direction_scene_id(act_id)
    if scene_id == stage_direction_id:
        raise ValueError("Cannot delete 'Stage Direction' scene - it is a protected system scene")

    from . import play_db

    scenes_data = play_db.delete_scene(act_id, scene_id)
    return [_dict_to_scene(d) for d in scenes_data]


def move_scene(
    *,
    scene_id: str,
    source_act_id: str,
    target_act_id: str,
) -> dict[str, Any]:
    """Move a Scene to a different Act.

    Args:
        scene_id: The Scene to move.
        source_act_id: The source Act.
        target_act_id: The target Act.

    Returns:
        Dict with moved scene_id and target_act_id.

    Raises:
        ValueError: If scene or acts not found.
    """
    _validate_id(name="scene_id", value=scene_id)
    _validate_id(name="source_act_id", value=source_act_id)
    _validate_id(name="target_act_id", value=target_act_id)

    from . import play_db

    return play_db.move_scene(
        scene_id=scene_id,
        source_act_id=source_act_id,
        target_act_id=target_act_id,
    )


def _kb_root_for(*, act_id: str, scene_id: str | None = None) -> Path:
    _validate_id(name="act_id", value=act_id)
    base = play_root() / "kb" / "acts" / act_id
    if scene_id is None:
        return base
    _validate_id(name="scene_id", value=scene_id)
    return base / "scenes" / scene_id


def _resolve_kb_file(*, kb_root: Path, rel_path: str) -> Path:
    if not isinstance(rel_path, str) or not rel_path.strip():
        raise ValueError("path is required")
    p = Path(rel_path)
    if p.is_absolute():
        raise ValueError("path must be relative")
    if any(part in {"..", ""} for part in p.parts):
        raise ValueError("path escapes kb root")
    candidate = (kb_root / p).resolve()
    kb_root_resolved = kb_root.resolve()
    if candidate != kb_root_resolved and kb_root_resolved not in candidate.parents:
        raise ValueError("path escapes kb root")
    return candidate


def kb_list_files(*, act_id: str, scene_id: str | None = None) -> list[str]:
    """List markdown/text files under an item's KB root.

    The default KB file is `kb.md` (created on demand).
    """

    ensure_play_skeleton()
    kb_root = _kb_root_for(act_id=act_id, scene_id=scene_id)
    kb_root.mkdir(parents=True, exist_ok=True)
    default = kb_root / "kb.md"
    if not default.exists():
        _write_text(default, "# KB\n\n")

    files: list[str] = []
    for path in kb_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in {".md", ".txt"}:
            continue
        files.append(path.relative_to(kb_root).as_posix())

    return sorted(set(files))


def _sha256_text(text: str) -> str:
    import hashlib

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _get_or_create_kb_page(act_id: str, scene_id: str | None = None) -> str:
    """Get or create the root KB page for an act/scene in SQLite.

    Returns the page_id.
    """
    from . import play_db

    title = "KB" if scene_id else "Knowledge Base"
    pages = play_db.list_pages(act_id=act_id, parent_page_id=None)
    # Find existing KB page (first root page)
    for page in pages:
        if page.get("system_page_role") != "memories":
            return page["page_id"]

    # Create one
    page = play_db.create_page(act_id=act_id, title=title)
    return page["page_id"]


def _kb_read_sqlite(act_id: str, scene_id: str | None = None) -> str:
    """Read KB content from SQLite blocks, rendered as markdown."""
    from .play.blocks_db import get_page_blocks
    from .play.markdown_renderer import render_markdown

    try:
        page_id = _get_or_create_kb_page(act_id, scene_id)
        blocks = get_page_blocks(page_id, recursive=True)
        if not blocks:
            return ""
        return render_markdown(blocks)
    except Exception:
        return ""


def _kb_write_sqlite(act_id: str, text: str, scene_id: str | None = None) -> None:
    """Write KB content to SQLite blocks by parsing markdown."""
    from .play.blocks_db import create_block, delete_block, get_page_blocks
    from .play.markdown_parser import parse_markdown

    page_id = _get_or_create_kb_page(act_id, scene_id)

    # Delete existing blocks for this page
    existing = get_page_blocks(page_id, recursive=False)
    for block in existing:
        delete_block(block.id, recursive=True)

    # Parse markdown into block data and create blocks
    if text.strip():
        block_datas = parse_markdown(text, act_id=act_id, page_id=page_id)
        for bd in block_datas:
            create_block(
                type=bd["type"],
                act_id=act_id,
                page_id=page_id,
                position=bd.get("position", 0),
                rich_text=bd.get("rich_text"),
                properties=bd.get("properties"),
            )


def kb_read(*, act_id: str, scene_id: str | None = None, path: str = "kb.md") -> str:
    """Read KB content. SQLite is the source of truth; falls back to filesystem for migration."""
    # Try SQLite first
    content = _kb_read_sqlite(act_id, scene_id)
    if content:
        return content

    # Fallback: read from filesystem and migrate to SQLite
    ensure_play_skeleton()
    kb_root = _kb_root_for(act_id=act_id, scene_id=scene_id)
    kb_root.mkdir(parents=True, exist_ok=True)
    target = _resolve_kb_file(kb_root=kb_root, rel_path=path)

    if not target.exists():
        if Path(path).as_posix() != "kb.md":
            raise FileNotFoundError(path)
        if act_id == YOUR_STORY_ACT_ID and scene_id is None:
            return _YOUR_STORY_DEFAULT
        return "# KB\n\n"

    content = _read_text(target)

    # Migrate filesystem content to SQLite for future reads
    if content.strip():
        try:
            _kb_write_sqlite(act_id, content, scene_id)
            logger.info("Migrated KB %s to SQLite (%d chars)", act_id, len(content))
        except Exception as exc:
            logger.warning("KB migration failed for %s: %s", act_id, exc)

    return content


def kb_write_preview(
    *,
    act_id: str,
    scene_id: str | None = None,
    path: str,
    text: str,
    _debug_source: str | None = None,
) -> dict[str, Any]:
    """Preview a KB write. Returns current SHA and diff for conflict detection."""
    try:
        current = kb_read(act_id=act_id, scene_id=scene_id, path=path)
    except FileNotFoundError:
        current = ""
    current_sha = _sha256_text(current)
    new_sha = _sha256_text(text)

    diff_lines = difflib.unified_diff(
        current.splitlines(keepends=True),
        text.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        lineterm="",
    )
    diff = "\n".join(diff_lines)

    return {
        "exists": bool(current),
        "sha256_current": current_sha,
        "sha256_new": new_sha,
        "diff": diff,
    }


def kb_write_apply(
    *,
    act_id: str,
    scene_id: str | None = None,
    path: str,
    text: str,
    expected_sha256_current: str,
    _debug_source: str | None = None,
) -> dict[str, Any]:
    """Apply a KB write. SQLite is the target; filesystem kept as backup."""
    # Conflict check against current state
    try:
        current = kb_read(act_id=act_id, scene_id=scene_id, path=path)
    except FileNotFoundError:
        current = ""
    current_sha = _sha256_text(current)

    if current_sha != expected_sha256_current:
        raise ValueError("conflict: file changed since preview")

    # Write to SQLite (source of truth)
    _kb_write_sqlite(act_id, text, scene_id)

    # Also write to filesystem as backup
    try:
        ensure_play_skeleton()
        kb_root = _kb_root_for(act_id=act_id, scene_id=scene_id)
        kb_root.mkdir(parents=True, exist_ok=True)
        target = _resolve_kb_file(kb_root=kb_root, rel_path=path)
        target.parent.mkdir(parents=True, exist_ok=True)
        _write_text(target, text)
    except Exception:
        logger.warning("Filesystem backup failed for %s", act_id)

    after_sha = _sha256_text(text)
    return {"ok": True, "sha256_current": after_sha}


# --- File Attachments (stores paths only, not file content) ---


def list_attachments(
    *,
    act_id: str | None = None,
    scene_id: str | None = None,
    page_id: str | None = None,
) -> list[FileAttachment]:
    """List file attachments at the specified level (Play, Act, Scene, or Page)."""
    from . import play_db

    attachments_data = play_db.list_attachments(act_id=act_id, scene_id=scene_id, page_id=page_id)
    return [
        FileAttachment(
            attachment_id=d["attachment_id"],
            file_path=d["file_path"],
            file_name=d["file_name"],
            file_type=d["file_type"],
            added_at=d["added_at"],
            page_id=d.get("page_id"),
        )
        for d in attachments_data
    ]


def add_attachment(
    *,
    act_id: str | None = None,
    scene_id: str | None = None,
    page_id: str | None = None,
    file_path: str,
    file_name: str | None = None,
) -> list[FileAttachment]:
    """Add a file attachment (stores path only, validates file exists).

    If act_id is None, adds to Play-level attachments.
    """
    if act_id is not None:
        _validate_id(name="act_id", value=act_id)
    if scene_id is not None:
        _validate_id(name="scene_id", value=scene_id)
    if page_id is not None:
        _validate_id(name="page_id", value=page_id)

    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("file_path is required")

    # Validate the file exists
    p = Path(file_path)
    if not p.exists():
        raise ValueError(f"file does not exist: {file_path}")
    if not p.is_file():
        raise ValueError(f"path is not a file: {file_path}")

    # Derive file_name if not provided
    if not file_name:
        file_name = p.name

    from . import play_db

    play_db.add_attachment(
        act_id=act_id, scene_id=scene_id, page_id=page_id, file_path=file_path, file_name=file_name
    )
    return list_attachments(act_id=act_id, scene_id=scene_id, page_id=page_id)


def remove_attachment(
    *,
    act_id: str | None = None,
    scene_id: str | None = None,
    page_id: str | None = None,
    attachment_id: str,
) -> list[FileAttachment]:
    """Remove a file attachment reference by ID.

    If act_id is None, removes from Play-level attachments.
    """
    if act_id is not None:
        _validate_id(name="act_id", value=act_id)
    if scene_id is not None:
        _validate_id(name="scene_id", value=scene_id)
    if page_id is not None:
        _validate_id(name="page_id", value=page_id)
    _validate_id(name="attachment_id", value=attachment_id)

    from . import play_db

    removed = play_db.remove_attachment(attachment_id)
    if not removed:
        raise ValueError("unknown attachment_id")
    return list_attachments(act_id=act_id, scene_id=scene_id, page_id=page_id)
