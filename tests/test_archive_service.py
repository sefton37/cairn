"""Tests for ArchiveService - LLM-driven conversation archival."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestArchiveServiceDataclasses:
    """Test the dataclass serialization."""

    def test_archive_result_to_dict(self) -> None:
        """ArchiveResult should serialize to dict."""
        from cairn.services.archive_service import ArchiveResult

        result = ArchiveResult(
            archive_id="arc123",
            title="Test Archive",
            summary="A test conversation",
            message_count=10,
            linked_act_id="act_456",
            linking_reason="Related to project",
            knowledge_entries_added=3,
            topics=["python", "testing"],
            archived_at="2024-01-15T10:00:00Z",
        )
        d = result.to_dict()
        assert d["archive_id"] == "arc123"
        assert d["title"] == "Test Archive"
        assert d["knowledge_entries_added"] == 3
        assert d["topics"] == ["python", "testing"]

    def test_archive_preview_to_dict(self) -> None:
        """ArchivePreview should serialize to dict."""
        from cairn.services.archive_service import ArchivePreview

        preview = ArchivePreview(
            title="Preview Title",
            summary="Preview summary",
            linked_act_id="act_789",
            linking_reason="Test linking",
            knowledge_entries=[
                {"category": "fact", "content": "Test fact"},
                {"category": "lesson", "content": "Test lesson"},
            ],
            topics=["topic1"],
            message_count=5,
        )
        d = preview.to_dict()
        assert d["title"] == "Preview Title"
        assert d["linked_act_id"] == "act_789"
        assert len(d["knowledge_entries"]) == 2
        assert d["message_count"] == 5

    def test_archive_quality_assessment_to_dict(self) -> None:
        """ArchiveQualityAssessment should serialize to dict."""
        from cairn.services.archive_service import ArchiveQualityAssessment

        assessment = ArchiveQualityAssessment(
            assessment_id="assess123",
            archive_id="arc123",
            title_quality=4,
            summary_quality=5,
            act_linking=3,
            knowledge_relevance=4,
            knowledge_coverage=4,
            deduplication=5,
            overall_score=4,
            suggestions=["Add more context"],
            user_feedback=None,
            user_rating=None,
            assessed_at="2024-01-15T10:00:00Z",
        )
        d = assessment.to_dict()
        assert d["overall_score"] == 4
        assert d["suggestions"] == ["Add more context"]
        assert d["user_feedback"] is None


class TestArchiveServiceInit:
    """Test ArchiveService initialization."""

    def test_init_creates_mem_service(self) -> None:
        """ArchiveService should create a MemoryService."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            assert service._db == mock_db
            assert service._mem_service is not None


class TestArchiveServicePreview:
    """Test preview_archive functionality."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        db.get_messages.return_value = [
            {"role": "user", "content": "Hello, how are you?", "created_at": "2024-01-15T10:00:00Z"},
            {"role": "assistant", "content": "I'm doing well!", "created_at": "2024-01-15T10:01:00Z"},
        ]
        return db

    @pytest.fixture
    def mock_provider(self) -> MagicMock:
        """Create a mock LLM provider."""
        provider = MagicMock()
        provider.chat_text.return_value = json.dumps({
            "title": "Greeting Conversation",
            "summary": "A friendly greeting exchange.",
            "linked_act_id": None,
            "linking_reason": None,
            "knowledge_entries": [],
            "topics": ["greeting"],
            "sentiment": "positive",
        })
        return provider

    def test_preview_archive_no_messages_raises(self, mock_db: MagicMock) -> None:
        """Should raise ValueError if no messages."""
        from cairn.services.archive_service import ArchiveService

        mock_db.get_messages.return_value = []

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            with pytest.raises(ValueError, match="No messages"):
                service.preview_archive("conv123")

    def test_preview_archive_returns_preview(
        self, mock_db: MagicMock, mock_provider: MagicMock
    ) -> None:
        """Should return ArchivePreview with LLM analysis."""
        from cairn.services.archive_service import ArchiveService, ArchivePreview

        with patch("cairn.services.archive_service.MemoryService"), \
             patch("cairn.services.archive_service.get_provider", return_value=mock_provider):
            service = ArchiveService(mock_db)
            # Mock _get_acts_context
            service._get_acts_context = MagicMock(return_value="No acts available")

            preview = service.preview_archive("conv123")

            assert isinstance(preview, ArchivePreview)
            assert preview.title == "Greeting Conversation"
            assert preview.message_count == 2


class TestArchiveServiceArchiveWithReview:
    """Test archive_with_review functionality."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        db.get_messages.return_value = [
            {"role": "user", "content": "Test message", "created_at": "2024-01-15T10:00:00Z"},
        ]
        return db

    def test_archive_with_review_returns_result(
        self, mock_db: MagicMock
    ) -> None:
        """Should return ArchiveResult with user-provided data."""
        from cairn.services.archive_service import ArchiveService

        mock_mem_service = MagicMock()
        mock_mem_service.store.return_value = MagicMock()

        with patch("cairn.services.archive_service.MemoryService", return_value=mock_mem_service):
            service = ArchiveService(mock_db)
            service._store_archive_metadata = MagicMock()

            result = service.archive_with_review(
                conversation_id="conv123",
                title="User Title",
                summary="User summary",
                act_id="act_456",
                knowledge_entries=[{"category": "fact", "content": "Test fact"}],
            )

            assert result.title == "User Title"
            assert result.summary == "User summary"
            assert result.linked_act_id == "act_456"

    def test_archive_with_review_adds_knowledge_entries(
        self, mock_db: MagicMock
    ) -> None:
        """Should add knowledge entries from user review via MemoryService."""
        from cairn.services.archive_service import ArchiveService

        mock_mem_service = MagicMock()
        mock_mem_service.store.return_value = MagicMock()

        with patch("cairn.services.archive_service.MemoryService", return_value=mock_mem_service):
            service = ArchiveService(mock_db)
            service._store_archive_metadata = MagicMock()

            result = service.archive_with_review(
                conversation_id="conv123",
                title="Title",
                summary="Summary",
                knowledge_entries=[
                    {"category": "fact", "content": "Fact 1"},
                    {"category": "lesson", "content": "Lesson 1"},
                ],
            )

            assert result.knowledge_entries_added == 2
            assert mock_mem_service.store.call_count == 2

    def test_archive_with_review_adds_additional_notes(
        self, mock_db: MagicMock
    ) -> None:
        """Should add additional notes as observation via MemoryService."""
        from cairn.services.archive_service import ArchiveService

        mock_mem_service = MagicMock()
        mock_mem_service.store.return_value = MagicMock()

        with patch("cairn.services.archive_service.MemoryService", return_value=mock_mem_service):
            service = ArchiveService(mock_db)
            service._store_archive_metadata = MagicMock()

            result = service.archive_with_review(
                conversation_id="conv123",
                title="Title",
                summary="Summary",
                knowledge_entries=[],
                additional_notes="User's additional note",
            )

            # Notes call adds one more store call
            assert result.knowledge_entries_added == 1
            # Verify store was called with observation type
            call_kwargs = mock_mem_service.store.call_args[1]
            assert call_kwargs["memory_type"] == "observation"
            assert call_kwargs["narrative"] == "User's additional note"

    def test_archive_with_review_submits_rating(
        self, mock_db: MagicMock
    ) -> None:
        """Should submit user rating for learning."""
        from cairn.services.archive_service import ArchiveService

        mock_mem_service = MagicMock()
        mock_mem_service.store.return_value = MagicMock()

        with patch("cairn.services.archive_service.MemoryService", return_value=mock_mem_service):
            service = ArchiveService(mock_db)
            service._store_archive_metadata = MagicMock()
            service.submit_user_feedback = MagicMock()

            result = service.archive_with_review(
                conversation_id="conv123",
                title="Title",
                summary="Summary",
                knowledge_entries=[],
                rating=5,
            )

            service.submit_user_feedback.assert_called_once_with(result.archive_id, 5)


class TestArchiveServiceFullArchive:
    """Test archive_conversation (auto mode)."""

    @pytest.fixture
    def mock_db(self) -> MagicMock:
        """Create a mock database."""
        db = MagicMock()
        db.get_messages.return_value = [
            {"role": "user", "content": "Hello", "created_at": "2024-01-15T10:00:00Z"},
            {"role": "assistant", "content": "Hi there!", "created_at": "2024-01-15T10:01:00Z"},
        ]
        return db

    def test_archive_conversation_no_messages_raises(self, mock_db: MagicMock) -> None:
        """Should raise ValueError if no messages."""
        from cairn.services.archive_service import ArchiveService

        mock_db.get_messages.return_value = []

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            with pytest.raises(ValueError, match="No messages"):
                service.archive_conversation("conv123")


class TestArchiveServiceMetadata:
    """Test metadata storage methods."""

    def test_store_archive_metadata(self) -> None:
        """Should store metadata in database."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value = mock_conn

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            service._store_archive_metadata(
                archive_id="arc123",
                conversation_id="conv123",
                act_id="act_456",
                linking_reason="Test reason",
                topics=["topic1"],
                sentiment="positive",
            )

            mock_conn.execute.assert_called_once()


class TestArchiveServiceFeedback:
    """Test user feedback methods."""

    def test_submit_user_feedback(self) -> None:
        """Should store user feedback in database."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value = mock_conn

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            service.submit_user_feedback("arc123", 5, "Great job!")

            mock_conn.execute.assert_called_once()

    def test_get_learning_stats(self) -> None:
        """Should return learning statistics."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value = mock_conn
        # Mock the execute calls to return cursor with fetchone
        mock_cursor = MagicMock()
        mock_cursor.fetchone.side_effect = [
            {"total_feedback": 10, "avg_rating": 4.2, "min_rating": 2, "max_rating": 5},
            {"total_assessments": 5, "avg_score": 3.8, "min_score": 2, "max_score": 5},
        ]
        mock_conn.execute.return_value = mock_cursor

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            stats = service.get_learning_stats()

            assert stats["total_user_feedback"] == 10
            assert stats["avg_user_rating"] == 4.2


class TestArchiveServiceList:
    """Test archive listing methods."""

    def test_list_archives_returns_list(self) -> None:
        """Should return list of archives from DB."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_conn.execute.return_value = mock_cursor

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            archives = service.list_archives()

            assert isinstance(archives, list)

    def test_get_archive_returns_none_when_not_found(self) -> None:
        """Should return None when archive not in DB."""
        from cairn.services.archive_service import ArchiveService

        mock_db = MagicMock()
        mock_conn = MagicMock()
        mock_db.connect.return_value = mock_conn
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.execute.return_value = mock_cursor

        with patch("cairn.services.archive_service.MemoryService"):
            service = ArchiveService(mock_db)
            result = service.get_archive("nonexistent")

            assert result is None
