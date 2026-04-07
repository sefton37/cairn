"""Unit tests for the context/ RPC handler functions.

Tests verify:
- handle_context_stats returns stats dict and uses DB for messages and settings
- handle_context_toggle_source validates source names and updates DB state
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.get_messages.return_value = []
    db.get_state.return_value = None
    db.get_active_persona_id.return_value = None
    return db


# =============================================================================
# handle_context_stats
# =============================================================================


class TestHandleContextStats:
    """handle_context_stats returns a stats dict from calculate_context_stats."""

    def test_returns_dict_with_no_conversation(self) -> None:
        from cairn.rpc_handlers.context import handle_context_stats

        fake_stats = MagicMock()
        fake_stats.to_dict.return_value = {"used": 100, "limit": 8192, "percent": 1.2}

        with (
            patch("cairn.rpc_handlers.context.play_list_acts", return_value=([], None)),
            patch("cairn.rpc_handlers.context.calculate_context_stats", return_value=fake_stats),
        ):
            result = handle_context_stats(_mock_db())

        assert result["used"] == 100
        assert result["limit"] == 8192

    def test_fetches_messages_when_conversation_id_provided(self) -> None:
        from cairn.rpc_handlers.context import handle_context_stats

        db = _mock_db()
        db.get_messages.return_value = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi there"},
        ]

        fake_stats = MagicMock()
        fake_stats.to_dict.return_value = {"used": 200, "limit": 8192}

        with (
            patch("cairn.rpc_handlers.context.play_list_acts", return_value=([], None)),
            patch("cairn.rpc_handlers.context.calculate_context_stats", return_value=fake_stats),
        ):
            result = handle_context_stats(db, conversation_id="conv-1")

        db.get_messages.assert_called_once_with(conversation_id="conv-1", limit=100)
        assert result["used"] == 200

    def test_uses_stored_num_ctx_as_context_limit(self) -> None:
        from cairn.rpc_handlers.context import handle_context_stats

        db = _mock_db()
        db.get_state.side_effect = lambda key: "16384" if key == "ollama_num_ctx" else None

        fake_stats = MagicMock()
        fake_stats.to_dict.return_value = {"limit": 16384}

        captured = {}

        def capture_stats(**kwargs):
            captured.update(kwargs)
            return fake_stats

        with (
            patch("cairn.rpc_handlers.context.play_list_acts", return_value=([], None)),
            patch("cairn.rpc_handlers.context.calculate_context_stats", side_effect=capture_stats),
        ):
            handle_context_stats(db)

        assert captured["context_limit"] == 16384

    def test_defaults_to_8192_when_num_ctx_not_set(self) -> None:
        from cairn.rpc_handlers.context import handle_context_stats

        db = _mock_db()
        db.get_state.return_value = None

        fake_stats = MagicMock()
        fake_stats.to_dict.return_value = {"limit": 8192}

        captured = {}

        def capture_stats(**kwargs):
            captured.update(kwargs)
            return fake_stats

        with (
            patch("cairn.rpc_handlers.context.play_list_acts", return_value=([], None)),
            patch("cairn.rpc_handlers.context.calculate_context_stats", side_effect=capture_stats),
        ):
            handle_context_stats(db)

        assert captured["context_limit"] == 8192


# =============================================================================
# handle_context_toggle_source
# =============================================================================


class TestHandleContextToggleSource:
    """handle_context_toggle_source validates and updates disabled source set."""

    def test_raises_rpc_error_for_invalid_source_name(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.context import handle_context_toggle_source

        with pytest.raises(RpcError) as exc_info:
            handle_context_toggle_source(_mock_db(), source_name="nonexistent_source", enabled=False)

        assert exc_info.value.code == -32602
        assert "Invalid source name" in exc_info.value.message

    def test_raises_rpc_error_when_disabling_required_source(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.context import handle_context_toggle_source

        # "system_prompt" is a required (non-disableable) source
        with pytest.raises(RpcError) as exc_info:
            handle_context_toggle_source(_mock_db(), source_name="system_prompt", enabled=False)

        assert exc_info.value.code == -32602
        assert "Cannot disable" in exc_info.value.message

    def test_disabling_play_context_saves_it_to_db(self) -> None:
        from cairn.rpc_handlers.context import handle_context_toggle_source

        db = _mock_db()
        db.get_state.return_value = None

        result = handle_context_toggle_source(db, source_name="play_context", enabled=False)

        assert result["ok"] is True
        db.set_state.assert_called_once()
        saved_value = db.set_state.call_args.kwargs.get("value") or db.set_state.call_args[1].get("value")
        assert "play_context" in saved_value

    def test_enabling_previously_disabled_source_removes_it_from_disabled_set(self) -> None:
        from cairn.rpc_handlers.context import handle_context_toggle_source

        db = _mock_db()
        db.get_state.return_value = "play_context,learned_kb"

        result = handle_context_toggle_source(db, source_name="play_context", enabled=True)

        assert result["ok"] is True
        assert "play_context" not in result["disabled_sources"]
