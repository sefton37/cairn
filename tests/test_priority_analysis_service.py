"""Tests for PriorityAnalysisService — CAIRN-driven priority learning.

Covers:
- Synthetic message construction (old order, new order, moved item, scene details)
- Moved item detection algorithm
- ChatAgent integration (is_system_initiated=True, agent_type='cairn')
- LLM failure propagation
- is_system_initiated behavior on ChatAgent.respond
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Moved Item Detection
# =============================================================================


class TestMovedItemDetection:
    """Test _detect_moved_item finds the item with the largest rank delta."""

    def test_simple_move(self) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        svc = PriorityAnalysisService()
        # Item "c" moved from position 2 to position 0
        old = {"a": 0, "b": 1, "c": 2}
        new = {"c": 0, "a": 1, "b": 2}
        moved_id, old_pos, new_pos = svc._detect_moved_item(old, new)

        assert moved_id == "c"
        assert old_pos == 2
        assert new_pos == 0

    def test_swap_picks_larger_delta(self) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        svc = PriorityAnalysisService()
        old = {"a": 0, "b": 1, "c": 2, "d": 3}
        new = {"a": 0, "d": 1, "c": 2, "b": 3}
        moved_id, old_pos, new_pos = svc._detect_moved_item(old, new)

        # Both b and d moved by 2 positions — first found wins (d)
        assert moved_id in ("b", "d")
        assert abs(old_pos - new_pos) == 2

    def test_no_change(self) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        svc = PriorityAnalysisService()
        old = {"a": 0, "b": 1}
        new = {"a": 0, "b": 1}
        moved_id, old_pos, new_pos = svc._detect_moved_item(old, new)

        # No change — no moved item (delta=0, never exceeds max_delta=0)
        assert moved_id is None

    def test_empty_old_priorities(self) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        svc = PriorityAnalysisService()
        old: dict[str, int] = {}
        new = {"a": 0, "b": 1}
        moved_id, old_pos, new_pos = svc._detect_moved_item(old, new)

        # No old order means no meaningful "moved" item
        assert moved_id is None

    def test_new_item_in_order(self) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        svc = PriorityAnalysisService()
        old = {"a": 0}
        new = {"b": 0, "a": 1}
        moved_id, old_pos, new_pos = svc._detect_moved_item(old, new)

        # "a" moved from 0→1 (delta=1), "b" is new (implicitly from end)
        # "b" treated as new item at position 1→0 — but "a" has delta=1
        # The new item "b" has old_pos=1 (len of old), new_pos=0, delta=1
        assert moved_id is not None


# =============================================================================
# Synthetic Message Construction
# =============================================================================


class TestSyntheticMessageConstruction:
    """Test _build_synthetic_message produces correct prompt."""

    def _make_service(self):
        from cairn.services.priority_analysis_service import PriorityAnalysisService
        return PriorityAnalysisService()

    def test_contains_system_event_header(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s1"],
            old_priorities={},
            scene_details=[{"scene_id": "s1", "title": "Task A", "stage": "planning"}],
        )
        assert "[SYSTEM EVENT — Priority Reorder]" in msg

    def test_contains_previous_order(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s2", "s1"],
            old_priorities={"s1": 0, "s2": 1},
            scene_details=[
                {"scene_id": "s1", "title": "First", "stage": "in_progress"},
                {"scene_id": "s2", "title": "Second", "stage": "planning"},
            ],
        )
        assert "PREVIOUS ORDER:" in msg
        assert '"First"' in msg
        assert '"Second"' in msg

    def test_contains_new_order_with_moved_annotation(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s2", "s1"],
            old_priorities={"s1": 0, "s2": 1},
            scene_details=[
                {"scene_id": "s1", "title": "First", "stage": "in_progress"},
                {"scene_id": "s2", "title": "Second", "stage": "planning"},
            ],
        )
        assert "NEW ORDER:" in msg
        assert "MOVED from position" in msg

    def test_contains_change_summary(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s2", "s1"],
            old_priorities={"s1": 0, "s2": 1},
            scene_details=[
                {"scene_id": "s1", "title": "First", "stage": "in_progress"},
                {"scene_id": "s2", "title": "Second", "stage": "planning"},
            ],
        )
        assert "CHANGE:" in msg
        assert "moved from position" in msg

    def test_contains_scene_details(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s1"],
            old_priorities={},
            scene_details=[{
                "scene_id": "s1",
                "title": "Important Task",
                "stage": "in_progress",
                "act_title": "Career",
                "start_date": "2026-03-01",
                "end_date": "2026-03-15",
                "notes": "Working on this actively",
            }],
        )
        assert "SCENE DETAILS:" in msg
        assert "Important Task" in msg
        assert "Career" in msg
        assert "2026-03-01" in msg
        assert "Working on this actively" in msg

    def test_contains_memory_proposal_instruction(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s1"],
            old_priorities={},
            scene_details=[{"scene_id": "s1", "title": "Task", "stage": "planning"}],
        )
        assert "propose one or two concise memory statements" in msg
        assert "ask the user whether these observations should be saved" in msg

    def test_no_previous_order(self) -> None:
        svc = self._make_service()
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s1", "s2"],
            old_priorities={},
            scene_details=[
                {"scene_id": "s1", "title": "A", "stage": "planning"},
                {"scene_id": "s2", "title": "B", "stage": "planning"},
            ],
        )
        assert "(no previous ordering)" in msg

    def test_notes_truncated_to_300_chars(self) -> None:
        svc = self._make_service()
        long_notes = "x" * 500
        msg = svc._build_synthetic_message(
            ordered_scene_ids=["s1"],
            old_priorities={},
            scene_details=[{
                "scene_id": "s1",
                "title": "Task",
                "stage": "planning",
                "notes": long_notes,
            }],
        )
        # Notes should be truncated to 300 chars
        assert "x" * 300 in msg
        assert "x" * 301 not in msg


# =============================================================================
# ChatAgent Integration
# =============================================================================


class TestAnalyzeReorder:
    """Test analyze_reorder calls ChatAgent correctly."""

    @patch("cairn.agent.ChatAgent")
    def test_calls_chat_agent_with_system_initiated(self, mock_agent_cls) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        mock_response = MagicMock()
        mock_response.answer = "I notice you prioritized X over Y."
        mock_agent = MagicMock()
        mock_agent.respond.return_value = mock_response
        mock_agent_cls.return_value = mock_agent

        svc = PriorityAnalysisService()
        db = MagicMock()
        result = svc.analyze_reorder(
            db=db,
            ordered_scene_ids=["s1", "s2"],
            old_priorities={"s2": 0, "s1": 1},
            scene_details=[
                {"scene_id": "s1", "title": "Task A", "stage": "planning"},
                {"scene_id": "s2", "title": "Task B", "stage": "in_progress"},
            ],
            conversation_id="conv-123",
        )

        assert result == "I notice you prioritized X over Y."
        mock_agent_cls.assert_called_once_with(db=db)
        mock_agent.respond.assert_called_once()

        call_kwargs = mock_agent.respond.call_args
        assert call_kwargs.kwargs["conversation_id"] == "conv-123"
        assert call_kwargs.kwargs["agent_type"] == "cairn"
        assert call_kwargs.kwargs["is_system_initiated"] is True

    @patch("cairn.agent.ChatAgent")
    def test_synthetic_message_passed_to_agent(self, mock_agent_cls) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        mock_response = MagicMock()
        mock_response.answer = "analysis"
        mock_agent = MagicMock()
        mock_agent.respond.return_value = mock_response
        mock_agent_cls.return_value = mock_agent

        svc = PriorityAnalysisService()
        svc.analyze_reorder(
            db=MagicMock(),
            ordered_scene_ids=["s1"],
            old_priorities={},
            scene_details=[{"scene_id": "s1", "title": "Task", "stage": "planning"}],
            conversation_id="conv-456",
        )

        call_args = mock_agent.respond.call_args
        message = call_args.args[0]
        assert "[SYSTEM EVENT — Priority Reorder]" in message

    @patch("cairn.agent.ChatAgent")
    def test_llm_failure_propagates(self, mock_agent_cls) -> None:
        from cairn.services.priority_analysis_service import PriorityAnalysisService

        mock_agent = MagicMock()
        mock_agent.respond.side_effect = RuntimeError("LLM unreachable")
        mock_agent_cls.return_value = mock_agent

        svc = PriorityAnalysisService()
        with pytest.raises(RuntimeError, match="LLM unreachable"):
            svc.analyze_reorder(
                db=MagicMock(),
                ordered_scene_ids=["s1"],
                old_priorities={},
                scene_details=[{"scene_id": "s1", "title": "Task", "stage": "planning"}],
                conversation_id="conv-789",
            )
