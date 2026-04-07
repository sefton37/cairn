"""Unit tests for the archive RPC handler functions (src/cairn/rpc_handlers/archive.py).

Each handler is tested with a mocked ArchiveService so tests only verify that:
- the handler delegates to the service correctly
- parameters are extracted and forwarded
- return values are wrapped as documented

No real DB, no real LLM inference.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _mock_db() -> MagicMock:
    """Return a dummy Database object (handlers only use it as a pass-through)."""
    return MagicMock()


# =============================================================================
# handle_conversation_archive_preview
# =============================================================================


class TestHandleConversationArchivePreview:
    """handle_conversation_archive_preview delegates to service.preview_archive."""

    def test_returns_preview_dict(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_preview

        expected = {"title": "Test Convo", "summary": "A summary", "knowledge": []}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.preview_archive.return_value = MagicMock(to_dict=lambda: expected)

            result = handle_conversation_archive_preview(_mock_db(), conversation_id="conv-1")

        assert result == expected

    def test_passes_conversation_id_and_auto_link_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_preview

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.preview_archive.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive_preview(
                _mock_db(), conversation_id="conv-42", auto_link=False
            )

            mock_service.preview_archive.assert_called_once_with("conv-42", auto_link=False)

    def test_auto_link_defaults_to_true(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_preview

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.preview_archive.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive_preview(_mock_db(), conversation_id="conv-1")

            mock_service.preview_archive.assert_called_once_with("conv-1", auto_link=True)


# =============================================================================
# handle_conversation_archive_confirm
# =============================================================================


class TestHandleConversationArchiveConfirm:
    """handle_conversation_archive_confirm delegates to service.archive_with_review."""

    def test_returns_result_dict(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_confirm

        expected = {"archive_id": "arch-1", "status": "archived"}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_with_review.return_value = MagicMock(to_dict=lambda: expected)

            result = handle_conversation_archive_confirm(
                _mock_db(),
                conversation_id="conv-1",
                title="My Title",
                summary="My Summary",
                knowledge_entries=[{"topic": "Python", "content": "It is great"}],
            )

        assert result == expected

    def test_passes_all_required_params_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_confirm

        entries = [{"topic": "TDD", "content": "Write tests first"}]

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_with_review.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive_confirm(
                _mock_db(),
                conversation_id="conv-7",
                title="Sprint Review",
                summary="Completed sprint goals",
                act_id="act-3",
                knowledge_entries=entries,
                additional_notes="Some notes",
                rating=5,
            )

            mock_service.archive_with_review.assert_called_once_with(
                "conv-7",
                title="Sprint Review",
                summary="Completed sprint goals",
                act_id="act-3",
                knowledge_entries=entries,
                additional_notes="Some notes",
                rating=5,
            )

    def test_optional_params_use_defaults(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive_confirm

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_with_review.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive_confirm(
                _mock_db(),
                conversation_id="conv-1",
                title="Title",
                summary="Summary",
                knowledge_entries=[],
            )

            mock_service.archive_with_review.assert_called_once_with(
                "conv-1",
                title="Title",
                summary="Summary",
                act_id=None,
                knowledge_entries=[],
                additional_notes="",
                rating=None,
            )


# =============================================================================
# handle_conversation_archive
# =============================================================================


class TestHandleConversationArchive:
    """handle_conversation_archive delegates to service.archive_conversation."""

    def test_returns_result_dict(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive

        expected = {"archive_id": "arch-99", "knowledge_count": 3}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_conversation.return_value = MagicMock(to_dict=lambda: expected)

            result = handle_conversation_archive(_mock_db(), conversation_id="conv-1")

        assert result == expected

    def test_passes_conversation_id_and_options_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_conversation.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive(
                _mock_db(),
                conversation_id="conv-5",
                act_id="act-1",
                auto_link=False,
                extract_knowledge=False,
            )

            mock_service.archive_conversation.assert_called_once_with(
                "conv-5",
                act_id="act-1",
                auto_link=False,
                extract_knowledge=False,
            )

    def test_optional_params_use_defaults(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_archive

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.archive_conversation.return_value = MagicMock(to_dict=lambda: {})

            handle_conversation_archive(_mock_db(), conversation_id="conv-1")

            mock_service.archive_conversation.assert_called_once_with(
                "conv-1",
                act_id=None,
                auto_link=True,
                extract_knowledge=True,
            )


# =============================================================================
# handle_conversation_delete
# =============================================================================


class TestHandleConversationDelete:
    """handle_conversation_delete delegates to service.delete_conversation."""

    def test_returns_dict_directly_from_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_delete

        expected = {"deleted": True, "conversation_id": "conv-1"}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.delete_conversation.return_value = expected

            result = handle_conversation_delete(_mock_db(), conversation_id="conv-1")

        assert result == expected

    def test_passes_conversation_id_and_archive_first_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_delete

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.delete_conversation.return_value = {"deleted": True}

            handle_conversation_delete(
                _mock_db(), conversation_id="conv-8", archive_first=True
            )

            mock_service.delete_conversation.assert_called_once_with(
                "conv-8", archive_first=True
            )

    def test_archive_first_defaults_to_false(self) -> None:
        from cairn.rpc_handlers.archive import handle_conversation_delete

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.delete_conversation.return_value = {"deleted": True}

            handle_conversation_delete(_mock_db(), conversation_id="conv-1")

            mock_service.delete_conversation.assert_called_once_with(
                "conv-1", archive_first=False
            )


# =============================================================================
# handle_archive_list
# =============================================================================


class TestHandleArchiveList:
    """handle_archive_list delegates to service.list_archives and wraps in {archives: ...}."""

    def test_returns_archives_key_wrapping_service_result(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_list

        fake_archives = [{"id": "arch-1", "title": "First"}, {"id": "arch-2", "title": "Second"}]

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.list_archives.return_value = fake_archives

            result = handle_archive_list(_mock_db())

        assert result == {"archives": fake_archives}

    def test_passes_act_id_and_limit_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_list

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.list_archives.return_value = []

            handle_archive_list(_mock_db(), act_id="act-2", limit=10)

            mock_service.list_archives.assert_called_once_with(act_id="act-2", limit=10)

    def test_defaults_act_id_none_and_limit_50(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_list

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.list_archives.return_value = []

            handle_archive_list(_mock_db())

            mock_service.list_archives.assert_called_once_with(act_id=None, limit=50)


# =============================================================================
# handle_archive_get
# =============================================================================


class TestHandleArchiveGet:
    """handle_archive_get delegates to service.get_archive, raises RpcError when None."""

    def test_returns_archive_dict_when_found(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_get

        fake_archive = {"id": "arch-1", "title": "My Archive", "messages": []}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_archive.return_value = fake_archive

            result = handle_archive_get(_mock_db(), archive_id="arch-1")

        assert result == fake_archive

    def test_raises_rpc_error_when_archive_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.archive import handle_archive_get

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_archive.return_value = None

            with pytest.raises(RpcError) as exc_info:
                handle_archive_get(_mock_db(), archive_id="missing-arch")

        assert exc_info.value.code == -32602

    def test_passes_archive_id_and_act_id_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_get

        fake_archive = {"id": "arch-5"}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_archive.return_value = fake_archive

            handle_archive_get(_mock_db(), archive_id="arch-5", act_id="act-3")

            mock_service.get_archive.assert_called_once_with("arch-5", act_id="act-3")


# =============================================================================
# handle_archive_assess
# =============================================================================


class TestHandleArchiveAssess:
    """handle_archive_assess delegates to service.assess_archive_quality."""

    def test_returns_assessment_dict(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_assess

        expected = {"score": 0.85, "notes": "Good extraction"}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.assess_archive_quality.return_value = MagicMock(
                to_dict=lambda: expected
            )

            result = handle_archive_assess(_mock_db(), archive_id="arch-1")

        assert result == expected

    def test_passes_archive_id_and_act_id_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_assess

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.assess_archive_quality.return_value = MagicMock(to_dict=lambda: {})

            handle_archive_assess(_mock_db(), archive_id="arch-7", act_id="act-2")

            mock_service.assess_archive_quality.assert_called_once_with(
                "arch-7", act_id="act-2"
            )

    def test_act_id_defaults_to_none(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_assess

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.assess_archive_quality.return_value = MagicMock(to_dict=lambda: {})

            handle_archive_assess(_mock_db(), archive_id="arch-1")

            mock_service.assess_archive_quality.assert_called_once_with("arch-1", act_id=None)


# =============================================================================
# handle_archive_feedback
# =============================================================================


class TestHandleArchiveFeedback:
    """handle_archive_feedback delegates to service.submit_user_feedback."""

    def test_returns_service_result_directly(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_feedback

        expected = {"ok": True, "archive_id": "arch-1"}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.submit_user_feedback.return_value = expected

            result = handle_archive_feedback(_mock_db(), archive_id="arch-1", rating=4)

        assert result == expected

    def test_passes_archive_id_rating_and_feedback_to_service(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_feedback

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.submit_user_feedback.return_value = {"ok": True}

            handle_archive_feedback(
                _mock_db(), archive_id="arch-3", rating=5, feedback="Very accurate"
            )

            mock_service.submit_user_feedback.assert_called_once_with(
                "arch-3", 5, "Very accurate"
            )

    def test_feedback_defaults_to_none(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_feedback

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.submit_user_feedback.return_value = {"ok": True}

            handle_archive_feedback(_mock_db(), archive_id="arch-1", rating=3)

            mock_service.submit_user_feedback.assert_called_once_with("arch-1", 3, None)


# =============================================================================
# handle_archive_learning_stats
# =============================================================================


class TestHandleArchiveLearningStats:
    """handle_archive_learning_stats delegates to service.get_learning_stats."""

    def test_returns_service_result_directly(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_learning_stats

        expected = {"total_archives": 12, "avg_rating": 4.2, "feedback_count": 7}

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_learning_stats.return_value = expected

            result = handle_archive_learning_stats(_mock_db())

        assert result == expected

    def test_calls_get_learning_stats_with_no_extra_args(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_learning_stats

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_learning_stats.return_value = {}

            handle_archive_learning_stats(_mock_db())

            mock_service.get_learning_stats.assert_called_once_with()

    def test_constructs_service_with_db(self) -> None:
        from cairn.rpc_handlers.archive import handle_archive_learning_stats

        db = _mock_db()

        with patch("cairn.services.archive_service.ArchiveService") as MockService:
            mock_service = MockService.return_value
            mock_service.get_learning_stats.return_value = {}

            handle_archive_learning_stats(db)

            MockService.assert_called_once_with(db)
