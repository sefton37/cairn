"""Unit tests for the reasoning/ RPC handler functions.

Tests verify:
- handle_reasoning_feedback validates rating, finds block, updates properties
- handle_reasoning_chain_get finds block and organises children
- handle_reasoning_chains_list queries DB with filters
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    return MagicMock()


def _make_chain_block(block_id: str = "chain-1") -> MagicMock:
    from cairn.play.blocks_models import BlockType

    block = MagicMock()
    block.id = block_id
    block.type = BlockType.REASONING_CHAIN
    block.children = []
    block.properties = {}
    block.created_at = "2026-01-01T00:00:00Z"
    return block


# =============================================================================
# handle_reasoning_feedback
# =============================================================================


class TestHandleReasoningFeedback:
    """handle_reasoning_feedback records user rating on a reasoning chain block."""

    def test_raises_rpc_error_for_invalid_rating(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        with pytest.raises(RpcError) as exc_info:
            handle_reasoning_feedback(_mock_db(), chain_block_id="chain-1", rating=3)

        assert exc_info.value.code == -32602
        assert "rating" in exc_info.value.message

    def test_raises_rpc_error_when_block_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        with patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_reasoning_feedback(_mock_db(), chain_block_id="missing", rating=5)

        assert exc_info.value.code == -32602
        assert "Block not found" in exc_info.value.message

    def test_raises_rpc_error_when_block_is_wrong_type(self) -> None:
        from cairn.play.blocks_models import BlockType
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        wrong_block = MagicMock()
        wrong_block.type = BlockType.USER_PROMPT

        with patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=wrong_block):
            with pytest.raises(RpcError) as exc_info:
                handle_reasoning_feedback(_mock_db(), chain_block_id="chain-1", rating=5)

        assert exc_info.value.code == -32602

    def test_returns_ok_true_for_thumbs_up_rating(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        block = _make_chain_block()

        with (
            patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=block),
            patch("cairn.rpc_handlers.reasoning.blocks_db.set_block_property"),
        ):
            result = handle_reasoning_feedback(_mock_db(), chain_block_id="chain-1", rating=5)

        assert result["ok"] is True
        assert result["feedback_status"] == "positive"

    def test_returns_negative_status_for_thumbs_down_rating(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        block = _make_chain_block()

        with (
            patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=block),
            patch("cairn.rpc_handlers.reasoning.blocks_db.set_block_property"),
        ):
            result = handle_reasoning_feedback(_mock_db(), chain_block_id="chain-1", rating=1)

        assert result["feedback_status"] == "negative"

    def test_stores_optional_comment_when_provided(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_feedback

        block = _make_chain_block()
        calls = []

        with (
            patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=block),
            patch(
                "cairn.rpc_handlers.reasoning.blocks_db.set_block_property",
                side_effect=lambda *a, **kw: calls.append(a),
            ),
        ):
            handle_reasoning_feedback(
                _mock_db(), chain_block_id="chain-1", rating=5, comment="Great answer"
            )

        property_keys = [call[1] for call in calls]
        assert "feedback_comment" in property_keys


# =============================================================================
# handle_reasoning_chain_get
# =============================================================================


class TestHandleReasoningChainGet:
    """handle_reasoning_chain_get returns full chain data including events."""

    def test_raises_rpc_error_when_block_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.reasoning import handle_reasoning_chain_get

        with patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_reasoning_chain_get(_mock_db(), chain_block_id="gone")

        assert exc_info.value.code == -32602

    def test_returns_chain_data_with_no_children(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_chain_get

        block = _make_chain_block("chain-abc")

        with (
            patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=block),
            patch("cairn.rpc_handlers.reasoning.blocks_db._load_children_recursive"),
        ):
            result = handle_reasoning_chain_get(_mock_db(), chain_block_id="chain-abc")

        assert result["chain_block_id"] == "chain-abc"
        assert result["consciousness_events"] == []
        assert result["event_count"] == 0
        assert result["user_prompt"] is None
        assert result["llm_response"] is None

    def test_raises_rpc_error_when_block_is_wrong_type(self) -> None:
        from cairn.play.blocks_models import BlockType
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.reasoning import handle_reasoning_chain_get

        block = MagicMock()
        block.type = BlockType.USER_PROMPT

        with patch("cairn.rpc_handlers.reasoning.blocks_db.get_block", return_value=block):
            with pytest.raises(RpcError) as exc_info:
                handle_reasoning_chain_get(_mock_db(), chain_block_id="bad-type")

        assert exc_info.value.code == -32602


# =============================================================================
# handle_reasoning_chains_list
# =============================================================================


class TestHandleReasoningChainsList:
    """handle_reasoning_chains_list queries DB and returns paginated chains."""

    def _make_conn(self, rows=None, total=0) -> MagicMock:
        """Return a fake DB connection that yields *rows* and total count."""
        conn = MagicMock()
        data_cursor = MagicMock()
        data_cursor.__iter__ = MagicMock(return_value=iter(rows or []))

        count_row = MagicMock()
        count_row.__getitem__ = MagicMock(side_effect=lambda k: total if k == "total" else 0)
        count_cursor = MagicMock()
        count_cursor.fetchone.return_value = count_row

        conn.execute.side_effect = [data_cursor, count_cursor]
        return conn

    def test_returns_empty_list_when_no_chains_exist(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_chains_list

        conn = self._make_conn(rows=[], total=0)

        with (
            patch("cairn.play_db.init_db"),
            patch("cairn.play_db._get_connection", return_value=conn),
        ):
            result = handle_reasoning_chains_list(_mock_db())

        assert result["chains"] == []
        assert result["total"] == 0

    def test_returns_default_limit_and_offset(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_chains_list

        conn = self._make_conn(rows=[], total=0)

        with (
            patch("cairn.play_db.init_db"),
            patch("cairn.play_db._get_connection", return_value=conn),
        ):
            result = handle_reasoning_chains_list(_mock_db())

        assert result["limit"] == 50
        assert result["offset"] == 0

    def test_passes_limit_and_offset_to_query(self) -> None:
        from cairn.rpc_handlers.reasoning import handle_reasoning_chains_list

        conn = self._make_conn(rows=[], total=0)

        with (
            patch("cairn.play_db.init_db"),
            patch("cairn.play_db._get_connection", return_value=conn),
        ):
            result = handle_reasoning_chains_list(_mock_db(), limit=10, offset=20)

        assert result["limit"] == 10
        assert result["offset"] == 20
