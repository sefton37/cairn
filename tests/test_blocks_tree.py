"""Tests for blocks_tree.py - Tree operations for block hierarchy.

Tests:
- Ancestor/descendant traversal
- Move operations
- Reordering siblings
- Scene block validation
- Tree utilities
"""

from __future__ import annotations

from pathlib import Path

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create isolated data directory."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    import cairn.play_db as play_db

    play_db.close_connection()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def initialized_db(temp_data_dir: Path):
    """Initialize the database."""
    import cairn.play_db as play_db
    from cairn.play import blocks_db, blocks_tree

    play_db.init_db()
    return {"blocks_db": blocks_db, "blocks_tree": blocks_tree}


@pytest.fixture
def test_act(temp_data_dir: Path) -> str:
    """Create a test act."""
    import cairn.play_db as play_db

    play_db.init_db()
    _, act_id = play_db.create_act(title="Test Act")
    return act_id


@pytest.fixture
def test_page(test_act: str) -> str:
    """Create a test page."""
    import cairn.play_db as play_db

    _, page_id = play_db.create_page(act_id=test_act, title="Test Page")
    return page_id


# =============================================================================
# Ancestor/Descendant Tests
# =============================================================================


class TestAncestorDescendant:
    """Test ancestor and descendant traversal."""

    def test_get_ancestors_root_block(self, initialized_db, test_act: str) -> None:
        """Root block has no ancestors."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        block = blocks_db.create_block(type="paragraph", act_id=test_act)

        ancestors = blocks_tree.get_ancestors(block.id)

        assert len(ancestors) == 0

    def test_get_ancestors_nested_block(self, initialized_db, test_act: str) -> None:
        """Nested block returns correct ancestors."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        grandparent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=grandparent.id)
        child = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        ancestors = blocks_tree.get_ancestors(child.id)

        assert len(ancestors) == 2
        assert ancestors[0].id == parent.id  # Immediate parent first
        assert ancestors[1].id == grandparent.id

    def test_get_descendants_no_children(self, initialized_db, test_act: str) -> None:
        """Block with no children returns empty list."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        block = blocks_db.create_block(type="paragraph", act_id=test_act)

        descendants = blocks_tree.get_descendants(block.id)

        assert len(descendants) == 0

    def test_get_descendants_nested(self, initialized_db, test_act: str) -> None:
        """Descendants returns all nested blocks depth-first."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        root = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child1 = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=root.id)
        grandchild = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=child1.id)
        child2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=root.id)

        descendants = blocks_tree.get_descendants(root.id)

        assert len(descendants) == 3
        # Depth-first: child1, grandchild, child2
        ids = [d.id for d in descendants]
        assert ids == [child1.id, grandchild.id, child2.id]

    def test_get_siblings(self, initialized_db, test_act: str) -> None:
        """get_siblings returns blocks with same parent."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        child2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        child3 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        siblings = blocks_tree.get_siblings(child1.id)

        assert len(siblings) == 2
        sibling_ids = {s.id for s in siblings}
        assert sibling_ids == {child2.id, child3.id}

    def test_get_siblings_include_self(self, initialized_db, test_act: str) -> None:
        """get_siblings with include_self=True includes the block."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        child2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        siblings = blocks_tree.get_siblings(child1.id, include_self=True)

        assert len(siblings) == 2
        sibling_ids = {s.id for s in siblings}
        assert child1.id in sibling_ids


# =============================================================================
# Move Operations Tests
# =============================================================================


class TestMoveOperations:
    """Test block move operations."""

    def test_move_block_to_parent(self, initialized_db, test_act: str) -> None:
        """Move a root block into a parent."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type="paragraph", act_id=test_act)

        moved = blocks_tree.move_block(child.id, new_parent_id=parent.id)

        assert moved is not None
        assert moved.parent_id == parent.id

    def test_move_block_to_root(self, initialized_db, test_act: str) -> None:
        """Move a nested block to root level."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        moved = blocks_tree.move_block(child.id, new_parent_id=None)

        assert moved is not None
        assert moved.parent_id is None

    def test_move_block_preserves_content(self, initialized_db, test_act: str) -> None:
        """Moving a block preserves its rich text and properties."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Test content"}],
            properties={"custom": "value"},
        )

        blocks_tree.move_block(child.id, new_parent_id=parent.id)
        moved = blocks_db.get_block(child.id)

        assert moved.plain_text() == "Test content"
        assert moved.properties["custom"] == "value"

    def test_move_block_into_self_raises(self, initialized_db, test_act: str) -> None:
        """Cannot move a block into itself."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        block = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)

        with pytest.raises(ValueError, match="Cannot move block into itself"):
            blocks_tree.move_block(block.id, new_parent_id=block.id)

    def test_move_block_into_descendant_raises(self, initialized_db, test_act: str) -> None:
        """Cannot move a block into its own descendant."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=parent.id)

        with pytest.raises(ValueError, match="Cannot move block into its own descendant"):
            blocks_tree.move_block(parent.id, new_parent_id=child.id)

    def test_move_block_into_non_nestable_raises(self, initialized_db, test_act: str) -> None:
        """Cannot move a block into a non-nestable parent."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        parent = blocks_db.create_block(type="paragraph", act_id=test_act)  # Not nestable
        child = blocks_db.create_block(type="paragraph", act_id=test_act)

        with pytest.raises(ValueError, match="does not support children"):
            blocks_tree.move_block(child.id, new_parent_id=parent.id)

    def test_move_block_nonexistent(self, initialized_db) -> None:
        """Move nonexistent block returns None."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.move_block("nonexistent", new_parent_id=None)
        assert result is None


class TestReorderSiblings:
    """Test sibling reordering."""

    def test_reorder_siblings(self, initialized_db, test_act: str) -> None:
        """Reorder siblings changes positions."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        c1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c3 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        # Original order: c1, c2, c3
        # Reorder to: c3, c1, c2
        reordered = blocks_tree.reorder_siblings([c3.id, c1.id, c2.id])

        assert reordered[0].id == c3.id
        assert reordered[0].position == 0
        assert reordered[1].id == c1.id
        assert reordered[1].position == 1
        assert reordered[2].id == c2.id
        assert reordered[2].position == 2

    def test_reorder_siblings_not_siblings_raises(self, initialized_db, test_act: str) -> None:
        """Reorder with non-siblings raises."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent1 = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        parent2 = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        c1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent1.id)
        c2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent2.id)

        with pytest.raises(ValueError, match="must be siblings"):
            blocks_tree.reorder_siblings([c1.id, c2.id])

    def test_reorder_empty_list(self, initialized_db) -> None:
        """Reorder with empty list returns empty."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.reorder_siblings([])
        assert result == []


class TestInsertBlockAt:
    """Test insert_block_at positioning."""

    def test_insert_after(self, initialized_db, test_act: str) -> None:
        """Insert block after target."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        c1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c3 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        # Insert c3 after c1: c1, c3, c2
        blocks_tree.insert_block_at(c3.id, c1.id, position="after")

        children = blocks_db.list_blocks(parent_id=parent.id)
        positions = [(c.id, c.position) for c in children]

        # Should be ordered: c1(0), c3(1), c2(2)
        assert children[1].id == c3.id

    def test_insert_before(self, initialized_db, test_act: str) -> None:
        """Insert block before target."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        c1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c3 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        # Insert c3 before c1: c3, c1, c2
        blocks_tree.insert_block_at(c3.id, c1.id, position="before")

        children = blocks_db.list_blocks(parent_id=parent.id)

        assert children[0].id == c3.id


# =============================================================================
# Scene Block Validation Tests
# =============================================================================


class TestSceneBlockValidation:
    """Test scene block validation."""

    def test_validate_scene_block_valid(self, initialized_db, test_act: str) -> None:
        """Valid scene block passes validation."""
        import cairn.play_db as play_db
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        _, scene_id = play_db.create_scene(act_id=test_act, title="Test Scene")
        block = blocks_db.create_block(type="scene", act_id=test_act, properties={"scene_id": scene_id})
        # Update scene_id on block
        play_db._get_connection().execute("UPDATE blocks SET scene_id = ? WHERE id = ?", (scene_id, block.id))
        play_db._get_connection().commit()
        block = blocks_db.get_block(block.id)

        result = blocks_tree.validate_scene_block(block.id, scene_id)

        assert result["valid"] is True
        assert result["scene_title"] == "Test Scene"

    def test_validate_scene_block_wrong_act(self, temp_data_dir: Path) -> None:
        """Scene block in different act fails validation."""
        import cairn.play_db as play_db
        from cairn.play import blocks_db, blocks_tree

        play_db.init_db()
        _, act1_id = play_db.create_act(title="Act 1")
        _, act2_id = play_db.create_act(title="Act 2")
        _, scene_id = play_db.create_scene(act_id=act1_id, title="Scene in Act 1")

        block = blocks_db.create_block(type="scene", act_id=act2_id)

        result = blocks_tree.validate_scene_block(block.id, scene_id)

        assert result["valid"] is False
        assert "different act" in result["error"].lower() or act1_id in result["error"]

    def test_validate_scene_block_nonexistent_scene(self, initialized_db, test_act: str) -> None:
        """Validation fails for nonexistent scene."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        block = blocks_db.create_block(type="scene", act_id=test_act)

        result = blocks_tree.validate_scene_block(block.id, "nonexistent-scene")

        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    def test_create_scene_block(self, initialized_db, test_act: str) -> None:
        """create_scene_block creates validated block."""
        import cairn.play_db as play_db
        blocks_tree = initialized_db["blocks_tree"]

        _, scene_id = play_db.create_scene(act_id=test_act, title="Embedded Scene")

        block = blocks_tree.create_scene_block(act_id=test_act, scene_id=scene_id)

        assert block.type.value == "scene"
        assert block.scene_id == scene_id

    def test_create_scene_block_wrong_act_raises(self, temp_data_dir: Path) -> None:
        """create_scene_block raises for mismatched acts."""
        import cairn.play_db as play_db
        from cairn.play import blocks_tree

        play_db.init_db()
        _, act1_id = play_db.create_act(title="Act 1")
        _, act2_id = play_db.create_act(title="Act 2")
        _, scene_id = play_db.create_scene(act_id=act1_id, title="Scene")

        with pytest.raises(ValueError, match="act"):
            blocks_tree.create_scene_block(act_id=act2_id, scene_id=scene_id)


# =============================================================================
# Tree Utilities Tests
# =============================================================================


class TestTreeUtilities:
    """Test tree traversal utilities."""

    def test_get_block_depth(self, initialized_db, test_act: str) -> None:
        """get_block_depth returns correct nesting level."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        root = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=root.id)
        grandchild = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=child.id)

        assert blocks_tree.get_block_depth(root.id) == 0
        assert blocks_tree.get_block_depth(child.id) == 1
        assert blocks_tree.get_block_depth(grandchild.id) == 2

    def test_get_root_block(self, initialized_db, test_act: str) -> None:
        """get_root_block returns root ancestor."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        root = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=root.id)
        grandchild = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=child.id)

        result = blocks_tree.get_root_block(grandchild.id)

        assert result is not None
        assert result.id == root.id

    def test_flatten_tree(self, initialized_db, test_act: str) -> None:
        """flatten_tree produces depth-first list."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        root = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child1 = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act, parent_id=root.id)
        grandchild = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=child1.id)
        child2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=root.id)

        # Build tree structure manually
        grandchild_loaded = blocks_db.get_block(grandchild.id)
        child1_loaded = blocks_db.get_block(child1.id)
        child1_loaded.children = [grandchild_loaded]
        child2_loaded = blocks_db.get_block(child2.id)
        root_loaded = blocks_db.get_block(root.id)
        root_loaded.children = [child1_loaded, child2_loaded]

        flat = blocks_tree.flatten_tree([root_loaded])

        ids = [b.id for b in flat]
        assert ids == [root.id, child1.id, grandchild.id, child2.id]

    def test_build_tree(self, initialized_db, test_act: str) -> None:
        """build_tree creates tree from flat list."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        root = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=root.id)

        flat = [
            blocks_db.get_block(root.id, include_rich_text=False),
            blocks_db.get_block(child.id, include_rich_text=False),
        ]

        tree = blocks_tree.build_tree(flat)

        assert len(tree) == 1
        assert tree[0].id == root.id
        assert len(tree[0].children) == 1
        assert tree[0].children[0].id == child.id

    def test_get_root_block_returns_self_for_root(self, initialized_db, test_act: str) -> None:
        """get_root_block returns block itself if already root."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        root = blocks_db.create_block(type="paragraph", act_id=test_act)

        result = blocks_tree.get_root_block(root.id)

        assert result is not None
        assert result.id == root.id

    def test_get_block_depth_root_is_zero(self, initialized_db, test_act: str) -> None:
        """Root block has depth 0."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]

        root = blocks_db.create_block(type="paragraph", act_id=test_act)

        assert blocks_tree.get_block_depth(root.id) == 0

    def test_flatten_tree_empty(self, initialized_db) -> None:
        """flatten_tree with empty list returns empty."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.flatten_tree([])
        assert result == []

    def test_build_tree_empty(self, initialized_db) -> None:
        """build_tree with empty list returns empty."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.build_tree([])
        assert result == []


# =============================================================================
# Edge Cases Tests
# =============================================================================


class TestBlocksTreeEdgeCases:
    """Test edge cases and error conditions."""

    def test_get_siblings_root_block(self, initialized_db, test_act: str) -> None:
        """Root blocks have siblings that share the same page."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        import cairn.play_db as play_db

        _, page_id = play_db.create_page(act_id=test_act, title="Test Page")

        b1 = blocks_db.create_block(type="paragraph", act_id=test_act, page_id=page_id)
        b2 = blocks_db.create_block(type="paragraph", act_id=test_act, page_id=page_id)
        b3 = blocks_db.create_block(type="paragraph", act_id=test_act, page_id=page_id)

        siblings = blocks_tree.get_siblings(b1.id)

        assert len(siblings) == 2
        sibling_ids = {s.id for s in siblings}
        assert b2.id in sibling_ids
        assert b3.id in sibling_ids

    def test_get_ancestors_nonexistent(self, initialized_db) -> None:
        """get_ancestors for nonexistent block returns empty."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.get_ancestors("nonexistent")
        assert result == []

    def test_get_descendants_nonexistent(self, initialized_db) -> None:
        """get_descendants for nonexistent block returns empty."""
        blocks_tree = initialized_db["blocks_tree"]

        result = blocks_tree.get_descendants("nonexistent")
        assert result == []

    def test_move_block_with_position(self, initialized_db, test_act: str) -> None:
        """Move block specifying new position."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        c1 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c2 = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        c3 = blocks_db.create_block(type="paragraph", act_id=test_act)

        # Move c3 into parent at position 1
        moved = blocks_tree.move_block(c3.id, new_parent_id=parent.id, new_position=1)

        assert moved is not None
        assert moved.parent_id == parent.id
        assert moved.position == 1

    def test_reorder_single_block(self, initialized_db, test_act: str) -> None:
        """Reorder with single block."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        from cairn.play.blocks_models import BlockType

        parent = blocks_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child = blocks_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        result = blocks_tree.reorder_siblings([child.id])

        assert len(result) == 1
        assert result[0].id == child.id
        assert result[0].position == 0

    def test_validate_scene_block_nonexistent_block(self, initialized_db, test_act: str) -> None:
        """validate_scene_block with nonexistent block."""
        import cairn.play_db as play_db
        blocks_tree = initialized_db["blocks_tree"]

        _, scene_id = play_db.create_scene(act_id=test_act, title="Test Scene")

        result = blocks_tree.validate_scene_block("nonexistent", scene_id)

        assert result["valid"] is False
        assert "not found" in result["error"].lower()

    def test_create_scene_block_nonexistent_scene(self, initialized_db, test_act: str) -> None:
        """create_scene_block with nonexistent scene raises."""
        blocks_tree = initialized_db["blocks_tree"]

        with pytest.raises(ValueError, match="not found"):
            blocks_tree.create_scene_block(act_id=test_act, scene_id="nonexistent")

    def test_move_to_different_page(self, initialized_db, test_act: str) -> None:
        """Move block to a different page."""
        blocks_db = initialized_db["blocks_db"]
        blocks_tree = initialized_db["blocks_tree"]
        import cairn.play_db as play_db

        _, page1_id = play_db.create_page(act_id=test_act, title="Page 1")
        _, page2_id = play_db.create_page(act_id=test_act, title="Page 2")

        block = blocks_db.create_block(type="paragraph", act_id=test_act, page_id=page1_id)

        moved = blocks_tree.move_block(block.id, new_page_id=page2_id)

        assert moved is not None
        assert moved.page_id == page2_id
