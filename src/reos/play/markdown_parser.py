"""Parse Markdown into blocks.

This module converts Markdown text into a list of Block objects
using the mistletoe library for parsing.
"""

from __future__ import annotations

import re
from typing import Any

import mistletoe
from mistletoe import Document
from mistletoe.block_token import (
    BlockCode,
    CodeFence,
    Heading,
    List,
    ListItem,
    Paragraph,
    ThematicBreak,
)
from mistletoe.span_token import (
    EscapeSequence,
    InlineCode,
    LineBreak,
    Link,
    RawText,
    Strikethrough,
    Strong,
    Emphasis,
)

from .blocks_models import Block, BlockType, RichTextSpan


def parse_markdown(
    markdown: str,
    act_id: str,
    page_id: str | None = None,
) -> list[dict[str, Any]]:
    """Parse Markdown text into block data structures.

    Args:
        markdown: The Markdown text to parse.
        act_id: Act ID for created blocks.
        page_id: Optional page ID for page-level blocks.

    Returns:
        List of block data dictionaries ready for create_block().
    """
    doc = Document(markdown)
    blocks = []
    position = 0

    for token in doc.children:
        block_data = _convert_token(token, act_id, page_id, position)
        if block_data:
            if isinstance(block_data, list):
                for bd in block_data:
                    bd["position"] = position
                    blocks.append(bd)
                    position += 1
            else:
                block_data["position"] = position
                blocks.append(block_data)
                position += 1

    return blocks


def _convert_token(
    token: Any,
    act_id: str,
    page_id: str | None,
    position: int,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Convert a mistletoe token to block data."""
    if isinstance(token, Heading):
        return _convert_heading(token, act_id, page_id)
    elif isinstance(token, Paragraph):
        return _convert_paragraph(token, act_id, page_id)
    elif isinstance(token, (BlockCode, CodeFence)):
        return _convert_code(token, act_id, page_id)
    elif isinstance(token, List):
        return _convert_list(token, act_id, page_id)
    elif isinstance(token, ThematicBreak):
        return _convert_divider(act_id, page_id)
    else:
        # Unknown token type - try to extract text
        if hasattr(token, "children"):
            text = _extract_text(token)
            if text.strip():
                return {
                    "type": BlockType.PARAGRAPH,
                    "act_id": act_id,
                    "page_id": page_id,
                    "rich_text": [{"content": text}],
                }
    return None


def _convert_heading(
    token: Heading,
    act_id: str,
    page_id: str | None,
) -> dict[str, Any]:
    """Convert a heading token."""
    level = token.level
    if level == 1:
        block_type = BlockType.HEADING_1
    elif level == 2:
        block_type = BlockType.HEADING_2
    else:
        block_type = BlockType.HEADING_3

    return {
        "type": block_type,
        "act_id": act_id,
        "page_id": page_id,
        "rich_text": _convert_inline_tokens(token.children),
    }


def _convert_paragraph(
    token: Paragraph,
    act_id: str,
    page_id: str | None,
) -> dict[str, Any]:
    """Convert a paragraph token."""
    # Check for checkbox pattern (to_do block)
    text = _extract_text(token)
    checkbox_match = re.match(r"^\[([xX ])\]\s*(.*)$", text, re.DOTALL)
    if checkbox_match:
        checked = checkbox_match.group(1).lower() == "x"
        content = checkbox_match.group(2)
        return {
            "type": BlockType.TO_DO,
            "act_id": act_id,
            "page_id": page_id,
            "rich_text": [{"content": content}],
            "properties": {"checked": checked},
        }

    return {
        "type": BlockType.PARAGRAPH,
        "act_id": act_id,
        "page_id": page_id,
        "rich_text": _convert_inline_tokens(token.children),
    }


def _convert_code(
    token: BlockCode | CodeFence,
    act_id: str,
    page_id: str | None,
) -> dict[str, Any]:
    """Convert a code block token."""
    language = None
    if isinstance(token, CodeFence) and token.language:
        language = token.language

    # Get code content
    if hasattr(token, "children") and token.children:
        content = _extract_text(token)
    else:
        content = ""

    result = {
        "type": BlockType.CODE,
        "act_id": act_id,
        "page_id": page_id,
        "rich_text": [{"content": content.rstrip("\n")}],
    }

    if language:
        result["properties"] = {"language": language}

    return result


def _convert_list(
    token: List,
    act_id: str,
    page_id: str | None,
) -> list[dict[str, Any]]:
    """Convert a list token into multiple list item blocks."""
    is_ordered = token.start is not None
    blocks = []

    for item in token.children:
        if not isinstance(item, ListItem):
            continue

        # Check if this is a checkbox item
        text = _extract_text(item)
        checkbox_match = re.match(r"^\[([xX ])\]\s*(.*)$", text, re.DOTALL)

        if checkbox_match:
            checked = checkbox_match.group(1).lower() == "x"
            content = checkbox_match.group(2)
            blocks.append({
                "type": BlockType.TO_DO,
                "act_id": act_id,
                "page_id": page_id,
                "rich_text": [{"content": content}],
                "properties": {"checked": checked},
            })
        else:
            block_type = BlockType.NUMBERED_LIST if is_ordered else BlockType.BULLETED_LIST
            blocks.append({
                "type": block_type,
                "act_id": act_id,
                "page_id": page_id,
                "rich_text": _convert_list_item_content(item),
            })

    return blocks


def _convert_list_item_content(item: ListItem) -> list[dict[str, Any]]:
    """Extract rich text from a list item."""
    spans = []
    for child in item.children:
        if isinstance(child, Paragraph):
            spans.extend(_convert_inline_tokens(child.children))
        elif hasattr(child, "children"):
            spans.extend(_convert_inline_tokens(child.children))
    return spans if spans else [{"content": ""}]


def _convert_divider(act_id: str, page_id: str | None) -> dict[str, Any]:
    """Convert a thematic break to a divider block."""
    return {
        "type": BlockType.DIVIDER,
        "act_id": act_id,
        "page_id": page_id,
    }


def _convert_inline_tokens(tokens: list[Any]) -> list[dict[str, Any]]:
    """Convert a list of inline tokens to rich text spans."""
    spans = []

    for token in tokens:
        span_data = _convert_inline_token(token)
        if span_data:
            if isinstance(span_data, list):
                spans.extend(span_data)
            else:
                spans.append(span_data)

    # Merge adjacent spans with same formatting
    return _merge_spans(spans)


def _convert_inline_token(
    token: Any,
    bold: bool = False,
    italic: bool = False,
    strikethrough: bool = False,
    code: bool = False,
    link_url: str | None = None,
) -> dict[str, Any] | list[dict[str, Any]] | None:
    """Convert a single inline token to span data."""
    if isinstance(token, RawText):
        span = {"content": token.content}
        if bold:
            span["bold"] = True
        if italic:
            span["italic"] = True
        if strikethrough:
            span["strikethrough"] = True
        if code:
            span["code"] = True
        if link_url:
            span["link_url"] = link_url
        return span

    elif isinstance(token, Strong):
        # Recursively process children with bold=True
        spans = []
        for child in token.children:
            result = _convert_inline_token(
                child,
                bold=True,
                italic=italic,
                strikethrough=strikethrough,
                code=code,
                link_url=link_url,
            )
            if result:
                if isinstance(result, list):
                    spans.extend(result)
                else:
                    spans.append(result)
        return spans

    elif isinstance(token, Emphasis):
        # Recursively process children with italic=True
        spans = []
        for child in token.children:
            result = _convert_inline_token(
                child,
                bold=bold,
                italic=True,
                strikethrough=strikethrough,
                code=code,
                link_url=link_url,
            )
            if result:
                if isinstance(result, list):
                    spans.extend(result)
                else:
                    spans.append(result)
        return spans

    elif isinstance(token, Strikethrough):
        spans = []
        for child in token.children:
            result = _convert_inline_token(
                child,
                bold=bold,
                italic=italic,
                strikethrough=True,
                code=code,
                link_url=link_url,
            )
            if result:
                if isinstance(result, list):
                    spans.extend(result)
                else:
                    spans.append(result)
        return spans

    elif isinstance(token, InlineCode):
        return {
            "content": token.children[0].content if token.children else "",
            "code": True,
        }

    elif isinstance(token, Link):
        spans = []
        url = token.target
        for child in token.children:
            result = _convert_inline_token(
                child,
                bold=bold,
                italic=italic,
                strikethrough=strikethrough,
                code=code,
                link_url=url,
            )
            if result:
                if isinstance(result, list):
                    spans.extend(result)
                else:
                    spans.append(result)
        return spans

    elif isinstance(token, (LineBreak, EscapeSequence)):
        if isinstance(token, LineBreak):
            return {"content": "\n"}
        elif hasattr(token, "children") and token.children:
            return {"content": token.children[0].content}
        return None

    elif hasattr(token, "children"):
        # Generic handling for tokens with children
        spans = []
        for child in token.children:
            result = _convert_inline_token(
                child,
                bold=bold,
                italic=italic,
                strikethrough=strikethrough,
                code=code,
                link_url=link_url,
            )
            if result:
                if isinstance(result, list):
                    spans.extend(result)
                else:
                    spans.append(result)
        return spans

    return None


def _extract_text(token: Any) -> str:
    """Extract plain text from a token."""
    if isinstance(token, RawText):
        return token.content
    elif hasattr(token, "children"):
        return "".join(_extract_text(child) for child in token.children)
    return ""


def _merge_spans(spans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge adjacent spans with identical formatting."""
    if not spans:
        return spans

    merged = []
    current = None

    for span in spans:
        if current is None:
            current = span.copy()
        elif _same_formatting(current, span):
            # Merge content
            current["content"] += span["content"]
        else:
            merged.append(current)
            current = span.copy()

    if current:
        merged.append(current)

    return merged


def _same_formatting(span1: dict[str, Any], span2: dict[str, Any]) -> bool:
    """Check if two spans have the same formatting."""
    format_keys = ["bold", "italic", "strikethrough", "code", "underline", "color", "background_color", "link_url"]
    for key in format_keys:
        if span1.get(key) != span2.get(key):
            return False
    return True
