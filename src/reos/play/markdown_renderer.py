"""Render blocks to Markdown.

This module converts Block objects back to Markdown text for export.
"""

from __future__ import annotations

from typing import Any

from .blocks_models import Block, BlockType, RichTextSpan


def render_markdown(blocks: list[Block], include_children: bool = True) -> str:
    """Render a list of blocks to Markdown.

    Args:
        blocks: List of Block objects to render.
        include_children: Whether to render nested children.

    Returns:
        Markdown text.
    """
    lines = []

    for i, block in enumerate(blocks):
        rendered = _render_block(block, include_children=include_children, depth=0)
        if rendered:
            lines.append(rendered)
            # Add blank line between blocks (except for dividers)
            if block.type != BlockType.DIVIDER and i < len(blocks) - 1:
                lines.append("")

    return "\n".join(lines)


def _render_block(block: Block, include_children: bool = True, depth: int = 0) -> str:
    """Render a single block to Markdown."""
    block_type = block.type if isinstance(block.type, BlockType) else BlockType(block.type)

    if block_type == BlockType.PAGE:
        return _render_page(block, include_children, depth)
    elif block_type == BlockType.PARAGRAPH:
        return _render_paragraph(block, depth)
    elif block_type in (BlockType.HEADING_1, BlockType.HEADING_2, BlockType.HEADING_3):
        return _render_heading(block, depth)
    elif block_type == BlockType.BULLETED_LIST:
        return _render_bulleted_list(block, include_children, depth)
    elif block_type == BlockType.NUMBERED_LIST:
        return _render_numbered_list(block, include_children, depth)
    elif block_type == BlockType.TO_DO:
        return _render_todo(block, include_children, depth)
    elif block_type == BlockType.CODE:
        return _render_code(block, depth)
    elif block_type == BlockType.DIVIDER:
        return _render_divider(depth)
    elif block_type == BlockType.CALLOUT:
        return _render_callout(block, include_children, depth)
    elif block_type == BlockType.SCENE:
        return _render_scene(block, depth)
    else:
        # Default: render as paragraph
        return _render_paragraph(block, depth)


def _render_page(block: Block, include_children: bool, depth: int) -> str:
    """Render a page block (as title heading)."""
    title = block.properties.get("title", block.plain_text() or "Untitled")
    lines = [f"# {title}"]

    if include_children and block.children:
        lines.append("")
        for child in block.children:
            lines.append(_render_block(child, include_children, depth))

    return "\n".join(lines)


def _render_paragraph(block: Block, depth: int) -> str:
    """Render a paragraph block."""
    indent = "  " * depth
    text = _render_rich_text(block.rich_text)
    return f"{indent}{text}"


def _render_heading(block: Block, depth: int) -> str:
    """Render a heading block."""
    block_type = block.type if isinstance(block.type, BlockType) else BlockType(block.type)

    if block_type == BlockType.HEADING_1:
        prefix = "#"
    elif block_type == BlockType.HEADING_2:
        prefix = "##"
    else:
        prefix = "###"

    text = _render_rich_text(block.rich_text)
    return f"{prefix} {text}"


def _render_bulleted_list(block: Block, include_children: bool, depth: int) -> str:
    """Render a bulleted list item."""
    indent = "  " * depth
    text = _render_rich_text(block.rich_text)
    lines = [f"{indent}- {text}"]

    if include_children and block.children:
        for child in block.children:
            lines.append(_render_block(child, include_children, depth + 1))

    return "\n".join(lines)


def _render_numbered_list(block: Block, include_children: bool, depth: int) -> str:
    """Render a numbered list item."""
    indent = "  " * depth
    text = _render_rich_text(block.rich_text)
    lines = [f"{indent}1. {text}"]

    if include_children and block.children:
        for child in block.children:
            lines.append(_render_block(child, include_children, depth + 1))

    return "\n".join(lines)


def _render_todo(block: Block, include_children: bool, depth: int) -> str:
    """Render a to-do block as checkbox."""
    indent = "  " * depth
    checked = block.properties.get("checked", False)
    checkbox = "[x]" if checked else "[ ]"
    text = _render_rich_text(block.rich_text)
    lines = [f"{indent}- {checkbox} {text}"]

    if include_children and block.children:
        for child in block.children:
            lines.append(_render_block(child, include_children, depth + 1))

    return "\n".join(lines)


def _render_code(block: Block, depth: int) -> str:
    """Render a code block."""
    language = block.properties.get("language", "")
    content = block.plain_text()
    return f"```{language}\n{content}\n```"


def _render_divider(depth: int) -> str:
    """Render a divider."""
    return "---"


def _render_callout(block: Block, include_children: bool, depth: int) -> str:
    """Render a callout block as blockquote."""
    icon = block.properties.get("icon", ">")
    text = _render_rich_text(block.rich_text)
    lines = [f"> {icon} {text}"]

    if include_children and block.children:
        for child in block.children:
            child_md = _render_block(child, include_children, 0)
            # Prefix each line with >
            for line in child_md.split("\n"):
                lines.append(f"> {line}")

    return "\n".join(lines)


def _render_scene(block: Block, depth: int) -> str:
    """Render a scene embed with details.

    Fetches scene information and renders as a formatted block.
    Falls back to ID only if scene not found.
    """
    scene_id = block.scene_id or block.properties.get("scene_id", "")
    if not scene_id:
        return "> [Scene embed: no scene linked]"

    snippet = get_scene_snippet(scene_id)
    if snippet:
        return render_scene_block(snippet)
    else:
        return f"> [Scene: {scene_id}]"


def get_scene_snippet(scene_id: str, max_notes_length: int = 100) -> dict | None:
    """Get a snippet of scene information for embedding.

    Args:
        scene_id: The scene ID.
        max_notes_length: Maximum length of notes preview.

    Returns:
        Dict with scene snippet data, or None if not found.
    """
    # Import here to avoid circular imports
    from ..play_db import get_scene

    scene = get_scene(scene_id)
    if not scene:
        return None

    # Truncate notes for preview
    notes = scene.get("notes", "")
    if notes and len(notes) > max_notes_length:
        notes = notes[:max_notes_length].rsplit(" ", 1)[0] + "..."

    return {
        "scene_id": scene_id,
        "title": scene.get("title", "Untitled"),
        "stage": scene.get("stage", "planning"),
        "notes_preview": notes,
        "has_calendar": bool(scene.get("calendar_event_id")),
        "calendar_start": scene.get("calendar_event_start"),
    }


def render_scene_block(snippet: dict) -> str:
    """Render a scene snippet as Markdown.

    Args:
        snippet: Scene snippet dict from get_scene_snippet.

    Returns:
        Formatted Markdown string.
    """
    title = snippet.get("title", "Untitled")
    stage = snippet.get("stage", "planning")
    notes = snippet.get("notes_preview", "")

    # Stage emoji mapping
    stage_emoji = {
        "planning": "\U0001F4CB",    # clipboard
        "active": "\U0001F3AF",      # target
        "awaiting_data": "\u23F3",   # hourglass
        "complete": "\u2705",         # check mark
    }
    emoji = stage_emoji.get(stage, "\U0001F4CB")

    lines = [f"> {emoji} **{title}** ({stage})"]

    if notes:
        lines.append(f"> {notes}")

    # Add calendar info if present
    if snippet.get("has_calendar") and snippet.get("calendar_start"):
        lines.append(f"> \U0001F4C5 {snippet['calendar_start']}")

    return "\n".join(lines)


def _render_rich_text(spans: list[RichTextSpan]) -> str:
    """Render rich text spans to Markdown."""
    if not spans:
        return ""

    parts = []
    for span in spans:
        text = _render_span(span)
        parts.append(text)

    return "".join(parts)


def _render_span(span: RichTextSpan) -> str:
    """Render a single rich text span with formatting."""
    content = span.content

    # Handle empty content
    if not content:
        return ""

    # Apply formatting in order: code > link > strikethrough > bold > italic
    # Code formatting overrides others
    if span.code:
        return f"`{content}`"

    # Apply text formatting
    if span.bold and span.italic:
        content = f"***{content}***"
    elif span.bold:
        content = f"**{content}**"
    elif span.italic:
        content = f"*{content}*"

    if span.strikethrough:
        content = f"~~{content}~~"

    # Apply link
    if span.link_url:
        content = f"[{content}]({span.link_url})"

    return content


# =============================================================================
# Block to Dict Rendering (for API responses)
# =============================================================================


def blocks_to_markdown_dict(blocks: list[Block]) -> dict[str, Any]:
    """Convert blocks to a dict with markdown and metadata.

    Args:
        blocks: List of blocks to render.

    Returns:
        Dict with 'markdown' text and 'block_count'.
    """
    return {
        "markdown": render_markdown(blocks),
        "block_count": len(blocks),
    }
