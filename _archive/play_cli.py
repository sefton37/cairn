#!/usr/bin/env python3
"""CLI demo for the block-based knowledge repository.

This script provides an interactive way to test the block system.

Usage:
    python -m reos.play_cli [command] [args...]

Commands:
    acts                    List all acts
    create-act TITLE        Create a new act
    pages ACT_ID            List pages in an act
    create-page ACT_ID TITLE  Create a new page
    blocks PAGE_ID          List blocks in a page
    add-block ACT_ID TYPE TEXT  Add a block
    search ACT_ID QUERY     Search blocks
    todos ACT_ID            Show unchecked todos
    export PAGE_ID          Export page as markdown
"""

from __future__ import annotations

import sys
from typing import Any


def main() -> int:
    """Main CLI entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        return 0

    command = sys.argv[1]

    try:
        if command == "acts":
            return cmd_acts()
        elif command == "create-act":
            if len(sys.argv) < 3:
                print("Usage: create-act TITLE")
                return 1
            return cmd_create_act(sys.argv[2])
        elif command == "pages":
            if len(sys.argv) < 3:
                print("Usage: pages ACT_ID")
                return 1
            return cmd_pages(sys.argv[2])
        elif command == "create-page":
            if len(sys.argv) < 4:
                print("Usage: create-page ACT_ID TITLE")
                return 1
            return cmd_create_page(sys.argv[2], sys.argv[3])
        elif command == "blocks":
            if len(sys.argv) < 3:
                print("Usage: blocks PAGE_ID")
                return 1
            return cmd_blocks(sys.argv[2])
        elif command == "add-block":
            if len(sys.argv) < 5:
                print("Usage: add-block ACT_ID TYPE TEXT")
                return 1
            return cmd_add_block(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]))
        elif command == "search":
            if len(sys.argv) < 4:
                print("Usage: search ACT_ID QUERY")
                return 1
            return cmd_search(sys.argv[2], " ".join(sys.argv[3:]))
        elif command == "todos":
            if len(sys.argv) < 3:
                print("Usage: todos ACT_ID")
                return 1
            return cmd_todos(sys.argv[2])
        elif command == "export":
            if len(sys.argv) < 3:
                print("Usage: export PAGE_ID")
                return 1
            return cmd_export(sys.argv[2])
        elif command == "demo":
            return cmd_demo()
        elif command in ("-h", "--help", "help"):
            print(__doc__)
            return 0
        else:
            print(f"Unknown command: {command}")
            print(__doc__)
            return 1

    except Exception as e:
        print(f"Error: {e}")
        return 1


def cmd_acts() -> int:
    """List all acts."""
    from . import play_db

    play_db.init_db()
    acts, active_id = play_db.list_acts()

    print(f"\n{'ID':<20} {'Title':<30} {'Active':<10} {'Root Block'}")
    print("-" * 75)
    for act in acts:
        active = "  *" if act["act_id"] == active_id else ""
        root = act.get("root_block_id", "-") or "-"
        print(f"{act['act_id']:<20} {act['title']:<30} {active:<10} {root}")

    print(f"\nTotal: {len(acts)} acts")
    return 0


def cmd_create_act(title: str) -> int:
    """Create a new act."""
    from . import play_db

    play_db.init_db()
    acts, act_id = play_db.create_act(title=title)

    print(f"Created act: {act_id}")
    print(f"Title: {title}")
    return 0


def cmd_pages(act_id: str) -> int:
    """List pages in an act."""
    from . import play_db

    play_db.init_db()
    pages = play_db.list_pages(act_id)

    print(f"\n{'ID':<20} {'Title':<40} {'Icon'}")
    print("-" * 70)
    for page in pages:
        icon = page.get("icon") or "-"
        print(f"{page['page_id']:<20} {page['title']:<40} {icon}")

    print(f"\nTotal: {len(pages)} pages in {act_id}")
    return 0


def cmd_create_page(act_id: str, title: str) -> int:
    """Create a new page."""
    from . import play_db

    play_db.init_db()
    _, page_id = play_db.create_page(act_id=act_id, title=title)

    print(f"Created page: {page_id}")
    print(f"Title: {title}")
    print(f"In act: {act_id}")
    return 0


def cmd_blocks(page_id: str) -> int:
    """List blocks in a page."""
    from .play import blocks_db

    blocks = blocks_db.get_page_blocks(page_id, recursive=True)

    def print_block(block: Any, indent: int = 0) -> None:
        prefix = "  " * indent
        text = block.plain_text()[:50] + ("..." if len(block.plain_text()) > 50 else "")
        print(f"{prefix}{block.type.value}: {text or '(empty)'}")
        for child in block.children:
            print_block(child, indent + 1)

    print(f"\nBlocks in page {page_id}:")
    print("-" * 60)
    for block in blocks:
        print_block(block)

    print(f"\nTotal: {len(blocks)} root blocks")
    return 0


def cmd_add_block(act_id: str, block_type: str, text: str) -> int:
    """Add a block."""
    from .play import blocks_db

    block = blocks_db.create_text_block(
        type=block_type,
        act_id=act_id,
        text=text,
    )

    print(f"Created block: {block.id}")
    print(f"Type: {block.type.value}")
    print(f"Text: {text}")
    return 0


def cmd_search(act_id: str, query: str) -> int:
    """Search blocks in an act."""
    from . import play_db

    play_db.init_db()
    results = play_db.search_blocks_in_act(act_id, query)

    print(f"\nSearch results for '{query}' in {act_id}:")
    print("-" * 60)
    for result in results:
        text = result["text"][:60] + ("..." if len(result["text"]) > 60 else "")
        print(f"[{result['type']}] {text}")

    print(f"\nFound: {len(results)} blocks")
    return 0


def cmd_todos(act_id: str) -> int:
    """Show unchecked todos in an act."""
    from . import play_db

    play_db.init_db()
    todos = play_db.get_unchecked_todos(act_id)

    print(f"\nUnchecked to-dos in {act_id}:")
    print("-" * 60)
    for todo in todos:
        print(f"[ ] {todo['text']}")

    print(f"\nTotal: {len(todos)} unchecked items")
    return 0


def cmd_export(page_id: str) -> int:
    """Export a page as markdown."""
    from .play import blocks_db
    from .play.markdown_renderer import render_markdown

    blocks = blocks_db.get_page_blocks(page_id, recursive=True)
    markdown = render_markdown(blocks)

    print(markdown)
    return 0


def cmd_demo() -> int:
    """Run a demo of the block system."""
    from . import play_db
    from .play import blocks_db
    from .play.markdown_renderer import render_markdown

    print("=" * 60)
    print("Block System Demo")
    print("=" * 60)

    # Initialize
    play_db.init_db()

    # Create an act
    print("\n1. Creating a demo act...")
    acts, act_id = play_db.create_act(title="Demo Act")
    print(f"   Created act: {act_id}")

    # Create a page
    print("\n2. Creating a demo page...")
    _, page_id = play_db.create_page(act_id=act_id, title="Demo Page")
    print(f"   Created page: {page_id}")

    # Add blocks
    print("\n3. Adding blocks...")
    blocks_db.create_text_block(
        type="heading_1",
        act_id=act_id,
        page_id=page_id,
        text="Welcome to the Block System",
    )
    blocks_db.create_text_block(
        type="paragraph",
        act_id=act_id,
        page_id=page_id,
        text="This is a demo of the Notion-style block editor.",
    )
    blocks_db.create_text_block(
        type="to_do",
        act_id=act_id,
        page_id=page_id,
        text="Learn how to use blocks",
        checked=False,
    )
    blocks_db.create_text_block(
        type="to_do",
        act_id=act_id,
        page_id=page_id,
        text="Create rich content",
        checked=True,
    )
    blocks_db.create_text_block(
        type="code",
        act_id=act_id,
        page_id=page_id,
        text="print('Hello, blocks!')",
        language="python",
    )
    print("   Added 5 blocks")

    # Show blocks
    print("\n4. Fetching page content...")
    blocks = blocks_db.get_page_blocks(page_id)
    print(f"   Retrieved {len(blocks)} blocks")

    # Export as markdown
    print("\n5. Exporting as markdown:")
    print("-" * 40)
    markdown = render_markdown(blocks)
    print(markdown)
    print("-" * 40)

    # Show unchecked todos
    print("\n6. Unchecked to-dos:")
    todos = play_db.get_unchecked_todos(act_id)
    for todo in todos:
        print(f"   [ ] {todo['text']}")

    # Search
    print("\n7. Searching for 'block':")
    results = play_db.search_blocks_in_act(act_id, "block")
    for result in results:
        print(f"   Found: {result['text'][:50]}...")

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
