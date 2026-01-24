"""Tests for blocks RPC handlers.

Tests the JSON-RPC interface for block operations.
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

    import reos.play_db as play_db

    play_db.close_connection()

    yield data_dir

    play_db.close_connection()


@pytest.fixture
def mock_db(temp_data_dir: Path):
    """Initialize database and return mock db object."""
    import reos.play_db as play_db

    play_db.init_db()

    # Return a simple mock that handlers expect
    class MockDb:
        pass

    return MockDb()


@pytest.fixture
def test_act(temp_data_dir: Path) -> str:
    """Create a test act."""
    import reos.play_db as play_db

    play_db.init_db()
    _, act_id = play_db.create_act(title="Test Act")
    return act_id


@pytest.fixture
def test_page(test_act: str) -> str:
    """Create a test page."""
    import reos.play_db as play_db

    _, page_id = play_db.create_page(act_id=test_act, title="Test Page")
    return page_id


# =============================================================================
# Block CRUD Tests
# =============================================================================


class TestBlocksCRUDHandlers:
    """Test block CRUD RPC handlers."""

    def test_handle_blocks_create(self, mock_db, test_act: str) -> None:
        """blocks/create creates a new block."""
        from reos.rpc_handlers.blocks import handle_blocks_create

        result = handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Hello world"}],
        )

        assert "block" in result
        assert result["block"]["type"] == "paragraph"
        assert result["block"]["act_id"] == test_act

    def test_handle_blocks_create_with_properties(self, mock_db, test_act: str) -> None:
        """blocks/create with properties."""
        from reos.rpc_handlers.blocks import handle_blocks_create

        result = handle_blocks_create(
            mock_db,
            type="to_do",
            act_id=test_act,
            properties={"checked": True},
        )

        assert result["block"]["properties"]["checked"] is True

    def test_handle_blocks_get(self, mock_db, test_act: str) -> None:
        """blocks/get returns block by ID."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_get

        created = handle_blocks_create(mock_db, type="paragraph", act_id=test_act)
        block_id = created["block"]["id"]

        result = handle_blocks_get(mock_db, block_id=block_id)

        assert result["block"]["id"] == block_id

    def test_handle_blocks_get_not_found(self, mock_db) -> None:
        """blocks/get raises for nonexistent ID."""
        from reos.rpc_handlers.blocks import handle_blocks_get
        from reos.rpc_handlers import RpcError

        with pytest.raises(RpcError, match="not found"):
            handle_blocks_get(mock_db, block_id="nonexistent")

    def test_handle_blocks_list(self, mock_db, test_act: str, test_page: str) -> None:
        """blocks/list returns matching blocks."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_list

        handle_blocks_create(mock_db, type="paragraph", act_id=test_act, page_id=test_page)
        handle_blocks_create(mock_db, type="heading_1", act_id=test_act, page_id=test_page)

        result = handle_blocks_list(mock_db, page_id=test_page)

        assert len(result["blocks"]) == 2

    def test_handle_blocks_update(self, mock_db, test_act: str) -> None:
        """blocks/update modifies block."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_update

        created = handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Original"}],
        )
        block_id = created["block"]["id"]

        result = handle_blocks_update(
            mock_db,
            block_id=block_id,
            rich_text=[{"content": "Updated"}],
        )

        assert result["block"]["rich_text"][0]["content"] == "Updated"

    def test_handle_blocks_delete(self, mock_db, test_act: str) -> None:
        """blocks/delete removes block."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_delete, handle_blocks_get
        from reos.rpc_handlers import RpcError

        created = handle_blocks_create(mock_db, type="paragraph", act_id=test_act)
        block_id = created["block"]["id"]

        result = handle_blocks_delete(mock_db, block_id=block_id)

        assert result["deleted"] is True

        with pytest.raises(RpcError, match="not found"):
            handle_blocks_get(mock_db, block_id=block_id)


# =============================================================================
# Block Tree Tests
# =============================================================================


class TestBlocksTreeHandlers:
    """Test block tree RPC handlers."""

    def test_handle_blocks_move(self, mock_db, test_act: str) -> None:
        """blocks/move moves block to new parent."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_move

        parent = handle_blocks_create(mock_db, type="bulleted_list", act_id=test_act)
        child = handle_blocks_create(mock_db, type="paragraph", act_id=test_act)

        result = handle_blocks_move(
            mock_db,
            block_id=child["block"]["id"],
            new_parent_id=parent["block"]["id"],
        )

        assert result["block"]["parent_id"] == parent["block"]["id"]

    def test_handle_blocks_reorder(self, mock_db, test_act: str) -> None:
        """blocks/reorder changes block positions."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_reorder

        parent = handle_blocks_create(mock_db, type="bulleted_list", act_id=test_act)
        parent_id = parent["block"]["id"]

        c1 = handle_blocks_create(mock_db, type="paragraph", act_id=test_act, parent_id=parent_id)
        c2 = handle_blocks_create(mock_db, type="paragraph", act_id=test_act, parent_id=parent_id)
        c3 = handle_blocks_create(mock_db, type="paragraph", act_id=test_act, parent_id=parent_id)

        # Reorder to c3, c1, c2
        result = handle_blocks_reorder(
            mock_db,
            block_ids=[c3["block"]["id"], c1["block"]["id"], c2["block"]["id"]],
        )

        assert result["blocks"][0]["id"] == c3["block"]["id"]
        assert result["blocks"][0]["position"] == 0

    def test_handle_blocks_ancestors(self, mock_db, test_act: str) -> None:
        """blocks/ancestors returns ancestor chain."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_ancestors

        grandparent = handle_blocks_create(mock_db, type="bulleted_list", act_id=test_act)
        parent = handle_blocks_create(
            mock_db, type="bulleted_list", act_id=test_act, parent_id=grandparent["block"]["id"]
        )
        child = handle_blocks_create(
            mock_db, type="paragraph", act_id=test_act, parent_id=parent["block"]["id"]
        )

        result = handle_blocks_ancestors(mock_db, block_id=child["block"]["id"])

        assert len(result["ancestors"]) == 2

    def test_handle_blocks_descendants(self, mock_db, test_act: str) -> None:
        """blocks/descendants returns all descendants."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_descendants

        parent = handle_blocks_create(mock_db, type="bulleted_list", act_id=test_act)
        handle_blocks_create(mock_db, type="paragraph", act_id=test_act, parent_id=parent["block"]["id"])
        handle_blocks_create(mock_db, type="paragraph", act_id=test_act, parent_id=parent["block"]["id"])

        result = handle_blocks_descendants(mock_db, block_id=parent["block"]["id"])

        assert len(result["descendants"]) == 2


# =============================================================================
# Page Blocks Tests
# =============================================================================


class TestBlocksPageHandlers:
    """Test page-level block handlers."""

    def test_handle_blocks_page_tree(self, mock_db, test_act: str, test_page: str) -> None:
        """blocks/page/tree returns block tree for page."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_page_tree

        handle_blocks_create(mock_db, type="heading_1", act_id=test_act, page_id=test_page)
        handle_blocks_create(mock_db, type="paragraph", act_id=test_act, page_id=test_page)

        result = handle_blocks_page_tree(mock_db, page_id=test_page)

        assert len(result["blocks"]) == 2

    def test_handle_blocks_page_markdown(self, mock_db, test_act: str, test_page: str) -> None:
        """blocks/page/markdown exports page as markdown."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_page_markdown

        handle_blocks_create(
            mock_db,
            type="heading_1",
            act_id=test_act,
            page_id=test_page,
            rich_text=[{"content": "Title"}],
        )
        handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            page_id=test_page,
            rich_text=[{"content": "Content"}],
        )

        result = handle_blocks_page_markdown(mock_db, page_id=test_page)

        assert "# Title" in result["markdown"]
        assert "Content" in result["markdown"]

    def test_handle_blocks_import_markdown(self, mock_db, test_act: str) -> None:
        """blocks/import/markdown creates blocks from markdown."""
        from reos.rpc_handlers.blocks import handle_blocks_import_markdown

        markdown = """# Title

This is a paragraph.

- Item 1
- Item 2"""

        result = handle_blocks_import_markdown(
            mock_db,
            act_id=test_act,
            markdown=markdown,
        )

        assert result["count"] >= 3  # heading + paragraph + 2 list items


# =============================================================================
# Rich Text Tests
# =============================================================================


class TestBlocksRichTextHandlers:
    """Test rich text RPC handlers."""

    def test_handle_blocks_rich_text_get(self, mock_db, test_act: str) -> None:
        """blocks/rich_text/get returns spans."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_rich_text_get

        created = handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Hello"}, {"content": " world", "bold": True}],
        )

        result = handle_blocks_rich_text_get(mock_db, block_id=created["block"]["id"])

        assert len(result["spans"]) == 2

    def test_handle_blocks_rich_text_set(self, mock_db, test_act: str) -> None:
        """blocks/rich_text/set replaces spans."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_rich_text_set

        created = handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Original"}],
        )

        result = handle_blocks_rich_text_set(
            mock_db,
            block_id=created["block"]["id"],
            spans=[{"content": "New content"}],
        )

        assert len(result["spans"]) == 1
        assert result["spans"][0]["content"] == "New content"


# =============================================================================
# Properties Tests
# =============================================================================


class TestBlocksPropertyHandlers:
    """Test block property RPC handlers."""

    def test_handle_blocks_property_get(self, mock_db, test_act: str) -> None:
        """blocks/property/get returns property value."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_property_get

        created = handle_blocks_create(
            mock_db,
            type="code",
            act_id=test_act,
            properties={"language": "python"},
        )

        result = handle_blocks_property_get(
            mock_db,
            block_id=created["block"]["id"],
            key="language",
        )

        assert result["value"] == "python"

    def test_handle_blocks_property_set(self, mock_db, test_act: str) -> None:
        """blocks/property/set sets property value."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_property_set, handle_blocks_property_get

        created = handle_blocks_create(mock_db, type="code", act_id=test_act)

        handle_blocks_property_set(
            mock_db,
            block_id=created["block"]["id"],
            key="language",
            value="javascript",
        )

        result = handle_blocks_property_get(
            mock_db,
            block_id=created["block"]["id"],
            key="language",
        )

        assert result["value"] == "javascript"

    def test_handle_blocks_property_delete(self, mock_db, test_act: str) -> None:
        """blocks/property/delete removes property."""
        from reos.rpc_handlers.blocks import (
            handle_blocks_create,
            handle_blocks_property_delete,
            handle_blocks_property_get,
        )

        created = handle_blocks_create(
            mock_db,
            type="to_do",
            act_id=test_act,
            properties={"checked": True},
        )

        result = handle_blocks_property_delete(
            mock_db,
            block_id=created["block"]["id"],
            key="checked",
        )

        assert result["deleted"] is True

        get_result = handle_blocks_property_get(
            mock_db,
            block_id=created["block"]["id"],
            key="checked",
        )
        assert get_result["value"] is None


# =============================================================================
# Scene Block Tests
# =============================================================================


class TestBlocksSceneHandlers:
    """Test scene block RPC handlers."""

    def test_handle_blocks_create_scene(self, mock_db, test_act: str) -> None:
        """blocks/scene/create creates scene embed block."""
        import reos.play_db as play_db
        from reos.rpc_handlers.blocks import handle_blocks_create_scene

        _, scene_id = play_db.create_scene(act_id=test_act, title="Test Scene")

        result = handle_blocks_create_scene(
            mock_db,
            act_id=test_act,
            scene_id=scene_id,
        )

        assert result["block"]["type"] == "scene"
        assert result["block"]["scene_id"] == scene_id

    def test_handle_blocks_validate_scene(self, mock_db, test_act: str) -> None:
        """blocks/scene/validate validates scene reference."""
        import reos.play_db as play_db
        from reos.rpc_handlers.blocks import handle_blocks_create_scene, handle_blocks_validate_scene

        _, scene_id = play_db.create_scene(act_id=test_act, title="Test Scene")
        created = handle_blocks_create_scene(mock_db, act_id=test_act, scene_id=scene_id)

        result = handle_blocks_validate_scene(
            mock_db,
            block_id=created["block"]["id"],
            scene_id=scene_id,
        )

        assert result["valid"] is True


# =============================================================================
# Search Tests
# =============================================================================


class TestBlocksSearchHandlers:
    """Test block search RPC handlers."""

    def test_handle_blocks_search(self, mock_db, test_act: str) -> None:
        """blocks/search finds blocks by text."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_search

        handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Hello world"}],
        )
        handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Goodbye world"}],
        )
        handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Something else"}],
        )

        result = handle_blocks_search(mock_db, act_id=test_act, query="world")

        assert result["count"] == 2
        texts = [b["text"] for b in result["blocks"]]
        assert "Hello world" in texts
        assert "Goodbye world" in texts

    def test_handle_blocks_search_no_matches(self, mock_db, test_act: str) -> None:
        """blocks/search returns empty for no matches."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_search

        handle_blocks_create(
            mock_db,
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Hello"}],
        )

        result = handle_blocks_search(mock_db, act_id=test_act, query="nonexistent")

        assert result["count"] == 0
        assert result["blocks"] == []

    def test_handle_blocks_unchecked_todos(self, mock_db, test_act: str) -> None:
        """blocks/unchecked_todos returns incomplete to-dos."""
        from reos.rpc_handlers.blocks import handle_blocks_create, handle_blocks_unchecked_todos

        handle_blocks_create(
            mock_db,
            type="to_do",
            act_id=test_act,
            rich_text=[{"content": "Unchecked task"}],
            properties={"checked": False},
        )
        handle_blocks_create(
            mock_db,
            type="to_do",
            act_id=test_act,
            rich_text=[{"content": "Checked task"}],
            properties={"checked": True},
        )
        handle_blocks_create(
            mock_db,
            type="to_do",
            act_id=test_act,
            rich_text=[{"content": "Another unchecked"}],
        )

        result = handle_blocks_unchecked_todos(mock_db, act_id=test_act)

        assert result["count"] == 2
        texts = [t["text"] for t in result["todos"]]
        assert "Unchecked task" in texts
        assert "Another unchecked" in texts
        assert "Checked task" not in texts
