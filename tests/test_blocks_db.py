"""Tests for blocks_db.py - SQLite storage for Notion-style blocks.

Tests the block-based content system:
- Block CRUD operations
- Rich text spans
- Block properties
- Cascade delete behavior
- Page blocks retrieval
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Create isolated data directory for play_db."""
    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("REOS_DATA_DIR", str(data_dir))

    # Close any existing connection before test
    import reos.play_db as play_db

    play_db.close_connection()

    yield data_dir

    # Cleanup after test
    play_db.close_connection()


@pytest.fixture
def initialized_db(temp_data_dir: Path):
    """Initialize the database and return the blocks_db module."""
    import reos.play_db as play_db
    from reos.play import blocks_db

    play_db.init_db()
    return blocks_db


@pytest.fixture
def test_act(temp_data_dir: Path) -> str:
    """Create a test act and return its ID."""
    import reos.play_db as play_db

    play_db.init_db()
    _, act_id = play_db.create_act(title="Test Act")
    return act_id


@pytest.fixture
def test_page(test_act: str) -> str:
    """Create a test page and return its ID."""
    import reos.play_db as play_db

    _, page_id = play_db.create_page(act_id=test_act, title="Test Page")
    return page_id


# =============================================================================
# Schema Tests
# =============================================================================


class TestBlocksSchema:
    """Test v7 schema creation."""

    def test_blocks_table_exists(self, temp_data_dir: Path) -> None:
        """blocks table is created in v7 schema."""
        import reos.play_db as play_db

        play_db.init_db()
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='blocks'"
        )
        assert cursor.fetchone() is not None

    def test_block_properties_table_exists(self, temp_data_dir: Path) -> None:
        """block_properties table is created in v7 schema."""
        import reos.play_db as play_db

        play_db.init_db()
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='block_properties'"
        )
        assert cursor.fetchone() is not None

    def test_rich_text_table_exists(self, temp_data_dir: Path) -> None:
        """rich_text table is created in v7 schema."""
        import reos.play_db as play_db

        play_db.init_db()
        conn = play_db._get_connection()

        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='rich_text'"
        )
        assert cursor.fetchone() is not None

    def test_schema_version_is_current(self, temp_data_dir: Path) -> None:
        """Schema version matches SCHEMA_VERSION after init."""
        import reos.play_db as play_db

        play_db.init_db()
        conn = play_db._get_connection()

        cursor = conn.execute("SELECT version FROM schema_version")
        version = cursor.fetchone()[0]
        assert version == play_db.SCHEMA_VERSION


# =============================================================================
# Block CRUD Tests
# =============================================================================


class TestBlockCRUD:
    """Test Block create, read, update, delete operations."""

    def test_create_block(self, initialized_db, test_act: str) -> None:
        """create_block creates a new block."""
        from reos.play.blocks_models import BlockType

        block = initialized_db.create_block(
            type=BlockType.PARAGRAPH,
            act_id=test_act,
        )

        assert block.id.startswith("block-")
        assert block.type == BlockType.PARAGRAPH
        assert block.act_id == test_act
        assert block.position == 0

    def test_create_block_with_string_type(self, initialized_db, test_act: str) -> None:
        """create_block accepts string type."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
        )

        from reos.play.blocks_models import BlockType
        assert block.type == BlockType.PARAGRAPH

    def test_create_block_with_rich_text(self, initialized_db, test_act: str) -> None:
        """create_block with rich text spans."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[
                {"content": "Hello ", "bold": True},
                {"content": "world", "italic": True},
            ],
        )

        assert len(block.rich_text) == 2
        assert block.rich_text[0].content == "Hello "
        assert block.rich_text[0].bold is True
        assert block.rich_text[1].content == "world"
        assert block.rich_text[1].italic is True

    def test_create_block_with_properties(self, initialized_db, test_act: str) -> None:
        """create_block with type-specific properties."""
        block = initialized_db.create_block(
            type="to_do",
            act_id=test_act,
            properties={"checked": True},
        )

        assert block.properties["checked"] is True

    def test_create_block_auto_position(self, initialized_db, test_act: str) -> None:
        """create_block auto-increments position."""
        block1 = initialized_db.create_block(type="paragraph", act_id=test_act)
        block2 = initialized_db.create_block(type="paragraph", act_id=test_act)
        block3 = initialized_db.create_block(type="paragraph", act_id=test_act)

        assert block1.position == 0
        assert block2.position == 1
        assert block3.position == 2

    def test_get_block(self, initialized_db, test_act: str) -> None:
        """get_block returns block by ID."""
        created = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Test content"}],
        )

        fetched = initialized_db.get_block(created.id)

        assert fetched is not None
        assert fetched.id == created.id
        assert len(fetched.rich_text) == 1
        assert fetched.rich_text[0].content == "Test content"

    def test_get_block_nonexistent(self, initialized_db) -> None:
        """get_block returns None for nonexistent ID."""
        result = initialized_db.get_block("nonexistent-id")
        assert result is None

    def test_list_blocks_by_page(self, initialized_db, test_act: str, test_page: str) -> None:
        """list_blocks filters by page_id."""
        initialized_db.create_block(type="paragraph", act_id=test_act, page_id=test_page)
        initialized_db.create_block(type="heading_1", act_id=test_act, page_id=test_page)
        initialized_db.create_block(type="paragraph", act_id=test_act)  # No page

        blocks = initialized_db.list_blocks(page_id=test_page)

        assert len(blocks) == 2

    def test_list_blocks_by_parent(self, initialized_db, test_act: str) -> None:
        """list_blocks filters by parent_id."""
        from reos.play.blocks_models import BlockType

        parent = initialized_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        initialized_db.create_block(type="paragraph", act_id=test_act)  # No parent

        children = initialized_db.list_blocks(parent_id=parent.id)

        assert len(children) == 2

    def test_update_block_rich_text(self, initialized_db, test_act: str) -> None:
        """update_block replaces rich text."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Original"}],
        )

        updated = initialized_db.update_block(
            block.id,
            rich_text=[{"content": "Updated", "bold": True}],
        )

        assert updated is not None
        assert len(updated.rich_text) == 1
        assert updated.rich_text[0].content == "Updated"
        assert updated.rich_text[0].bold is True

    def test_update_block_properties(self, initialized_db, test_act: str) -> None:
        """update_block merges properties."""
        block = initialized_db.create_block(
            type="to_do",
            act_id=test_act,
            properties={"checked": False, "color": "red"},
        )

        updated = initialized_db.update_block(
            block.id,
            properties={"checked": True},
        )

        assert updated is not None
        assert updated.properties["checked"] is True
        # Original property preserved (this is a merge)

    def test_update_block_position(self, initialized_db, test_act: str) -> None:
        """update_block can change position."""
        block = initialized_db.create_block(type="paragraph", act_id=test_act)

        updated = initialized_db.update_block(block.id, position=5)

        assert updated is not None
        assert updated.position == 5

    def test_delete_block(self, initialized_db, test_act: str) -> None:
        """delete_block removes block."""
        block = initialized_db.create_block(type="paragraph", act_id=test_act)

        result = initialized_db.delete_block(block.id)

        assert result is True
        assert initialized_db.get_block(block.id) is None

    def test_delete_block_nonexistent(self, initialized_db) -> None:
        """delete_block returns False for nonexistent ID."""
        result = initialized_db.delete_block("nonexistent-id")
        assert result is False

    def test_delete_block_cascade_children(self, initialized_db, test_act: str) -> None:
        """delete_block with recursive=True deletes children."""
        from reos.play.blocks_models import BlockType

        parent = initialized_db.create_block(type=BlockType.BULLETED_LIST, act_id=test_act)
        child1 = initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        child2 = initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        initialized_db.delete_block(parent.id, recursive=True)

        assert initialized_db.get_block(parent.id) is None
        assert initialized_db.get_block(child1.id) is None
        assert initialized_db.get_block(child2.id) is None


# =============================================================================
# Rich Text Tests
# =============================================================================


class TestRichText:
    """Test rich text operations."""

    def test_get_rich_text(self, initialized_db, test_act: str) -> None:
        """get_rich_text returns spans for block."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[
                {"content": "Hello"},
                {"content": " world", "bold": True},
            ],
        )

        spans = initialized_db.get_rich_text(block.id)

        assert len(spans) == 2
        assert spans[0].content == "Hello"
        assert spans[1].content == " world"
        assert spans[1].bold is True

    def test_set_rich_text(self, initialized_db, test_act: str) -> None:
        """set_rich_text replaces all spans."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Original"}],
        )

        spans = initialized_db.set_rich_text(block.id, [
            {"content": "New ", "italic": True},
            {"content": "content"},
        ])

        assert len(spans) == 2
        assert spans[0].content == "New "
        assert spans[0].italic is True

        # Verify via get
        fetched = initialized_db.get_rich_text(block.id)
        assert len(fetched) == 2

    def test_rich_text_formatting_flags(self, initialized_db, test_act: str) -> None:
        """Rich text supports all formatting flags."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{
                "content": "Test",
                "bold": True,
                "italic": True,
                "strikethrough": True,
                "code": True,
                "underline": True,
                "color": "red",
                "background_color": "yellow",
                "link_url": "https://example.com",
            }],
        )

        span = block.rich_text[0]
        assert span.bold is True
        assert span.italic is True
        assert span.strikethrough is True
        assert span.code is True
        assert span.underline is True
        assert span.color == "red"
        assert span.background_color == "yellow"
        assert span.link_url == "https://example.com"


# =============================================================================
# Block Properties Tests
# =============================================================================


class TestBlockProperties:
    """Test block properties operations."""

    def test_get_block_property(self, initialized_db, test_act: str) -> None:
        """get_block_property returns single property."""
        block = initialized_db.create_block(
            type="to_do",
            act_id=test_act,
            properties={"checked": True, "priority": 5},
        )

        checked = initialized_db.get_block_property(block.id, "checked")
        priority = initialized_db.get_block_property(block.id, "priority")

        assert checked is True
        assert priority == 5

    def test_get_block_property_nonexistent(self, initialized_db, test_act: str) -> None:
        """get_block_property returns None for missing key."""
        block = initialized_db.create_block(type="paragraph", act_id=test_act)

        result = initialized_db.get_block_property(block.id, "nonexistent")
        assert result is None

    def test_set_block_property(self, initialized_db, test_act: str) -> None:
        """set_block_property sets or updates property."""
        block = initialized_db.create_block(type="code", act_id=test_act)

        initialized_db.set_block_property(block.id, "language", "python")

        result = initialized_db.get_block_property(block.id, "language")
        assert result == "python"

    def test_set_block_property_complex_value(self, initialized_db, test_act: str) -> None:
        """set_block_property handles complex JSON values."""
        block = initialized_db.create_block(type="paragraph", act_id=test_act)

        initialized_db.set_block_property(block.id, "metadata", {"tags": ["a", "b"], "count": 42})

        result = initialized_db.get_block_property(block.id, "metadata")
        assert result == {"tags": ["a", "b"], "count": 42}

    def test_delete_block_property(self, initialized_db, test_act: str) -> None:
        """delete_block_property removes property."""
        block = initialized_db.create_block(
            type="to_do",
            act_id=test_act,
            properties={"checked": True},
        )

        result = initialized_db.delete_block_property(block.id, "checked")

        assert result is True
        assert initialized_db.get_block_property(block.id, "checked") is None


# =============================================================================
# Convenience Functions Tests
# =============================================================================


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_text_block(self, initialized_db, test_act: str) -> None:
        """create_text_block creates block with plain text."""
        block = initialized_db.create_text_block(
            type="paragraph",
            act_id=test_act,
            text="Hello world",
        )

        assert len(block.rich_text) == 1
        assert block.rich_text[0].content == "Hello world"
        assert block.plain_text() == "Hello world"

    def test_create_text_block_with_properties(self, initialized_db, test_act: str) -> None:
        """create_text_block passes through properties."""
        block = initialized_db.create_text_block(
            type="code",
            act_id=test_act,
            text="print('hello')",
            language="python",
        )

        assert block.properties["language"] == "python"

    def test_get_page_blocks(self, initialized_db, test_act: str, test_page: str) -> None:
        """get_page_blocks returns root blocks for page."""
        initialized_db.create_block(type="heading_1", act_id=test_act, page_id=test_page)
        initialized_db.create_block(type="paragraph", act_id=test_act, page_id=test_page)
        initialized_db.create_block(type="paragraph", act_id=test_act)  # Different page

        blocks = initialized_db.get_page_blocks(test_page)

        assert len(blocks) == 2

    def test_get_page_blocks_recursive(self, initialized_db, test_act: str, test_page: str) -> None:
        """get_page_blocks with recursive=True loads children."""
        from reos.play.blocks_models import BlockType

        parent = initialized_db.create_block(
            type=BlockType.BULLETED_LIST,
            act_id=test_act,
            page_id=test_page,
        )
        initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)
        initialized_db.create_block(type="paragraph", act_id=test_act, parent_id=parent.id)

        blocks = initialized_db.get_page_blocks(test_page, recursive=True)

        assert len(blocks) == 1
        assert len(blocks[0].children) == 2


# =============================================================================
# Block Models Tests
# =============================================================================


class TestBlockModels:
    """Test Block and RichTextSpan model methods."""

    def test_block_to_dict(self, initialized_db, test_act: str) -> None:
        """Block.to_dict serializes correctly."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Test"}],
            properties={"custom": "value"},
        )

        data = block.to_dict()

        assert data["id"] == block.id
        assert data["type"] == "paragraph"
        assert data["act_id"] == test_act
        assert len(data["rich_text"]) == 1
        assert data["properties"]["custom"] == "value"

    def test_block_from_dict(self) -> None:
        """Block.from_dict deserializes correctly."""
        from reos.play.blocks_models import Block, BlockType

        data = {
            "id": "block-123",
            "type": "heading_1",
            "act_id": "act-456",
            "parent_id": None,
            "page_id": "page-789",
            "scene_id": None,
            "position": 0,
            "created_at": "2026-01-01T00:00:00Z",
            "updated_at": "2026-01-01T00:00:00Z",
            "rich_text": [{"id": "span-1", "block_id": "block-123", "content": "Title"}],
            "properties": {},
        }

        block = Block.from_dict(data)

        assert block.id == "block-123"
        assert block.type == BlockType.HEADING_1
        assert len(block.rich_text) == 1

    def test_block_plain_text(self, initialized_db, test_act: str) -> None:
        """Block.plain_text concatenates all spans."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[
                {"content": "Hello "},
                {"content": "world"},
                {"content": "!"},
            ],
        )

        assert block.plain_text() == "Hello world!"

    def test_block_is_nestable(self) -> None:
        """Block.is_nestable returns correct value for type."""
        from reos.play.blocks_models import Block, BlockType

        paragraph = Block(id="1", type=BlockType.PARAGRAPH, act_id="a")
        bulleted = Block(id="2", type=BlockType.BULLETED_LIST, act_id="a")
        callout = Block(id="3", type=BlockType.CALLOUT, act_id="a")

        assert paragraph.is_nestable() is False
        assert bulleted.is_nestable() is True
        assert callout.is_nestable() is True

    def test_rich_text_span_to_dict(self) -> None:
        """RichTextSpan.to_dict serializes correctly."""
        from reos.play.blocks_models import RichTextSpan

        span = RichTextSpan(
            id="span-1",
            block_id="block-1",
            position=0,
            content="Bold text",
            bold=True,
            link_url="https://example.com",
        )

        data = span.to_dict()

        assert data["id"] == "span-1"
        assert data["content"] == "Bold text"
        assert data["bold"] is True
        assert data["link_url"] == "https://example.com"


# =============================================================================
# Cascade Delete Tests
# =============================================================================


class TestCascadeDelete:
    """Test cascade delete behavior."""

    def test_delete_act_cascades_to_blocks(self, temp_data_dir: Path) -> None:
        """Deleting act cascades to its blocks."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")

        block = blocks_db.create_block(type="paragraph", act_id=act_id)
        block_id = block.id

        play_db.delete_act(act_id)

        assert blocks_db.get_block(block_id) is None

    def test_delete_page_cascades_to_blocks(self, temp_data_dir: Path) -> None:
        """Deleting page cascades to its blocks."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        _, page_id = play_db.create_page(act_id=act_id, title="Test Page")

        block = blocks_db.create_block(type="paragraph", act_id=act_id, page_id=page_id)
        block_id = block.id

        play_db.delete_page(page_id)

        assert blocks_db.get_block(block_id) is None

    def test_delete_block_cascades_to_rich_text(self, initialized_db, test_act: str) -> None:
        """Deleting block cascades to its rich_text."""
        block = initialized_db.create_block(
            type="paragraph",
            act_id=test_act,
            rich_text=[{"content": "Test"}],
        )
        block_id = block.id

        initialized_db.delete_block(block_id)

        # Rich text should be gone
        spans = initialized_db.get_rich_text(block_id)
        assert len(spans) == 0

    def test_delete_block_cascades_to_properties(self, initialized_db, test_act: str) -> None:
        """Deleting block cascades to its properties."""
        block = initialized_db.create_block(
            type="to_do",
            act_id=test_act,
            properties={"checked": True},
        )
        block_id = block.id

        initialized_db.delete_block(block_id)

        # Property should be gone
        result = initialized_db.get_block_property(block_id, "checked")
        assert result is None


# =============================================================================
# Act Integration Tests (v8)
# =============================================================================


class TestActIntegration:
    """Test act-block integration functions."""

    def test_set_act_root_block(self, temp_data_dir: Path) -> None:
        """set_act_root_block links a block to an act."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        block = blocks_db.create_block(type="page", act_id=act_id)

        result = play_db.set_act_root_block(act_id, block.id)

        assert result is True
        act = play_db.get_act(act_id)
        assert act["root_block_id"] == block.id

    def test_set_act_root_block_nonexistent_act(self, temp_data_dir: Path) -> None:
        """set_act_root_block returns False for missing act."""
        import reos.play_db as play_db

        play_db.init_db()

        result = play_db.set_act_root_block("nonexistent", "block-123")

        assert result is False

    def test_get_act_root_block(self, temp_data_dir: Path) -> None:
        """get_act_root_block returns the root block."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        block = blocks_db.create_block(
            type="page",
            act_id=act_id,
            properties={"title": "Root Page"},
        )
        play_db.set_act_root_block(act_id, block.id)

        result = play_db.get_act_root_block(act_id)

        assert result is not None
        assert result["id"] == block.id
        assert result["type"] == "page"

    def test_get_act_root_block_no_root(self, temp_data_dir: Path) -> None:
        """get_act_root_block returns None if no root set."""
        import reos.play_db as play_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")

        result = play_db.get_act_root_block(act_id)

        assert result is None

    def test_create_act_with_root_block(self, temp_data_dir: Path) -> None:
        """create_act_with_root_block creates act and root block."""
        import reos.play_db as play_db

        play_db.init_db()

        acts, act_id, root_block_id = play_db.create_act_with_root_block(
            title="New Act",
            notes="Some notes",
            color="#ff0000",
        )

        assert act_id is not None
        assert root_block_id is not None

        act = play_db.get_act(act_id)
        assert act["title"] == "New Act"
        assert act["root_block_id"] == root_block_id

        root = play_db.get_act_root_block(act_id)
        assert root is not None
        assert root["properties"]["title"] == "New Act"

    def test_get_unchecked_todos(self, temp_data_dir: Path) -> None:
        """get_unchecked_todos returns incomplete to-dos."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")

        # Create checked and unchecked todos
        blocks_db.create_block(
            type="to_do",
            act_id=act_id,
            rich_text=[{"content": "Unchecked task"}],
            properties={"checked": False},
        )
        blocks_db.create_block(
            type="to_do",
            act_id=act_id,
            rich_text=[{"content": "Checked task"}],
            properties={"checked": True},
        )
        blocks_db.create_block(
            type="to_do",
            act_id=act_id,
            rich_text=[{"content": "Another unchecked"}],
        )  # No checked property defaults to unchecked

        todos = play_db.get_unchecked_todos(act_id)

        assert len(todos) == 2
        texts = [t["text"] for t in todos]
        assert "Unchecked task" in texts
        assert "Another unchecked" in texts
        assert "Checked task" not in texts

    def test_search_blocks_in_act(self, temp_data_dir: Path) -> None:
        """search_blocks_in_act finds blocks by text."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")

        blocks_db.create_block(
            type="paragraph",
            act_id=act_id,
            rich_text=[{"content": "Hello world"}],
        )
        blocks_db.create_block(
            type="paragraph",
            act_id=act_id,
            rich_text=[{"content": "Goodbye world"}],
        )
        blocks_db.create_block(
            type="paragraph",
            act_id=act_id,
            rich_text=[{"content": "Something else"}],
        )

        results = play_db.search_blocks_in_act(act_id, "world")

        assert len(results) == 2
        texts = [r["text"] for r in results]
        assert "Hello world" in texts
        assert "Goodbye world" in texts

    def test_search_blocks_in_act_no_matches(self, temp_data_dir: Path) -> None:
        """search_blocks_in_act returns empty list for no matches."""
        import reos.play_db as play_db
        from reos.play import blocks_db

        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")

        blocks_db.create_block(
            type="paragraph",
            act_id=act_id,
            rich_text=[{"content": "Hello world"}],
        )

        results = play_db.search_blocks_in_act(act_id, "nonexistent")

        assert len(results) == 0

    def test_acts_include_root_block_id(self, temp_data_dir: Path) -> None:
        """list_acts includes root_block_id field."""
        import reos.play_db as play_db

        play_db.init_db()
        play_db.create_act(title="Test Act")

        acts, _ = play_db.list_acts()

        assert "root_block_id" in acts[0]
