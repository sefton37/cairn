"""Unit tests for the personas/ RPC handler functions.

Tests verify:
- handle_personas_list delegates to db.iter_agent_personas and db.get_active_persona_id
- handle_persona_get retrieves a single persona by ID
- handle_persona_upsert validates required fields and calls db.upsert_agent_persona
- handle_persona_set_active updates the active persona ID
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.iter_agent_personas.return_value = []
    db.get_active_persona_id.return_value = None
    return db


def _valid_persona() -> dict:
    return {
        "id": "persona-1",
        "name": "Cairn Default",
        "system_prompt": "You are a helpful assistant.",
        "default_context": "minimal",
        "temperature": 0.7,
        "top_p": 0.9,
        "tool_call_limit": 10,
    }


# =============================================================================
# handle_personas_list
# =============================================================================


class TestHandlePersonasList:
    """handle_personas_list wraps db.iter_agent_personas."""

    def test_returns_empty_personas_list_when_none_exist(self) -> None:
        from cairn.rpc_handlers.personas import handle_personas_list

        db = _mock_db()
        result = handle_personas_list(db)

        assert result["personas"] == []
        assert result["active_persona_id"] is None

    def test_returns_personas_and_active_id(self) -> None:
        from cairn.rpc_handlers.personas import handle_personas_list

        db = _mock_db()
        db.iter_agent_personas.return_value = [{"id": "p1", "name": "Bot"}]
        db.get_active_persona_id.return_value = "p1"

        result = handle_personas_list(db)

        assert len(result["personas"]) == 1
        assert result["active_persona_id"] == "p1"

    def test_calls_both_db_methods(self) -> None:
        from cairn.rpc_handlers.personas import handle_personas_list

        db = _mock_db()
        handle_personas_list(db)

        db.iter_agent_personas.assert_called_once()
        db.get_active_persona_id.assert_called_once()


# =============================================================================
# handle_persona_get
# =============================================================================


class TestHandlePersonaGet:
    """handle_persona_get returns a single persona by ID."""

    def test_returns_persona_when_found(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_get

        db = _mock_db()
        db.get_agent_persona.return_value = {"id": "p1", "name": "Bot"}

        result = handle_persona_get(db, persona_id="p1")

        assert result["persona"]["id"] == "p1"

    def test_returns_none_when_persona_not_found(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_get

        db = _mock_db()
        db.get_agent_persona.return_value = None

        result = handle_persona_get(db, persona_id="missing")

        assert result["persona"] is None

    def test_passes_persona_id_to_db(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_get

        db = _mock_db()
        db.get_agent_persona.return_value = {}

        handle_persona_get(db, persona_id="persona-xyz")

        db.get_agent_persona.assert_called_once_with(persona_id="persona-xyz")


# =============================================================================
# handle_persona_upsert
# =============================================================================


class TestHandlePersonaUpsert:
    """handle_persona_upsert validates and saves a persona."""

    def test_returns_ok_true_for_valid_persona(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_upsert

        db = _mock_db()
        result = handle_persona_upsert(db, persona=_valid_persona())

        assert result == {"ok": True}

    def test_raises_rpc_error_when_required_fields_missing(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.personas import handle_persona_upsert

        incomplete = {"id": "p1", "name": "Bot"}  # missing most fields

        with pytest.raises(RpcError) as exc_info:
            handle_persona_upsert(_mock_db(), persona=incomplete)

        assert exc_info.value.code == -32602
        assert "missing fields" in exc_info.value.message

    def test_calls_db_upsert_with_correct_arguments(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_upsert

        db = _mock_db()
        persona = _valid_persona()

        handle_persona_upsert(db, persona=persona)

        db.upsert_agent_persona.assert_called_once_with(
            persona_id="persona-1",
            name="Cairn Default",
            system_prompt="You are a helpful assistant.",
            default_context="minimal",
            temperature=0.7,
            top_p=0.9,
            tool_call_limit=10,
        )


# =============================================================================
# handle_persona_set_active
# =============================================================================


class TestHandlePersonaSetActive:
    """handle_persona_set_active updates the active persona or clears it."""

    def test_returns_ok_true_when_setting_active_persona(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_set_active

        db = _mock_db()
        result = handle_persona_set_active(db, persona_id="p1")

        assert result == {"ok": True}

    def test_passes_persona_id_to_db(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_set_active

        db = _mock_db()
        handle_persona_set_active(db, persona_id="p2")

        db.set_active_persona_id.assert_called_once_with(persona_id="p2")

    def test_accepts_none_to_clear_active_persona(self) -> None:
        from cairn.rpc_handlers.personas import handle_persona_set_active

        db = _mock_db()
        result = handle_persona_set_active(db, persona_id=None)

        assert result == {"ok": True}
        db.set_active_persona_id.assert_called_once_with(persona_id=None)

    def test_raises_rpc_error_when_persona_id_is_non_string_non_none(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.personas import handle_persona_set_active

        with pytest.raises(RpcError) as exc_info:
            handle_persona_set_active(_mock_db(), persona_id=123)

        assert exc_info.value.code == -32602
