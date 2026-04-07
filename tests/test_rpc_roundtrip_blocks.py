"""RPC round-trip integration tests for Blocks through the real dispatcher with a real DB.

Tests pass through _handle_jsonrpc_request using a temporary SQLite database — no mocks.
"""

from __future__ import annotations

import pytest


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def rpc_db(tmp_path, monkeypatch, isolated_db_singleton):
    """Isolated DB for round-trip RPC tests."""
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))
    from cairn.db import get_db
    from cairn import play_db

    play_db.close_connection()  # force reconnect with new env
    db = get_db()
    yield db
    play_db.close_connection()


@pytest.fixture
def act_id(rpc_db) -> str:
    """Create a test act and return its ID."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Test Act"},
    )
    return resp["result"]["created_act_id"]


# =============================================================================
# RPC helper
# =============================================================================


def _rpc(db, *, req_id: int, method: str, params: dict | None = None) -> dict:
    import cairn.ui_rpc_server as ui

    req: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    req["params"] = p
    resp = ui._handle_jsonrpc_request(db, req)
    assert resp is not None
    return resp


# =============================================================================
# Block CRUD
# =============================================================================


def test_create_block_and_get(rpc_db, act_id: str) -> None:
    """Creating a paragraph block then getting by ID returns the correct type and act_id."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )

    assert "result" in create_resp
    block = create_resp["result"]["block"]
    block_id = block["id"]
    assert block["type"] == "paragraph"
    assert block["act_id"] == act_id

    get_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/get",
        params={"block_id": block_id},
    )

    assert "result" in get_resp
    fetched = get_resp["result"]["block"]
    assert fetched["id"] == block_id
    assert fetched["type"] == "paragraph"
    assert fetched["act_id"] == act_id


def test_create_block_with_rich_text(rpc_db, act_id: str) -> None:
    """Creating a block with rich_text spans preserves the content on retrieval."""
    spans = [{"content": "Hello world", "bold": False, "italic": False, "code": False}]

    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "rich_text": spans},
    )

    assert "result" in create_resp
    block_id = create_resp["result"]["block"]["id"]

    rt_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/rich_text/get",
        params={"block_id": block_id},
    )

    assert "result" in rt_resp
    returned_spans = rt_resp["result"]["spans"]
    assert len(returned_spans) == 1
    assert returned_spans[0]["content"] == "Hello world"


def test_list_blocks_by_act(rpc_db, act_id: str) -> None:
    """Creating multiple blocks in the same act returns all of them via blocks/list."""
    _rpc(rpc_db, req_id=1, method="blocks/create", params={"type": "paragraph", "act_id": act_id})
    _rpc(rpc_db, req_id=2, method="blocks/create", params={"type": "heading_1", "act_id": act_id})
    _rpc(rpc_db, req_id=3, method="blocks/create", params={"type": "paragraph", "act_id": act_id})

    list_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/list",
        params={"act_id": act_id},
    )

    assert "result" in list_resp
    blocks = list_resp["result"]["blocks"]
    assert len(blocks) == 3


def test_update_block(rpc_db, act_id: str) -> None:
    """Updating a block's rich_text via blocks/update is reflected in a subsequent get."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    new_spans = [{"content": "Updated content", "bold": True, "italic": False, "code": False}]
    update_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/update",
        params={"block_id": block_id, "rich_text": new_spans},
    )

    assert "result" in update_resp
    assert update_resp["result"]["block"]["id"] == block_id

    rt_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/rich_text/get",
        params={"block_id": block_id},
    )
    spans = rt_resp["result"]["spans"]
    assert len(spans) == 1
    assert spans[0]["content"] == "Updated content"


def test_delete_block(rpc_db, act_id: str) -> None:
    """Deleting a block causes blocks/get to return an error for that block_id."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    delete_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/delete",
        params={"block_id": block_id},
    )

    assert "result" in delete_resp
    assert delete_resp["result"]["deleted"] is True

    get_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/get",
        params={"block_id": block_id},
    )

    assert "error" in get_resp


def test_create_child_block(rpc_db, act_id: str) -> None:
    """Creating a child block stores the parent_id relationship correctly."""
    # bulleted_list is a nestable type that supports children
    parent_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id},
    )["result"]["block"]["id"]

    child_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "parent_id": parent_id},
    )

    assert "result" in child_resp
    child = child_resp["result"]["block"]
    assert child["parent_id"] == parent_id


# =============================================================================
# Rich Text
# =============================================================================


def test_rich_text_set_and_get(rpc_db, act_id: str) -> None:
    """Setting rich_text via blocks/rich_text/set and getting it back returns identical spans."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    spans = [{"content": "Hello", "bold": False, "italic": False, "code": False}]
    set_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/rich_text/set",
        params={"block_id": block_id, "spans": spans},
    )

    assert "result" in set_resp

    get_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/rich_text/get",
        params={"block_id": block_id},
    )

    assert "result" in get_resp
    returned = get_resp["result"]["spans"]
    assert len(returned) == 1
    assert returned[0]["content"] == "Hello"


def test_rich_text_with_formatting(rpc_db, act_id: str) -> None:
    """Bold, italic, and code formatting round-trip correctly through the RPC layer."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    spans = [
        {"content": "bold text", "bold": True, "italic": False, "code": False},
        {"content": "italic text", "bold": False, "italic": True, "code": False},
        {"content": "code text", "bold": False, "italic": False, "code": True},
    ]
    _rpc(
        rpc_db,
        req_id=2,
        method="blocks/rich_text/set",
        params={"block_id": block_id, "spans": spans},
    )

    get_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/rich_text/get",
        params={"block_id": block_id},
    )

    returned = get_resp["result"]["spans"]
    assert len(returned) == 3
    assert returned[0]["bold"] is True
    assert returned[1]["italic"] is True
    assert returned[2]["code"] is True


# =============================================================================
# Properties
# =============================================================================


def test_property_set_and_get(rpc_db, act_id: str) -> None:
    """Setting a string property via blocks/property/set reads back the same value."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    _rpc(
        rpc_db,
        req_id=2,
        method="blocks/property/set",
        params={"block_id": block_id, "key": "color", "value": "red"},
    )

    get_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/property/get",
        params={"block_id": block_id, "key": "color"},
    )

    assert "result" in get_resp
    assert get_resp["result"]["key"] == "color"
    assert get_resp["result"]["value"] == "red"


def test_property_delete(rpc_db, act_id: str) -> None:
    """Deleting a property causes blocks/property/get to return None for that key."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    _rpc(
        rpc_db,
        req_id=2,
        method="blocks/property/set",
        params={"block_id": block_id, "key": "temp_key", "value": "temp_val"},
    )

    delete_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/property/delete",
        params={"block_id": block_id, "key": "temp_key"},
    )

    assert "result" in delete_resp

    get_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/property/get",
        params={"block_id": block_id, "key": "temp_key"},
    )

    assert "result" in get_resp
    assert get_resp["result"]["value"] is None


def test_property_with_json_value(rpc_db, act_id: str) -> None:
    """Setting a dict property stores and retrieves it intact."""
    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id},
    )["result"]["block"]["id"]

    json_value = {"level": 2, "collapsed": True, "tags": ["a", "b"]}
    _rpc(
        rpc_db,
        req_id=2,
        method="blocks/property/set",
        params={"block_id": block_id, "key": "metadata", "value": json_value},
    )

    get_resp = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/property/get",
        params={"block_id": block_id, "key": "metadata"},
    )

    assert "result" in get_resp
    assert get_resp["result"]["value"] == json_value


# =============================================================================
# Tree Operations
# =============================================================================


def test_blocks_move(rpc_db, act_id: str) -> None:
    """Moving a child block from parent1 to parent2 updates its parent_id."""
    # Use bulleted_list (nestable) as parents so they accept children
    parent1_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id},
    )["result"]["block"]["id"]

    parent2_id = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id},
    )["result"]["block"]["id"]

    child_id = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "parent_id": parent1_id},
    )["result"]["block"]["id"]

    move_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/move",
        params={"block_id": child_id, "new_parent_id": parent2_id},
    )

    assert "result" in move_resp
    moved = move_resp["result"]["block"]
    assert moved["parent_id"] == parent2_id


def test_blocks_reorder(rpc_db, act_id: str) -> None:
    """Reordering siblings via blocks/reorder returns them in the requested order."""
    ids = []
    for i in range(3):
        bid = _rpc(
            rpc_db,
            req_id=i + 1,
            method="blocks/create",
            params={"type": "paragraph", "act_id": act_id},
        )["result"]["block"]["id"]
        ids.append(bid)

    # Reverse the order
    reversed_ids = list(reversed(ids))
    reorder_resp = _rpc(
        rpc_db,
        req_id=10,
        method="blocks/reorder",
        params={"block_ids": reversed_ids},
    )

    assert "result" in reorder_resp
    returned_ids = [b["id"] for b in reorder_resp["result"]["blocks"]]
    assert returned_ids == reversed_ids


def test_blocks_ancestors(rpc_db, act_id: str) -> None:
    """Getting ancestors of a child returns its parent chain in order."""
    # Use nestable types (bulleted_list) as non-leaf nodes
    grandparent_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id},
    )["result"]["block"]["id"]

    parent_id = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id, "parent_id": grandparent_id},
    )["result"]["block"]["id"]

    child_id = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "parent_id": parent_id},
    )["result"]["block"]["id"]

    anc_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/ancestors",
        params={"block_id": child_id},
    )

    assert "result" in anc_resp
    ancestor_ids = [a["id"] for a in anc_resp["result"]["ancestors"]]
    assert parent_id in ancestor_ids
    assert grandparent_id in ancestor_ids


def test_blocks_descendants(rpc_db, act_id: str) -> None:
    """Getting descendants of a parent returns both its direct children."""
    # bulleted_list supports children
    parent_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id},
    )["result"]["block"]["id"]

    child1_id = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "parent_id": parent_id},
    )["result"]["block"]["id"]

    child2_id = _rpc(
        rpc_db,
        req_id=3,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "parent_id": parent_id},
    )["result"]["block"]["id"]

    desc_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/descendants",
        params={"block_id": parent_id},
    )

    assert "result" in desc_resp
    desc_ids = {d["id"] for d in desc_resp["result"]["descendants"]}
    assert child1_id in desc_ids
    assert child2_id in desc_ids


# =============================================================================
# Search & Page
# =============================================================================


def test_blocks_search(rpc_db, act_id: str) -> None:
    """Creating a block with unique text and searching for it returns that block."""
    unique_text = "xyzzy_unique_search_term_1a2b3c"
    spans = [{"content": unique_text, "bold": False, "italic": False, "code": False}]

    block_id = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "rich_text": spans},
    )["result"]["block"]["id"]

    search_resp = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/search",
        params={"act_id": act_id, "query": unique_text},
    )

    assert "result" in search_resp
    # search returns dicts with block_id key (from play_db.search_blocks_in_act)
    result = search_resp["result"]
    assert result["count"] > 0
    block_ids_in_result = {b.get("id") or b.get("block_id") for b in result["blocks"]}
    assert block_id in block_ids_in_result


def test_page_tree(rpc_db, act_id: str) -> None:
    """Creating blocks under a real page_id and fetching the page tree returns nested blocks."""
    page_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/pages/create",
        params={"act_id": act_id, "title": "Test Page"},
    )
    assert "result" in page_resp
    page_id = page_resp["result"]["created_page_id"]

    root_id = _rpc(
        rpc_db,
        req_id=2,
        method="blocks/create",
        params={"type": "bulleted_list", "act_id": act_id, "page_id": page_id},
    )["result"]["block"]["id"]

    _rpc(
        rpc_db,
        req_id=3,
        method="blocks/create",
        params={"type": "paragraph", "act_id": act_id, "page_id": page_id, "parent_id": root_id},
    )

    tree_resp = _rpc(
        rpc_db,
        req_id=4,
        method="blocks/page/tree",
        params={"page_id": page_id},
    )

    assert "result" in tree_resp
    root_blocks = tree_resp["result"]["blocks"]
    assert len(root_blocks) >= 1
    root_ids = [b["id"] for b in root_blocks]
    assert root_id in root_ids


def test_import_markdown(rpc_db, act_id: str) -> None:
    """Importing a markdown string via blocks/import/markdown creates the expected blocks."""
    md = "# Heading\n\nParagraph text here.\n\n- Item one\n- Item two\n"

    import_resp = _rpc(
        rpc_db,
        req_id=1,
        method="blocks/import/markdown",
        params={"act_id": act_id, "markdown": md},
    )

    assert "result" in import_resp
    result = import_resp["result"]
    assert result["count"] > 0
    assert len(result["blocks"]) == result["count"]
    block_types = {b["type"] for b in result["blocks"]}
    assert "heading_1" in block_types
