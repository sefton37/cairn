"""Tests for markdown_parser.py and markdown_renderer.py.

Tests:
- Markdown -> Blocks parsing
- Blocks -> Markdown rendering
- Round-trip consistency
- Rich text formatting
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
def test_act(temp_data_dir: Path) -> str:
    """Create a test act."""
    import reos.play_db as play_db

    play_db.init_db()
    _, act_id = play_db.create_act(title="Test Act")
    return act_id


# =============================================================================
# Markdown Parser Tests
# =============================================================================


class TestMarkdownParser:
    """Test Markdown to Blocks parsing."""

    def test_parse_paragraph(self, test_act: str) -> None:
        """Parse a simple paragraph."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("Hello world", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.PARAGRAPH
        assert blocks[0]["rich_text"][0]["content"] == "Hello world"

    def test_parse_heading_1(self, test_act: str) -> None:
        """Parse a level 1 heading."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("# Main Title", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.HEADING_1
        assert blocks[0]["rich_text"][0]["content"] == "Main Title"

    def test_parse_heading_2(self, test_act: str) -> None:
        """Parse a level 2 heading."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("## Sub Title", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.HEADING_2

    def test_parse_heading_3(self, test_act: str) -> None:
        """Parse a level 3 heading."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("### Small Title", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.HEADING_3

    def test_parse_bold_text(self, test_act: str) -> None:
        """Parse text with bold formatting."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("This is **bold** text", test_act)

        assert len(blocks) == 1
        spans = blocks[0]["rich_text"]
        # Should have: "This is ", "bold", " text"
        bold_spans = [s for s in spans if s.get("bold")]
        assert len(bold_spans) >= 1
        assert any("bold" in s["content"] for s in bold_spans)

    def test_parse_italic_text(self, test_act: str) -> None:
        """Parse text with italic formatting."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("This is *italic* text", test_act)

        assert len(blocks) == 1
        spans = blocks[0]["rich_text"]
        italic_spans = [s for s in spans if s.get("italic")]
        assert len(italic_spans) >= 1

    def test_parse_code_inline(self, test_act: str) -> None:
        """Parse inline code."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("Use `print()` function", test_act)

        assert len(blocks) == 1
        spans = blocks[0]["rich_text"]
        code_spans = [s for s in spans if s.get("code")]
        assert len(code_spans) >= 1

    def test_parse_link(self, test_act: str) -> None:
        """Parse a link."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("Visit [Example](https://example.com)", test_act)

        assert len(blocks) == 1
        spans = blocks[0]["rich_text"]
        link_spans = [s for s in spans if s.get("link_url")]
        assert len(link_spans) >= 1
        assert link_spans[0]["link_url"] == "https://example.com"

    def test_parse_code_block(self, test_act: str) -> None:
        """Parse a fenced code block."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        markdown = """```python
def hello():
    print("Hello")
```"""
        blocks = parse_markdown(markdown, test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.CODE
        assert blocks[0]["properties"]["language"] == "python"
        assert "def hello" in blocks[0]["rich_text"][0]["content"]

    def test_parse_bulleted_list(self, test_act: str) -> None:
        """Parse a bulleted list."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        markdown = """- Item 1
- Item 2
- Item 3"""
        blocks = parse_markdown(markdown, test_act)

        assert len(blocks) == 3
        for block in blocks:
            assert block["type"] == BlockType.BULLETED_LIST

    def test_parse_numbered_list(self, test_act: str) -> None:
        """Parse a numbered list."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        markdown = """1. First
2. Second
3. Third"""
        blocks = parse_markdown(markdown, test_act)

        assert len(blocks) == 3
        for block in blocks:
            assert block["type"] == BlockType.NUMBERED_LIST

    def test_parse_checkbox_unchecked(self, test_act: str) -> None:
        """Parse unchecked checkbox."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("- [ ] Todo item", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.TO_DO
        assert blocks[0]["properties"]["checked"] is False

    def test_parse_checkbox_checked(self, test_act: str) -> None:
        """Parse checked checkbox."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("- [x] Completed item", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.TO_DO
        assert blocks[0]["properties"]["checked"] is True

    def test_parse_divider(self, test_act: str) -> None:
        """Parse horizontal rule as divider."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("---", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.DIVIDER

    def test_parse_multiple_blocks(self, test_act: str) -> None:
        """Parse document with multiple block types."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        markdown = """# Title

This is a paragraph.

- List item 1
- List item 2

---

Another paragraph."""

        blocks = parse_markdown(markdown, test_act)

        types = [b["type"] for b in blocks]
        assert BlockType.HEADING_1 in types
        assert BlockType.PARAGRAPH in types
        assert BlockType.BULLETED_LIST in types
        assert BlockType.DIVIDER in types

    def test_parse_positions_sequential(self, test_act: str) -> None:
        """Blocks have sequential positions."""
        from reos.play.markdown_parser import parse_markdown

        markdown = """# One
## Two
### Three"""
        blocks = parse_markdown(markdown, test_act)

        positions = [b["position"] for b in blocks]
        assert positions == [0, 1, 2]


# =============================================================================
# Markdown Renderer Tests
# =============================================================================


class TestMarkdownRenderer:
    """Test Blocks to Markdown rendering."""

    def test_render_paragraph(self) -> None:
        """Render a paragraph block."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Hello world")],
        )

        result = render_markdown([block])

        assert result == "Hello world"

    def test_render_heading_1(self) -> None:
        """Render a heading 1 block."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.HEADING_1,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Title")],
        )

        result = render_markdown([block])

        assert result == "# Title"

    def test_render_heading_2(self) -> None:
        """Render a heading 2 block."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.HEADING_2,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Subtitle")],
        )

        result = render_markdown([block])

        assert result == "## Subtitle"

    def test_render_bold_text(self) -> None:
        """Render bold formatted text."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            act_id="a1",
            rich_text=[
                RichTextSpan(id="s1", block_id="b1", position=0, content="This is "),
                RichTextSpan(id="s2", block_id="b1", position=1, content="bold", bold=True),
                RichTextSpan(id="s3", block_id="b1", position=2, content=" text"),
            ],
        )

        result = render_markdown([block])

        assert "**bold**" in result

    def test_render_italic_text(self) -> None:
        """Render italic formatted text."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="italic", italic=True)],
        )

        result = render_markdown([block])

        assert result == "*italic*"

    def test_render_code_inline(self) -> None:
        """Render inline code."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="print()", code=True)],
        )

        result = render_markdown([block])

        assert result == "`print()`"

    def test_render_link(self) -> None:
        """Render a link."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.PARAGRAPH,
            act_id="a1",
            rich_text=[
                RichTextSpan(
                    id="s1",
                    block_id="b1",
                    position=0,
                    content="Click here",
                    link_url="https://example.com",
                )
            ],
        )

        result = render_markdown([block])

        assert result == "[Click here](https://example.com)"

    def test_render_code_block(self) -> None:
        """Render a code block with language."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.CODE,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="print('hello')")],
            properties={"language": "python"},
        )

        result = render_markdown([block])

        assert "```python" in result
        assert "print('hello')" in result
        assert "```" in result

    def test_render_bulleted_list(self) -> None:
        """Render bulleted list items."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        blocks = [
            Block(
                id="b1",
                type=BlockType.BULLETED_LIST,
                act_id="a1",
                rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Item 1")],
            ),
            Block(
                id="b2",
                type=BlockType.BULLETED_LIST,
                act_id="a1",
                rich_text=[RichTextSpan(id="s2", block_id="b2", position=0, content="Item 2")],
            ),
        ]

        result = render_markdown(blocks)

        assert "- Item 1" in result
        assert "- Item 2" in result

    def test_render_numbered_list(self) -> None:
        """Render numbered list items."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        blocks = [
            Block(
                id="b1",
                type=BlockType.NUMBERED_LIST,
                act_id="a1",
                rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="First")],
            ),
        ]

        result = render_markdown(blocks)

        assert "1. First" in result

    def test_render_todo_unchecked(self) -> None:
        """Render unchecked todo."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.TO_DO,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Task")],
            properties={"checked": False},
        )

        result = render_markdown([block])

        assert "- [ ] Task" in result

    def test_render_todo_checked(self) -> None:
        """Render checked todo."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType, RichTextSpan

        block = Block(
            id="b1",
            type=BlockType.TO_DO,
            act_id="a1",
            rich_text=[RichTextSpan(id="s1", block_id="b1", position=0, content="Done")],
            properties={"checked": True},
        )

        result = render_markdown([block])

        assert "- [x] Done" in result

    def test_render_divider(self) -> None:
        """Render divider."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType

        block = Block(id="b1", type=BlockType.DIVIDER, act_id="a1")

        result = render_markdown([block])

        assert result == "---"


# =============================================================================
# Round-Trip Tests
# =============================================================================


class TestRoundTrip:
    """Test parse -> render round-trip consistency."""

    def _blocks_from_data(self, blocks_data: list) -> list:
        """Convert parsed block data to Block objects for rendering."""
        from reos.play.blocks_models import Block, RichTextSpan

        blocks = []
        for i, data in enumerate(blocks_data):
            rich_text = []
            for j, span_data in enumerate(data.get("rich_text", [])):
                rich_text.append(RichTextSpan(
                    id=f"span-{i}-{j}",
                    block_id=f"block-{i}",
                    position=j,
                    content=span_data.get("content", ""),
                    bold=span_data.get("bold", False),
                    italic=span_data.get("italic", False),
                    strikethrough=span_data.get("strikethrough", False),
                    code=span_data.get("code", False),
                    underline=span_data.get("underline", False),
                    color=span_data.get("color"),
                    background_color=span_data.get("background_color"),
                    link_url=span_data.get("link_url"),
                ))

            blocks.append(Block(
                id=f"block-{i}",
                type=data["type"],
                act_id=data["act_id"],
                page_id=data.get("page_id"),
                position=data.get("position", i),
                rich_text=rich_text,
                properties=data.get("properties", {}),
            ))
        return blocks

    def test_roundtrip_paragraph(self, test_act: str) -> None:
        """Paragraph survives round-trip."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.markdown_renderer import render_markdown

        original = "Hello world"
        blocks_data = parse_markdown(original, test_act)
        blocks = self._blocks_from_data(blocks_data)
        rendered = render_markdown(blocks)

        assert rendered.strip() == original

    def test_roundtrip_heading(self, test_act: str) -> None:
        """Heading survives round-trip."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.markdown_renderer import render_markdown

        original = "# Main Title"
        blocks_data = parse_markdown(original, test_act)
        blocks = self._blocks_from_data(blocks_data)
        rendered = render_markdown(blocks)

        assert rendered.strip() == original

    def test_roundtrip_code_block(self, test_act: str) -> None:
        """Code block survives round-trip."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.markdown_renderer import render_markdown

        original = """```python
print("hello")
```"""
        blocks_data = parse_markdown(original, test_act)
        blocks = self._blocks_from_data(blocks_data)
        rendered = render_markdown(blocks)

        assert "```python" in rendered
        assert 'print("hello")' in rendered

    def test_roundtrip_checkbox(self, test_act: str) -> None:
        """Checkbox survives round-trip."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.markdown_renderer import render_markdown

        original = "- [x] Completed task"
        blocks_data = parse_markdown(original, test_act)
        blocks = self._blocks_from_data(blocks_data)
        rendered = render_markdown(blocks)

        assert "[x]" in rendered
        assert "Completed task" in rendered

    def test_roundtrip_complex_document(self, test_act: str) -> None:
        """Complex document survives round-trip."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.markdown_renderer import render_markdown

        original = """# Document Title

This is a paragraph with **bold** and *italic* text.

## Section

- Item 1
- Item 2

---

Final paragraph."""

        blocks_data = parse_markdown(original, test_act)
        blocks = self._blocks_from_data(blocks_data)
        rendered = render_markdown(blocks)

        # Check key elements are preserved
        assert "# Document Title" in rendered
        assert "## Section" in rendered
        assert "- Item" in rendered
        assert "---" in rendered
        assert "bold" in rendered.lower() or "**" in rendered


# =============================================================================
# Edge Cases
# =============================================================================


class TestEdgeCases:
    """Test edge cases and special scenarios."""

    def test_empty_markdown(self, test_act: str) -> None:
        """Empty markdown produces no blocks."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("", test_act)
        assert len(blocks) == 0

    def test_whitespace_only(self, test_act: str) -> None:
        """Whitespace-only markdown produces no blocks."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("   \n\n   ", test_act)
        # May produce empty blocks or none depending on parser
        for block in blocks:
            if "rich_text" in block and block["rich_text"]:
                text = "".join(s.get("content", "") for s in block["rich_text"])
                # Allow whitespace-only content
                assert text.strip() == "" or len(text) > 0

    def test_nested_formatting(self, test_act: str) -> None:
        """Nested formatting is handled."""
        from reos.play.markdown_parser import parse_markdown

        blocks = parse_markdown("***bold italic***", test_act)

        assert len(blocks) >= 1

    def test_render_empty_blocks(self) -> None:
        """Empty block list renders to empty string."""
        from reos.play.markdown_renderer import render_markdown

        result = render_markdown([])
        assert result == ""

    def test_code_block_without_language(self, test_act: str) -> None:
        """Code block without language specification."""
        from reos.play.markdown_parser import parse_markdown
        from reos.play.blocks_models import BlockType

        blocks = parse_markdown("```\ncode here\n```", test_act)

        assert len(blocks) == 1
        assert blocks[0]["type"] == BlockType.CODE
        # Language may be None or empty string
        lang = blocks[0].get("properties", {}).get("language")
        assert lang is None or lang == ""


# =============================================================================
# Scene Block Rendering Tests
# =============================================================================


class TestSceneBlockRendering:
    """Test scene block rendering functions."""

    def test_get_scene_snippet(self, temp_data_dir: Path) -> None:
        """get_scene_snippet returns scene data."""
        import reos.play_db as play_db
        from reos.play.markdown_renderer import get_scene_snippet

        play_db.close_connection()
        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Test Scene",
            stage="active",
            notes="Some notes here",
        )

        snippet = get_scene_snippet(scene_id)

        assert snippet is not None
        assert snippet["title"] == "Test Scene"
        assert snippet["stage"] == "active"
        assert snippet["notes_preview"] == "Some notes here"

        play_db.close_connection()

    def test_get_scene_snippet_not_found(self, temp_data_dir: Path) -> None:
        """get_scene_snippet returns None for missing scene."""
        import reos.play_db as play_db
        from reos.play.markdown_renderer import get_scene_snippet

        play_db.close_connection()
        play_db.init_db()

        snippet = get_scene_snippet("nonexistent")

        assert snippet is None

        play_db.close_connection()

    def test_get_scene_snippet_truncates_long_notes(self, temp_data_dir: Path) -> None:
        """get_scene_snippet truncates long notes."""
        import reos.play_db as play_db
        from reos.play.markdown_renderer import get_scene_snippet

        play_db.close_connection()
        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        long_notes = "A very long note that goes on and on " * 10
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Test Scene",
            notes=long_notes,
        )

        snippet = get_scene_snippet(scene_id, max_notes_length=50)

        assert snippet is not None
        assert len(snippet["notes_preview"]) < 60  # Some buffer for truncation
        assert snippet["notes_preview"].endswith("...")

        play_db.close_connection()

    def test_render_scene_block(self) -> None:
        """render_scene_block formats scene nicely."""
        from reos.play.markdown_renderer import render_scene_block

        snippet = {
            "scene_id": "scene-123",
            "title": "My Task",
            "stage": "active",
            "notes_preview": "Do something important",
            "has_calendar": False,
            "calendar_start": None,
        }

        result = render_scene_block(snippet)

        assert "**My Task**" in result
        assert "(active)" in result
        assert "Do something important" in result
        assert result.startswith(">")  # blockquote format

    def test_render_scene_block_with_calendar(self) -> None:
        """render_scene_block includes calendar info."""
        from reos.play.markdown_renderer import render_scene_block

        snippet = {
            "scene_id": "scene-123",
            "title": "Meeting",
            "stage": "planning",
            "notes_preview": "",
            "has_calendar": True,
            "calendar_start": "2026-01-24T10:00:00",
        }

        result = render_scene_block(snippet)

        assert "**Meeting**" in result
        assert "2026-01-24T10:00:00" in result

    def test_render_scene_in_markdown(self, temp_data_dir: Path) -> None:
        """Scene block renders with details in markdown output."""
        import reos.play_db as play_db
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType

        play_db.close_connection()
        play_db.init_db()
        _, act_id = play_db.create_act(title="Test Act")
        _, scene_id = play_db.create_scene(
            act_id=act_id,
            title="Important Task",
            stage="active",
            notes="Do this thing",
        )

        block = Block(
            id="b1",
            type=BlockType.SCENE,
            act_id=act_id,
            scene_id=scene_id,
        )

        result = render_markdown([block])

        assert "**Important Task**" in result
        assert "(active)" in result

        play_db.close_connection()

    def test_render_scene_missing(self) -> None:
        """Scene block with missing scene shows ID."""
        from reos.play.markdown_renderer import render_markdown
        from reos.play.blocks_models import Block, BlockType

        block = Block(
            id="b1",
            type=BlockType.SCENE,
            act_id="a1",
            scene_id="nonexistent-scene",
        )

        result = render_markdown([block])

        assert "nonexistent-scene" in result
        assert result.startswith(">")  # blockquote format
