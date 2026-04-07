"""RPC round-trip integration tests for Play (Acts, Scenes, Me) with a real DB.

Tests pass through the real JSON-RPC dispatcher (_handle_jsonrpc_request) using a
real temporary SQLite database — no mocks, no stubs.
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
# Acts CRUD
# =============================================================================


def test_acts_list_empty_has_your_story(rpc_db) -> None:
    """A fresh DB always has the built-in 'your-story' act in the list."""
    resp = _rpc(rpc_db, req_id=1, method="play/acts/list")

    assert "result" in resp
    act_ids = {a["act_id"] for a in resp["result"]["acts"]}
    assert "your-story" in act_ids


def test_acts_create_and_list(rpc_db) -> None:
    """Creating an act via play/acts/create makes it appear in play/acts/list."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "My New Act", "notes": "some notes"},
    )

    assert "result" in create_resp
    created_id = create_resp["result"]["created_act_id"]
    assert isinstance(created_id, str)
    assert created_id

    list_resp = _rpc(rpc_db, req_id=2, method="play/acts/list")
    act_ids = {a["act_id"] for a in list_resp["result"]["acts"]}
    assert created_id in act_ids


def test_acts_update(rpc_db) -> None:
    """Updating an act's title, notes, and color persists via play/acts/list."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Original Title"},
    )
    act_id = create_resp["result"]["created_act_id"]

    update_resp = _rpc(
        rpc_db,
        req_id=2,
        method="play/acts/update",
        params={"act_id": act_id, "title": "Updated Title", "notes": "new notes", "color": "#ff0000"},
    )

    assert "result" in update_resp
    acts_by_id = {a["act_id"]: a for a in update_resp["result"]["acts"]}
    updated = acts_by_id[act_id]
    assert updated["title"] == "Updated Title"
    assert updated["notes"] == "new notes"
    assert updated["color"] == "#ff0000"


def test_acts_set_active(rpc_db) -> None:
    """Setting an act active via play/acts/set_active reflects in active_act_id."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Active Act"},
    )
    act_id = create_resp["result"]["created_act_id"]

    set_resp = _rpc(
        rpc_db,
        req_id=2,
        method="play/acts/set_active",
        params={"act_id": act_id},
    )

    assert "result" in set_resp
    assert set_resp["result"]["active_act_id"] == act_id


def test_acts_delete(rpc_db) -> None:
    """Deleting an act removes it from play/acts/list."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Act To Delete"},
    )
    act_id = create_resp["result"]["created_act_id"]

    delete_resp = _rpc(
        rpc_db,
        req_id=2,
        method="play/acts/delete",
        params={"act_id": act_id},
    )

    assert "result" in delete_resp
    act_ids = {a["act_id"] for a in delete_resp["result"]["acts"]}
    assert act_id not in act_ids


def test_acts_delete_your_story_fails(rpc_db) -> None:
    """The built-in 'your-story' act cannot be deleted."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/delete",
        params={"act_id": "your-story"},
    )

    assert "error" in resp


# =============================================================================
# Scenes CRUD
# =============================================================================


def test_scenes_list_empty(rpc_db) -> None:
    """A freshly created act has no scenes."""
    create_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Empty Act"},
    )
    act_id = create_resp["result"]["created_act_id"]

    list_resp = _rpc(
        rpc_db,
        req_id=2,
        method="play/scenes/list",
        params={"act_id": act_id},
    )

    assert "result" in list_resp
    assert list_resp["result"]["scenes"] == []


def test_scenes_create_and_list(rpc_db) -> None:
    """Creating a scene in an act makes it appear in play/scenes/list."""
    act_id = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Act With Scene"},
    )["result"]["created_act_id"]

    create_resp = _rpc(
        rpc_db,
        req_id=2,
        method="play/scenes/create",
        params={"act_id": act_id, "title": "My Scene"},
    )

    assert "result" in create_resp
    scenes = create_resp["result"]["scenes"]
    assert len(scenes) == 1
    assert scenes[0]["title"] == "My Scene"
    assert scenes[0]["act_id"] == act_id
    assert "scene_id" in scenes[0]


def test_scenes_update(rpc_db) -> None:
    """Updating a scene's title, stage, and notes persists in the response."""
    act_id = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Act"},
    )["result"]["created_act_id"]

    scene_id = _rpc(
        rpc_db,
        req_id=2,
        method="play/scenes/create",
        params={"act_id": act_id, "title": "Original Scene"},
    )["result"]["scenes"][0]["scene_id"]

    update_resp = _rpc(
        rpc_db,
        req_id=3,
        method="play/scenes/update",
        params={
            "act_id": act_id,
            "scene_id": scene_id,
            "title": "Updated Scene",
            "stage": "in_progress",
            "notes": "updated notes",
        },
    )

    assert "result" in update_resp
    scenes_by_id = {s["scene_id"]: s for s in update_resp["result"]["scenes"]}
    updated = scenes_by_id[scene_id]
    assert updated["title"] == "Updated Scene"
    assert updated["stage"] == "in_progress"
    assert updated["notes"] == "updated notes"


def test_scenes_list_all(rpc_db) -> None:
    """play/scenes/list_all returns scenes from multiple acts."""
    act1_id = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Act 1"},
    )["result"]["created_act_id"]

    act2_id = _rpc(
        rpc_db,
        req_id=2,
        method="play/acts/create",
        params={"title": "Act 2"},
    )["result"]["created_act_id"]

    _rpc(
        rpc_db,
        req_id=3,
        method="play/scenes/create",
        params={"act_id": act1_id, "title": "Scene A"},
    )
    _rpc(
        rpc_db,
        req_id=4,
        method="play/scenes/create",
        params={"act_id": act2_id, "title": "Scene B"},
    )

    list_all_resp = _rpc(rpc_db, req_id=5, method="play/scenes/list_all")

    assert "result" in list_all_resp
    scenes = list_all_resp["result"]["scenes"]
    act_ids_in_result = {s["act_id"] for s in scenes}
    assert act1_id in act_ids_in_result
    assert act2_id in act_ids_in_result


def test_scenes_delete(rpc_db) -> None:
    """Deleting a scene removes it from the act's scene list."""
    act_id = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": "Act"},
    )["result"]["created_act_id"]

    scene_id = _rpc(
        rpc_db,
        req_id=2,
        method="play/scenes/create",
        params={"act_id": act_id, "title": "Scene To Delete"},
    )["result"]["scenes"][0]["scene_id"]

    delete_resp = _rpc(
        rpc_db,
        req_id=3,
        method="play/scenes/delete",
        params={"act_id": act_id, "scene_id": scene_id},
    )

    assert "result" in delete_resp
    remaining_ids = {s["scene_id"] for s in delete_resp["result"]["scenes"]}
    assert scene_id not in remaining_ids


# =============================================================================
# Me (Your Story)
# =============================================================================


def test_me_read_default(rpc_db) -> None:
    """play/me/read returns markdown containing 'Your Story' by default."""
    resp = _rpc(rpc_db, req_id=1, method="play/me/read")

    assert "result" in resp
    assert "markdown" in resp["result"]
    assert "Your Story" in str(resp["result"]["markdown"])


def test_me_write_and_read_roundtrip(rpc_db) -> None:
    """Writing text via play/me/write and reading it back via play/me/read returns the same content."""
    new_content = "# My Story\n\nThis is my personal narrative."

    write_resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/me/write",
        params={"text": new_content},
    )

    assert "result" in write_resp
    assert write_resp["result"]["ok"] is True

    read_resp = _rpc(rpc_db, req_id=2, method="play/me/read")

    assert "result" in read_resp
    assert new_content in read_resp["result"]["markdown"]


# =============================================================================
# Validation
# =============================================================================


def test_acts_create_empty_title_fails(rpc_db) -> None:
    """Creating an act with an empty title returns a JSON-RPC error."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/acts/create",
        params={"title": ""},
    )

    assert "error" in resp


def test_scenes_create_nonexistent_act_fails(rpc_db) -> None:
    """Creating a scene in a non-existent act returns a JSON-RPC error."""
    resp = _rpc(
        rpc_db,
        req_id=1,
        method="play/scenes/create",
        params={"act_id": "does-not-exist-act-id", "title": "Orphan Scene"},
    )

    assert "error" in resp
