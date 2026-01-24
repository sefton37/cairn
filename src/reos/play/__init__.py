"""Block-based knowledge repository for The Play.

This module provides a Notion-inspired block system for rich content storage
in SQLite, integrating with existing Acts/Scenes/Pages.

Key components:
- blocks_models: Block, RichTextSpan, BlockType dataclasses
- blocks_db: CRUD operations for blocks and rich text
- blocks_tree: Tree operations (move, reorder, ancestors)
- markdown_parser: Markdown -> Blocks conversion
- markdown_renderer: Blocks -> Markdown export
"""

from .blocks_models import Block, BlockType, RichTextSpan
from .blocks_tree import (
    get_ancestors,
    get_descendants,
    get_siblings,
    move_block,
    reorder_siblings,
    create_scene_block,
    validate_scene_block,
)
from .markdown_parser import parse_markdown
from .markdown_renderer import render_markdown, get_scene_snippet, render_scene_block

__all__ = [
    "Block",
    "BlockType",
    "RichTextSpan",
    "get_ancestors",
    "get_descendants",
    "get_siblings",
    "move_block",
    "reorder_siblings",
    "create_scene_block",
    "validate_scene_block",
    "parse_markdown",
    "render_markdown",
    "get_scene_snippet",
    "render_scene_block",
]
