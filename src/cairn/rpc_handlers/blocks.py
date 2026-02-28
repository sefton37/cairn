"""Blocks RPC handlers - Notion-style block editor operations.

These handlers manage the block-based content system for pages.
"""

from __future__ import annotations

import logging
from typing import Any

from cairn.db import Database
from cairn.play import blocks_db, blocks_tree
from cairn.play.blocks_models import BlockType
from cairn.play.markdown_parser import parse_markdown
from cairn.play.markdown_renderer import render_markdown

from . import RpcError

logger = logging.getLogger(__name__)


# =============================================================================
# Block CRUD Handlers
# =============================================================================


def handle_blocks_create(
    _db: Database,
    *,
    type: str,
    act_id: str,
    parent_id: str | None = None,
    page_id: str | None = None,
    scene_id: str | None = None,
    position: int | None = None,
    rich_text: list[dict[str, Any]] | None = None,
    properties: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new block.

    Args:
        type: Block type (paragraph, heading_1, bulleted_list, etc.)
        act_id: Act this block belongs to
        parent_id: Parent block ID for nesting
        page_id: Page ID for page-level blocks
        scene_id: Scene ID for scene embed blocks
        position: Position among siblings (auto-calculated if None)
        rich_text: Initial rich text content
        properties: Type-specific properties

    Returns:
        Created block data
    """
    try:
        block = blocks_db.create_block(
            type=type,
            act_id=act_id,
            parent_id=parent_id,
            page_id=page_id,
            scene_id=scene_id,
            position=position,
            rich_text=rich_text,
            properties=properties,
        )
        return {"block": block.to_dict()}
    except ValueError as exc:
        raise RpcError(code=-32602, message=str(exc)) from exc


def handle_blocks_get(
    _db: Database,
    *,
    block_id: str,
    include_children: bool = False,
) -> dict[str, Any]:
    """Get a block by ID.

    Args:
        block_id: The block ID
        include_children: Whether to load children recursively

    Returns:
        Block data or error if not found
    """
    block = blocks_db.get_block(block_id)
    if not block:
        raise RpcError(code=-32602, message=f"Block not found: {block_id}")

    if include_children:
        blocks_db._load_children_recursive(block)

    return {"block": block.to_dict(include_children=include_children)}


def handle_blocks_list(
    _db: Database,
    *,
    page_id: str | None = None,
    parent_id: str | None = None,
    act_id: str | None = None,
) -> dict[str, Any]:
    """List blocks with optional filtering.

    Args:
        page_id: Filter by page ID (root blocks of a page)
        parent_id: Filter by parent block ID (children)
        act_id: Filter by act ID

    Returns:
        List of matching blocks
    """
    blocks = blocks_db.list_blocks(
        page_id=page_id,
        parent_id=parent_id,
        act_id=act_id,
    )
    return {"blocks": [b.to_dict() for b in blocks]}


def handle_blocks_update(
    _db: Database,
    *,
    block_id: str,
    rich_text: list[dict[str, Any]] | None = None,
    properties: dict[str, Any] | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    """Update a block.

    Args:
        block_id: The block to update
        rich_text: New rich text content (replaces existing)
        properties: Properties to update (merged with existing)
        position: New position among siblings

    Returns:
        Updated block data
    """
    block = blocks_db.update_block(
        block_id,
        rich_text=rich_text,
        properties=properties,
        position=position,
    )
    if not block:
        raise RpcError(code=-32602, message=f"Block not found: {block_id}")

    return {"block": block.to_dict()}


def handle_blocks_delete(
    _db: Database,
    *,
    block_id: str,
    recursive: bool = True,
) -> dict[str, Any]:
    """Delete a block.

    Args:
        block_id: The block to delete
        recursive: Also delete all descendants (default: True)

    Returns:
        Deletion result
    """
    deleted = blocks_db.delete_block(block_id, recursive=recursive)
    if not deleted:
        raise RpcError(code=-32602, message=f"Block not found: {block_id}")

    return {"deleted": True}


# =============================================================================
# Block Tree Handlers
# =============================================================================


def handle_blocks_move(
    _db: Database,
    *,
    block_id: str,
    new_parent_id: str | None = None,
    new_page_id: str | None = None,
    new_position: int | None = None,
) -> dict[str, Any]:
    """Move a block to a new parent and/or position.

    Args:
        block_id: The block to move
        new_parent_id: New parent block ID (None for root level)
        new_page_id: New page ID (only valid when new_parent_id is None)
        new_position: New position among siblings

    Returns:
        Moved block data
    """
    try:
        block = blocks_tree.move_block(
            block_id,
            new_parent_id=new_parent_id,
            new_page_id=new_page_id,
            new_position=new_position,
        )
        if not block:
            raise RpcError(code=-32602, message=f"Block not found: {block_id}")
        return {"block": block.to_dict()}
    except ValueError as exc:
        raise RpcError(code=-32602, message=str(exc)) from exc


def handle_blocks_reorder(
    _db: Database,
    *,
    block_ids: list[str],
) -> dict[str, Any]:
    """Reorder sibling blocks.

    Args:
        block_ids: List of block IDs in desired order

    Returns:
        Reordered blocks
    """
    try:
        blocks = blocks_tree.reorder_siblings(block_ids)
        return {"blocks": [b.to_dict() for b in blocks]}
    except ValueError as exc:
        raise RpcError(code=-32602, message=str(exc)) from exc


def handle_blocks_ancestors(
    _db: Database,
    *,
    block_id: str,
) -> dict[str, Any]:
    """Get all ancestors of a block.

    Args:
        block_id: The block ID

    Returns:
        List of ancestor blocks (immediate parent first)
    """
    ancestors = blocks_tree.get_ancestors(block_id)
    return {"ancestors": [a.to_dict() for a in ancestors]}


def handle_blocks_descendants(
    _db: Database,
    *,
    block_id: str,
) -> dict[str, Any]:
    """Get all descendants of a block.

    Args:
        block_id: The block ID

    Returns:
        List of descendant blocks (depth-first order)
    """
    descendants = blocks_tree.get_descendants(block_id)
    return {"descendants": [d.to_dict() for d in descendants]}


# =============================================================================
# Page Blocks Handlers
# =============================================================================


def handle_blocks_page_tree(
    _db: Database,
    *,
    page_id: str,
) -> dict[str, Any]:
    """Get the full block tree for a page.

    Args:
        page_id: The page ID

    Returns:
        List of root blocks with children nested
    """
    blocks = blocks_db.get_page_blocks(page_id, recursive=True)
    return {"blocks": [b.to_dict(include_children=True) for b in blocks]}


def handle_blocks_page_markdown(
    _db: Database,
    *,
    page_id: str,
) -> dict[str, Any]:
    """Export page blocks as Markdown.

    Args:
        page_id: The page ID

    Returns:
        Markdown text representation
    """
    blocks = blocks_db.get_page_blocks(page_id, recursive=True)
    markdown = render_markdown(blocks)
    return {"markdown": markdown, "block_count": len(blocks)}


def handle_blocks_import_markdown(
    _db: Database,
    *,
    act_id: str,
    page_id: str | None = None,
    markdown: str,
) -> dict[str, Any]:
    """Import Markdown as blocks.

    Args:
        act_id: Act ID for new blocks
        page_id: Page ID for new blocks
        markdown: Markdown text to import

    Returns:
        Created blocks
    """
    blocks_data = parse_markdown(markdown, act_id, page_id)

    created_blocks = []
    for data in blocks_data:
        block = blocks_db.create_block(
            type=data["type"],
            act_id=data["act_id"],
            page_id=data.get("page_id"),
            position=data.get("position"),
            rich_text=data.get("rich_text"),
            properties=data.get("properties"),
        )
        created_blocks.append(block)

    return {
        "blocks": [b.to_dict() for b in created_blocks],
        "count": len(created_blocks),
    }


# =============================================================================
# Scene Block Handlers
# =============================================================================


def handle_blocks_create_scene(
    _db: Database,
    *,
    act_id: str,
    scene_id: str,
    parent_id: str | None = None,
    page_id: str | None = None,
    position: int | None = None,
) -> dict[str, Any]:
    """Create a scene embed block.

    Args:
        act_id: Act ID (must match scene's act)
        scene_id: Scene to embed
        parent_id: Parent block ID
        page_id: Page ID
        position: Position among siblings

    Returns:
        Created scene block
    """
    try:
        block = blocks_tree.create_scene_block(
            act_id=act_id,
            scene_id=scene_id,
            parent_id=parent_id,
            page_id=page_id,
            position=position,
        )
        return {"block": block.to_dict()}
    except ValueError as exc:
        raise RpcError(code=-32602, message=str(exc)) from exc


def handle_blocks_validate_scene(
    _db: Database,
    *,
    block_id: str,
    scene_id: str,
) -> dict[str, Any]:
    """Validate a scene block reference.

    Args:
        block_id: The block ID
        scene_id: The scene ID to validate

    Returns:
        Validation result
    """
    return blocks_tree.validate_scene_block(block_id, scene_id)


# =============================================================================
# Rich Text Handlers
# =============================================================================


def handle_blocks_rich_text_get(
    _db: Database,
    *,
    block_id: str,
) -> dict[str, Any]:
    """Get rich text spans for a block.

    Args:
        block_id: The block ID

    Returns:
        List of rich text spans
    """
    spans = blocks_db.get_rich_text(block_id)
    return {"spans": [s.to_dict() for s in spans]}


def handle_blocks_rich_text_set(
    _db: Database,
    *,
    block_id: str,
    spans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Replace all rich text for a block.

    Args:
        block_id: The block ID
        spans: List of span data

    Returns:
        Created spans
    """
    created = blocks_db.set_rich_text(block_id, spans)
    return {"spans": [s.to_dict() for s in created]}


# =============================================================================
# Properties Handlers
# =============================================================================


def handle_blocks_property_get(
    _db: Database,
    *,
    block_id: str,
    key: str,
) -> dict[str, Any]:
    """Get a single block property.

    Args:
        block_id: The block ID
        key: Property key

    Returns:
        Property value
    """
    value = blocks_db.get_block_property(block_id, key)
    return {"key": key, "value": value}


def handle_blocks_property_set(
    _db: Database,
    *,
    block_id: str,
    key: str,
    value: Any,
) -> dict[str, Any]:
    """Set a block property.

    Args:
        block_id: The block ID
        key: Property key
        value: Property value

    Returns:
        Success confirmation
    """
    blocks_db.set_block_property(block_id, key, value)
    return {"ok": True, "key": key}


def handle_blocks_property_delete(
    _db: Database,
    *,
    block_id: str,
    key: str,
) -> dict[str, Any]:
    """Delete a block property.

    Args:
        block_id: The block ID
        key: Property key

    Returns:
        Deletion result
    """
    deleted = blocks_db.delete_block_property(block_id, key)
    return {"deleted": deleted, "key": key}


# =============================================================================
# Search Handlers
# =============================================================================


def handle_blocks_search(
    _db: Database,
    *,
    act_id: str,
    query: str,
) -> dict[str, Any]:
    """Search blocks by text content.

    Args:
        act_id: The act ID to search within
        query: Text to search for

    Returns:
        List of matching blocks with their text content
    """
    from cairn import play_db

    results = play_db.search_blocks_in_act(act_id, query)
    return {"blocks": results, "count": len(results)}


def handle_blocks_unchecked_todos(
    _db: Database,
    *,
    act_id: str,
) -> dict[str, Any]:
    """Get all unchecked to-do blocks in an act.

    Args:
        act_id: The act ID

    Returns:
        List of unchecked to-do blocks with their text content
    """
    from cairn import play_db

    todos = play_db.get_unchecked_todos(act_id)
    return {"todos": todos, "count": len(todos)}
