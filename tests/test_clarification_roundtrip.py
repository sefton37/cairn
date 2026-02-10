"""Tests for clarification round-trip storage and handling.

Tests:
- Store/retrieve/resolve clarification in AtomicOpsStore
- LLM-based detection of clarification responses
- Full round-trip through CairnAtomicBridge
"""

from __future__ import annotations

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from reos.atomic_ops.models import (
    AtomicOperation,
    Classification,
    ConsumerType,
    DestinationType,
    ExecutionSemantics,
    OperationStatus,
)
from reos.atomic_ops.schema import AtomicOpsStore

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def db_conn() -> sqlite3.Connection:
    """Create an in-memory database with atomic ops schema."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    return conn


@pytest.fixture
def store(db_conn: sqlite3.Connection) -> AtomicOpsStore:
    """Create an AtomicOpsStore with initialized schema."""
    return AtomicOpsStore(db_conn)


def _create_operation(store: AtomicOpsStore, user_id: str, request: str) -> str:
    """Helper to create an operation and return its ID."""
    op = AtomicOperation(
        user_request=request,
        user_id=user_id,
        classification=Classification(
            destination=DestinationType.STREAM,
            consumer=ConsumerType.HUMAN,
            semantics=ExecutionSemantics.INTERPRET,
            confident=False,
            reasoning="ambiguous",
        ),
        status=OperationStatus.AWAITING_APPROVAL,
    )
    store.create_operation(op)
    return op.id


class MockLLM:
    """Mock LLM provider for testing."""

    def __init__(self, response: str | None = None, error: Exception | None = None):
        self.response = response
        self.error = error
        self.call_count = 0
        self.current_model = "test-model-1b"

    def chat_json(
        self,
        system: str = "",
        user: str = "",
        temperature: float = 0.1,
        top_p: float = 0.9,
        **kwargs,
    ) -> str:
        self.call_count += 1
        if self.error:
            raise self.error
        return self.response or "{}"


# =============================================================================
# TestClarificationStorage
# =============================================================================


class TestClarificationStorage:
    """Test store/retrieve/resolve clarification methods."""

    def test_store_and_retrieve_pending(self, store: AtomicOpsStore) -> None:
        """Store a clarification, retrieve it as pending."""
        op_id = _create_operation(store, "user-1", "move that to Career")
        store.store_clarification(op_id, "Which beat did you mean?")
        store.conn.commit()

        pending = store.get_pending_clarification("user-1")
        assert pending is not None
        assert pending["operation_id"] == op_id
        assert pending["question"] == "Which beat did you mean?"
        assert pending["original_request"] == "move that to Career"

    def test_no_pending_when_none_stored(self, store: AtomicOpsStore) -> None:
        """No pending clarification returns None."""
        pending = store.get_pending_clarification("user-1")
        assert pending is None

    def test_resolve_clears_pending(self, store: AtomicOpsStore) -> None:
        """After resolving, get_pending returns None."""
        op_id = _create_operation(store, "user-1", "move that to Career")
        store.store_clarification(op_id, "Which beat did you mean?")
        store.conn.commit()

        pending = store.get_pending_clarification("user-1")
        assert pending is not None

        store.resolve_clarification(pending["id"], "Job Search")
        store.conn.commit()

        assert store.get_pending_clarification("user-1") is None

    def test_only_latest_returned(self, store: AtomicOpsStore) -> None:
        """Multiple clarifications -> most recent unresolved returned."""
        op_id1 = _create_operation(store, "user-1", "move that")
        op_id2 = _create_operation(store, "user-1", "delete that scene")

        store.store_clarification(op_id1, "Which beat?")
        store.store_clarification(op_id2, "Which scene to delete?")
        store.conn.commit()

        pending = store.get_pending_clarification("user-1")
        assert pending is not None
        assert pending["question"] == "Which scene to delete?"
        assert pending["operation_id"] == op_id2

    def test_resolved_not_returned(self, store: AtomicOpsStore) -> None:
        """Resolved clarification is not returned as pending."""
        op_id1 = _create_operation(store, "user-1", "move that")
        op_id2 = _create_operation(store, "user-1", "delete that scene")

        clar1_id = store.store_clarification(op_id1, "Which beat?")
        store.store_clarification(op_id2, "Which scene to delete?")
        store.conn.commit()

        # Resolve the second (latest) one
        pending = store.get_pending_clarification("user-1")
        store.resolve_clarification(pending["id"], "the morning one")
        store.conn.commit()

        # Should now get the first (still unresolved) one
        pending = store.get_pending_clarification("user-1")
        assert pending is not None
        assert pending["id"] == clar1_id

    def test_different_users_isolated(self, store: AtomicOpsStore) -> None:
        """Clarifications for different users don't interfere."""
        op_id1 = _create_operation(store, "user-1", "move that")
        op_id2 = _create_operation(store, "user-2", "delete that")

        store.store_clarification(op_id1, "Which beat?")
        store.store_clarification(op_id2, "Which scene?")
        store.conn.commit()

        pending1 = store.get_pending_clarification("user-1")
        pending2 = store.get_pending_clarification("user-2")

        assert pending1 is not None
        assert pending1["question"] == "Which beat?"
        assert pending2 is not None
        assert pending2["question"] == "Which scene?"


# =============================================================================
# TestClarificationDetection
# =============================================================================


class TestClarificationDetection:
    """Test LLM-based detection of clarification responses."""

    def _make_bridge(self, llm: MockLLM | None = None):
        """Create a CairnAtomicBridge with mocked dependencies."""
        from reos.atomic_ops.cairn_integration import CairnAtomicBridge

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # Mock the intent engine to provide the LLM
        intent_engine = MagicMock()
        intent_engine.llm = llm

        bridge = CairnAtomicBridge(conn=conn, intent_engine=intent_engine)
        return bridge

    def test_detects_direct_answer(self) -> None:
        """'Job Search' after 'Which beat?' -> is_answer=True."""
        llm = MockLLM(response=json.dumps({"is_answer": True, "reasoning": "direct answer"}))
        bridge = self._make_bridge(llm)

        pending = {"question": "Which beat did you mean?", "original_request": "move that"}
        assert bridge._is_clarification_response("Job Search", pending) is True
        assert llm.call_count == 1

    def test_detects_new_request(self) -> None:
        """'show my calendar' after 'Which beat?' -> is_answer=False."""
        llm = MockLLM(response=json.dumps({"is_answer": False, "reasoning": "new request"}))
        bridge = self._make_bridge(llm)

        pending = {"question": "Which beat did you mean?", "original_request": "move that"}
        assert bridge._is_clarification_response("show my calendar", pending) is False

    def test_fallback_without_llm(self) -> None:
        """No LLM -> returns False (treat as new request)."""
        bridge = self._make_bridge(llm=None)

        pending = {"question": "Which beat?", "original_request": "move that"}
        assert bridge._is_clarification_response("Job Search", pending) is False

    def test_handles_llm_error(self) -> None:
        """LLM error -> returns False (treat as new request)."""
        llm = MockLLM(error=RuntimeError("connection failed"))
        bridge = self._make_bridge(llm)

        pending = {"question": "Which beat?", "original_request": "move that"}
        assert bridge._is_clarification_response("Job Search", pending) is False

    def test_handles_invalid_json(self) -> None:
        """LLM returns non-JSON -> returns False."""
        llm = MockLLM(response="not json at all")
        bridge = self._make_bridge(llm)

        pending = {"question": "Which beat?", "original_request": "move that"}
        assert bridge._is_clarification_response("Job Search", pending) is False


# =============================================================================
# TestClarificationRoundTrip
# =============================================================================


class TestClarificationRoundTrip:
    """Test the full round-trip through the bridge."""

    def test_ambiguous_stores_clarification(self) -> None:
        """Ambiguous request stores clarification and returns question."""
        from reos.atomic_ops.cairn_integration import CairnAtomicBridge
        from reos.atomic_ops.processor import ProcessingResult

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        intent_engine = MagicMock()
        intent_engine.llm = None

        bridge = CairnAtomicBridge(conn=conn, intent_engine=intent_engine)

        # Create an operation that the processor would return
        op = AtomicOperation(
            user_request="move that to Career",
            user_id="user-1",
            status=OperationStatus.AWAITING_APPROVAL,
        )

        # Mock the processor to return needs_clarification
        mock_result = ProcessingResult(
            success=True,
            operations=[op],
            primary_operation_id=op.id,
            decomposed=False,
            message="clarification needed",
            needs_clarification=True,
            clarification_prompt="Which beat did you mean?",
        )

        # First, store the operation so the clarification FK is valid
        bridge.processor.store.create_operation(op)
        conn.commit()

        with patch.object(bridge.processor, "process_request", return_value=mock_result):
            result = bridge.process_request(
                user_input="move that to Career",
                user_id="user-1",
            )

        assert result.response == "Which beat did you mean?"
        assert result.needs_approval is True

        # Verify clarification was stored
        pending = bridge.processor.store.get_pending_clarification("user-1")
        assert pending is not None
        assert pending["question"] == "Which beat did you mean?"
        assert pending["original_request"] == "move that to Career"

    def test_answer_resolves_and_reprocesses(self) -> None:
        """Answering clarification resolves it and processes augmented input."""
        from reos.atomic_ops.cairn_integration import CairnAtomicBridge, CairnOperationResult
        from reos.atomic_ops.verifiers.pipeline import PipelineResult

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # LLM that detects the answer
        llm = MockLLM(response=json.dumps({"is_answer": True, "reasoning": "direct answer"}))
        intent_engine = MagicMock()
        intent_engine.llm = llm

        bridge = CairnAtomicBridge(conn=conn, intent_engine=intent_engine)

        # Set up a pending clarification
        op = AtomicOperation(
            user_request="move that to Career",
            user_id="user-1",
            status=OperationStatus.AWAITING_APPROVAL,
        )
        bridge.processor.store.create_operation(op)
        bridge.processor.store.store_clarification(op.id, "Which beat did you mean?")
        conn.commit()

        # Mock process_request on the recursive call (after clarification detection)
        # The bridge will call process_request recursively with augmented input
        original_process = bridge.process_request
        call_inputs = []

        def mock_process(user_input, user_id, **kwargs):
            call_inputs.append(user_input)
            # On recursive call (augmented input), return a successful result
            if "(clarification:" in user_input:
                return CairnOperationResult(
                    operation=AtomicOperation(user_request=user_input, user_id=user_id),
                    verification=PipelineResult(
                        passed=True,
                        status=OperationStatus.COMPLETE,
                        results={},
                    ),
                    response="Moved Job Search to Career.",
                    approved=True,
                )
            # First call hits the real method
            return original_process(user_input, user_id, **kwargs)

        with patch.object(bridge, "process_request", side_effect=mock_process):
            result = bridge.process_request(
                user_input="Job Search",
                user_id="user-1",
            )

        assert result.response == "Moved Job Search to Career."
        # Verify augmented input was passed
        assert any("(clarification: Job Search)" in inp for inp in call_inputs)

        # Verify clarification was resolved
        pending = bridge.processor.store.get_pending_clarification("user-1")
        assert pending is None

    def test_non_answer_after_clarification_processes_normally(self) -> None:
        """New request after clarification skips round-trip."""
        from reos.atomic_ops.cairn_integration import CairnAtomicBridge
        from reos.atomic_ops.processor import ProcessingResult

        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row

        # LLM that says "not an answer"
        llm = MockLLM(response=json.dumps({"is_answer": False, "reasoning": "new request"}))
        intent_engine = MagicMock()
        intent_engine.llm = llm

        bridge = CairnAtomicBridge(conn=conn, intent_engine=intent_engine)

        # Set up a pending clarification
        op = AtomicOperation(
            user_request="move that to Career",
            user_id="user-1",
            status=OperationStatus.AWAITING_APPROVAL,
        )
        bridge.processor.store.create_operation(op)
        bridge.processor.store.store_clarification(op.id, "Which beat did you mean?")
        conn.commit()

        # Mock the processor to handle the new request normally
        new_op = AtomicOperation(
            user_request="show my calendar",
            user_id="user-1",
            classification=Classification(
                destination=DestinationType.STREAM,
                consumer=ConsumerType.HUMAN,
                semantics=ExecutionSemantics.READ,
                confident=True,
                reasoning="calendar query",
            ),
            status=OperationStatus.COMPLETE,
        )
        bridge.processor.store.create_operation(new_op)

        mock_result = ProcessingResult(
            success=True,
            operations=[new_op],
            primary_operation_id=new_op.id,
            decomposed=False,
            message="ok",
        )

        with patch.object(bridge.processor, "process_request", return_value=mock_result):
            bridge.process_request(
                user_input="show my calendar",
                user_id="user-1",
            )

        # The pending clarification should still be there (not resolved)
        pending = bridge.processor.store.get_pending_clarification("user-1")
        assert pending is not None
        assert pending["question"] == "Which beat did you mean?"
