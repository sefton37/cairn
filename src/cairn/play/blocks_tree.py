"""Tree operations for block hierarchy.

This module provides operations for manipulating the block tree structure:
- Moving blocks between parents
- Reordering siblings
- Getting ancestors and descendants
- Scene block validation
"""

from __future__ import annotations

import logging
from typing import Any

from ..play_db import _get_connection, _transaction, init_db, get_scene

from .blocks_models import Block, BlockType, NESTABLE_TYPES
from .blocks_db import get_block, list_blocks, _now_iso

logger = logging.getLogger(__name__)


# =============================================================================
# Ancestor/Descendant Operations
# =============================================================================


def get_ancestors(block_id: str) -> list[Block]:
    """Get all ancestors of a block, from immediate parent to root.

    Args:
        block_id: The block ID.

    Returns:
        List of ancestor blocks, starting with immediate parent.
    """
    init_db()

    ancestors = []
    current_id = block_id

    while True:
        block = get_block(current_id, include_rich_text=False)
        if not block or not block.parent_id:
            break

        parent = get_block(block.parent_id, include_rich_text=False)
        if not parent:
            break

        ancestors.append(parent)
        current_id = parent.id

    return ancestors


def get_descendants(block_id: str, include_rich_text: bool = False) -> list[Block]:
    """Get all descendants of a block (depth-first).

    Args:
        block_id: The parent block ID.
        include_rich_text: Whether to load rich text for each block.

    Returns:
        List of all descendant blocks in depth-first order.
    """
    init_db()

    descendants = []
    _collect_descendants(block_id, descendants, include_rich_text)
    return descendants


def _collect_descendants(parent_id: str, result: list[Block], include_rich_text: bool) -> None:
    """Recursively collect descendants."""
    children = list_blocks(parent_id=parent_id, include_rich_text=include_rich_text)
    for child in children:
        result.append(child)
        _collect_descendants(child.id, result, include_rich_text)


def get_siblings(block_id: str, include_self: bool = False) -> list[Block]:
    """Get siblings of a block (blocks with the same parent).

    Args:
        block_id: The block ID.
        include_self: Whether to include the block itself.

    Returns:
        List of sibling blocks ordered by position.
    """
    init_db()

    block = get_block(block_id, include_rich_text=False)
    if not block:
        return []

    # Get blocks with same parent
    if block.parent_id:
        siblings = list_blocks(parent_id=block.parent_id, include_rich_text=False)
    elif block.page_id:
        siblings = list_blocks(page_id=block.page_id, include_rich_text=False)
    else:
        siblings = list_blocks(act_id=block.act_id, include_rich_text=False)
        # Filter to root-level blocks
        siblings = [s for s in siblings if s.parent_id is None and s.page_id is None]

    if not include_self:
        siblings = [s for s in siblings if s.id != block_id]

    return siblings


# =============================================================================
# Move Operations
# =============================================================================


def move_block(
    block_id: str,
    *,
    new_parent_id: str | None = None,
    new_page_id: str | None = None,
    new_position: int | None = None,
) -> Block | None:
    """Move a block to a new parent and/or position.

    Args:
        block_id: The block to move.
        new_parent_id: New parent block ID (None for root level).
        new_page_id: New page ID (only valid when new_parent_id is None).
        new_position: New position among siblings (None to append at end).

    Returns:
        Updated block or None if not found.

    Raises:
        ValueError: If move would create a cycle or violate constraints.
    """
    init_db()

    block = get_block(block_id, include_rich_text=False)
    if not block:
        return None

    # Validate: can't move block into itself or its descendants
    if new_parent_id:
        if new_parent_id == block_id:
            raise ValueError("Cannot move block into itself")

        ancestors_of_target = get_ancestors(new_parent_id)
        if any(a.id == block_id for a in ancestors_of_target):
            raise ValueError("Cannot move block into its own descendant")

        # Validate: parent must be nestable
        parent = get_block(new_parent_id, include_rich_text=False)
        if parent and not parent.is_nestable():
            raise ValueError(f"Parent block type '{parent.type.value}' does not support children")

    now = _now_iso()

    with _transaction() as conn:
        # Calculate new position if not specified
        if new_position is None:
            if new_parent_id:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM blocks WHERE parent_id = ?",
                    (new_parent_id,)
                )
            elif new_page_id:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM blocks WHERE page_id = ? AND parent_id IS NULL",
                    (new_page_id,)
                )
            else:
                cursor = conn.execute(
                    "SELECT COALESCE(MAX(position), -1) + 1 FROM blocks WHERE act_id = ? AND parent_id IS NULL AND page_id IS NULL",
                    (block.act_id,)
                )
            new_position = cursor.fetchone()[0]

        # Update the block
        conn.execute("""
            UPDATE blocks
            SET parent_id = ?, page_id = COALESCE(?, page_id), position = ?, updated_at = ?
            WHERE id = ?
        """, (new_parent_id, new_page_id, new_position, now, block_id))

    return get_block(block_id)


def reorder_siblings(block_ids: list[str]) -> list[Block]:
    """Reorder sibling blocks according to the given order.

    Args:
        block_ids: List of block IDs in desired order.

    Returns:
        List of updated blocks in new order.

    Raises:
        ValueError: If blocks are not siblings or IDs are invalid.
    """
    init_db()

    if not block_ids:
        return []

    # Verify all blocks exist and are siblings
    blocks = []
    first_block = get_block(block_ids[0], include_rich_text=False)
    if not first_block:
        raise ValueError(f"Block not found: {block_ids[0]}")

    ref_parent = first_block.parent_id
    ref_page = first_block.page_id
    ref_act = first_block.act_id

    for bid in block_ids:
        block = get_block(bid, include_rich_text=False)
        if not block:
            raise ValueError(f"Block not found: {bid}")
        if block.parent_id != ref_parent or block.page_id != ref_page or block.act_id != ref_act:
            raise ValueError("All blocks must be siblings")
        blocks.append(block)

    now = _now_iso()

    with _transaction() as conn:
        for i, bid in enumerate(block_ids):
            conn.execute(
                "UPDATE blocks SET position = ?, updated_at = ? WHERE id = ?",
                (i, now, bid)
            )

    return [get_block(bid, include_rich_text=False) for bid in block_ids]


def insert_block_at(
    block_id: str,
    target_id: str,
    position: str = "after",
) -> Block | None:
    """Insert a block before or after a target sibling.

    Args:
        block_id: The block to move.
        target_id: The reference sibling block.
        position: "before" or "after" the target.

    Returns:
        Updated block or None if not found.

    Raises:
        ValueError: If blocks are not siblings or position is invalid.
    """
    init_db()

    if position not in ("before", "after"):
        raise ValueError("position must be 'before' or 'after'")

    block = get_block(block_id, include_rich_text=False)
    target = get_block(target_id, include_rich_text=False)

    if not block or not target:
        return None

    # Verify they're siblings (or will be)
    if block.parent_id != target.parent_id:
        # Move to target's parent first
        move_block(block_id, new_parent_id=target.parent_id, new_page_id=target.page_id)
        block = get_block(block_id, include_rich_text=False)
        if not block:
            return None

    # Get all siblings
    siblings = get_siblings(target_id, include_self=True)
    sibling_ids = [s.id for s in siblings]

    # Remove block from current position
    if block_id in sibling_ids:
        sibling_ids.remove(block_id)

    # Insert at target position
    target_idx = sibling_ids.index(target_id)
    if position == "after":
        target_idx += 1

    sibling_ids.insert(target_idx, block_id)

    # Reorder
    reorder_siblings(sibling_ids)

    return get_block(block_id)


# =============================================================================
# Scene Block Validation
# =============================================================================


def validate_scene_block(block_id: str, scene_id: str) -> dict[str, Any]:
    """Validate a scene embed block.

    Scene blocks must reference a scene in the same act as the block.

    Args:
        block_id: The block ID.
        scene_id: The scene ID to embed.

    Returns:
        Validation result with 'valid', 'error', and scene info.
    """
    init_db()

    block = get_block(block_id, include_rich_text=False)
    if not block:
        return {"valid": False, "error": "Block not found"}

    if block.type != BlockType.SCENE:
        return {"valid": False, "error": f"Block type is {block.type.value}, not scene"}

    scene = get_scene(scene_id)
    if not scene:
        return {"valid": False, "error": "Scene not found"}

    if scene["act_id"] != block.act_id:
        return {
            "valid": False,
            "error": f"Scene is in act {scene['act_id']}, block is in act {block.act_id}",
        }

    return {
        "valid": True,
        "scene_id": scene_id,
        "scene_title": scene["title"],
        "scene_stage": scene["stage"],
    }


def create_scene_block(
    *,
    act_id: str,
    scene_id: str,
    parent_id: str | None = None,
    page_id: str | None = None,
    position: int | None = None,
) -> Block:
    """Create a scene embed block with validation.

    Args:
        act_id: Act ID (must match scene's act).
        scene_id: Scene to embed.
        parent_id: Parent block ID.
        page_id: Page ID.
        position: Position among siblings.

    Returns:
        Created block.

    Raises:
        ValueError: If scene is not in the same act.
    """
    from .blocks_db import create_block

    init_db()

    # Validate scene
    scene = get_scene(scene_id)
    if not scene:
        raise ValueError(f"Scene not found: {scene_id}")

    if scene["act_id"] != act_id:
        raise ValueError(
            f"Scene is in act {scene['act_id']}, but block would be in act {act_id}"
        )

    return create_block(
        type=BlockType.SCENE,
        act_id=act_id,
        scene_id=scene_id,
        parent_id=parent_id,
        page_id=page_id,
        position=position,
    )


# =============================================================================
# Tree Traversal Utilities
# =============================================================================


def get_block_depth(block_id: str) -> int:
    """Get the nesting depth of a block (0 for root blocks).

    Args:
        block_id: The block ID.

    Returns:
        Nesting depth (number of ancestors).
    """
    return len(get_ancestors(block_id))


def get_root_block(block_id: str) -> Block | None:
    """Get the root-level ancestor of a block.

    Args:
        block_id: The block ID.

    Returns:
        The root ancestor block, or the block itself if it's a root.
    """
    ancestors = get_ancestors(block_id)
    if ancestors:
        return ancestors[-1]

    return get_block(block_id, include_rich_text=False)


def flatten_tree(root_blocks: list[Block]) -> list[Block]:
    """Flatten a tree of blocks to a depth-first list.

    Args:
        root_blocks: List of root-level blocks with children loaded.

    Returns:
        Flat list of all blocks in depth-first order.
    """
    result = []
    for block in root_blocks:
        _flatten_recursive(block, result)
    return result


def _flatten_recursive(block: Block, result: list[Block]) -> None:
    """Recursively flatten a block tree."""
    result.append(block)
    for child in block.children:
        _flatten_recursive(child, result)


def build_tree(blocks: list[Block]) -> list[Block]:
    """Build a tree structure from a flat list of blocks.

    Args:
        blocks: List of blocks (children field will be populated).

    Returns:
        List of root blocks with children populated.
    """
    blocks_by_id = {b.id: b for b in blocks}
    root_blocks = []

    # Clear existing children
    for block in blocks:
        block.children = []

    # Build tree
    for block in blocks:
        if block.parent_id and block.parent_id in blocks_by_id:
            blocks_by_id[block.parent_id].children.append(block)
        else:
            root_blocks.append(block)

    # Sort children by position
    for block in blocks:
        block.children.sort(key=lambda b: b.position)

    return sorted(root_blocks, key=lambda b: b.position)
