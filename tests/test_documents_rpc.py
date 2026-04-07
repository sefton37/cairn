"""Unit tests for the documents/ RPC handler functions.

Each handler is tested with mocked dependencies so tests only verify:
- delegation to the underlying document functions
- parameter extraction and forwarding
- error handling for missing files and unknown documents

No real filesystem I/O beyond tmp_path for handle_documents_insert.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    return MagicMock()


# =============================================================================
# handle_documents_insert
# =============================================================================


class TestHandleDocumentsInsert:
    """handle_documents_insert copies, extracts, chunks, and blocks a file."""

    def test_raises_rpc_error_when_file_does_not_exist(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_insert

        with pytest.raises(RpcError) as exc_info:
            handle_documents_insert(_mock_db(), file_path="/nonexistent/path/file.pdf")

        assert exc_info.value.code == -32602
        assert "File not found" in exc_info.value.message

    def test_raises_rpc_error_when_path_is_a_directory(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_insert

        with pytest.raises(RpcError) as exc_info:
            handle_documents_insert(_mock_db(), file_path=str(tmp_path))

        assert exc_info.value.code == -32602
        assert "Not a file" in exc_info.value.message

    def test_returns_document_metadata_on_success(self, tmp_path) -> None:
        from cairn.rpc_handlers.documents import handle_documents_insert
        from pathlib import Path

        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello world content here")

        # storage_path must be inside Path.home() so relative_to(Path.home()) works.
        storage_path = Path.home() / ".talkingrock" / "docs" / "doc-abc" / "test.txt"

        fake_chunk = MagicMock()
        fake_chunk.chunk_index = 0
        fake_chunk.page_number = None
        fake_chunk.section_title = None
        fake_chunk.content = "Hello world content here"

        fake_block = MagicMock()
        fake_block.id = "block-001"

        with (
            patch("cairn.rpc_handlers.documents.store_document", return_value=("doc-abc", storage_path)),
            patch("cairn.rpc_handlers.documents.extract_text", return_value=("Hello world content here", {})),
            patch("cairn.rpc_handlers.documents.save_extracted_text"),
            patch("cairn.rpc_handlers.documents.chunk_text", return_value=[fake_chunk]),
            patch("cairn.rpc_handlers.documents.blocks_db.create_block", return_value=fake_block),
            patch("cairn.rpc_handlers.documents.save_metadata"),
            patch("cairn.rpc_handlers.documents.handle_memory_index_batch", create=True),
        ):
            result = handle_documents_insert(_mock_db(), file_path=str(test_file))

        assert result["documentId"] == "doc-abc"
        assert result["fileName"] == "test.txt"
        assert result["chunkCount"] == 1

    def test_raises_rpc_error_when_store_raises_value_error(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_insert

        test_file = tmp_path / "doc.txt"
        test_file.write_text("content")

        with patch("cairn.rpc_handlers.documents.store_document", side_effect=ValueError("bad type")):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_insert(_mock_db(), file_path=str(test_file))

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_extraction_fails(self, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_insert
        from cairn.documents import DocumentExtractionError

        test_file = tmp_path / "bad.pdf"
        test_file.write_bytes(b"%PDF-corrupt")

        with (
            patch("cairn.rpc_handlers.documents.store_document", return_value=("doc-x", test_file)),
            patch(
                "cairn.rpc_handlers.documents.extract_text",
                side_effect=DocumentExtractionError("cannot parse"),
            ),
            patch("cairn.rpc_handlers.documents.delete_document"),
        ):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_insert(_mock_db(), file_path=str(test_file))

        assert exc_info.value.code == -32000


# =============================================================================
# handle_documents_list
# =============================================================================


class TestHandleDocumentsList:
    """handle_documents_list wraps list_documents results."""

    def test_returns_empty_list_when_no_documents_exist(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_list

        with patch("cairn.rpc_handlers.documents.list_documents", return_value=[]):
            result = handle_documents_list(_mock_db())

        assert result["documents"] == []
        assert result["count"] == 0

    def test_returns_document_list_with_metadata_fields(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_list

        fake_doc = MagicMock()
        fake_doc.document_id = "doc-1"
        fake_doc.file_name = "report.pdf"
        fake_doc.file_type = "pdf"
        fake_doc.file_size = 1024
        fake_doc.chunk_count = 5
        fake_doc.extracted_at = "2026-01-01T00:00:00Z"
        fake_doc.title = "Annual Report"
        fake_doc.author = "Alice"
        fake_doc.page_count = 10

        with patch("cairn.rpc_handlers.documents.list_documents", return_value=[fake_doc]):
            result = handle_documents_list(_mock_db())

        assert result["count"] == 1
        assert result["documents"][0]["documentId"] == "doc-1"
        assert result["documents"][0]["fileName"] == "report.pdf"

    def test_passes_act_id_to_list_documents(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_list

        with patch("cairn.rpc_handlers.documents.list_documents", return_value=[]) as mock_list:
            handle_documents_list(_mock_db(), act_id="act-42")

        mock_list.assert_called_once_with(act_id="act-42")


# =============================================================================
# handle_documents_get
# =============================================================================


class TestHandleDocumentsGet:
    """handle_documents_get returns full document metadata."""

    def test_raises_rpc_error_when_document_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_get

        with patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_get(_mock_db(), document_id="missing-doc")

        assert exc_info.value.code == -32602
        assert "Document not found" in exc_info.value.message

    def test_returns_document_metadata_when_found(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_get

        fake_meta = MagicMock()
        fake_meta.document_id = "doc-99"
        fake_meta.file_name = "notes.txt"
        fake_meta.file_type = "txt"
        fake_meta.file_size = 512
        fake_meta.chunk_count = 2
        fake_meta.storage_path = "/home/user/.talkingrock/docs/doc-99"
        fake_meta.extracted_at = "2026-01-01T00:00:00Z"
        fake_meta.act_id = None
        fake_meta.title = None
        fake_meta.author = None
        fake_meta.page_count = None
        fake_meta.extraction_metadata = {}

        with patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=fake_meta):
            result = handle_documents_get(_mock_db(), document_id="doc-99")

        assert result["documentId"] == "doc-99"
        assert result["fileName"] == "notes.txt"
        assert result["chunkCount"] == 2


# =============================================================================
# handle_documents_delete
# =============================================================================


class TestHandleDocumentsDelete:
    """handle_documents_delete removes document and associated chunk blocks."""

    def test_raises_rpc_error_when_document_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_delete

        with patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_delete(_mock_db(), document_id="ghost-doc")

        assert exc_info.value.code == -32602

    def test_returns_deleted_true_on_success(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_delete

        fake_meta = MagicMock()
        fake_meta.act_id = None

        fake_conn = MagicMock()
        fake_conn.execute.return_value = iter([])

        with (
            patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=fake_meta),
            patch("cairn.rpc_handlers.documents.delete_document", return_value=True),
            patch("cairn.play_db._get_connection", return_value=fake_conn),
        ):
            result = handle_documents_delete(_mock_db(), document_id="doc-del")

        assert result["deleted"] is True
        assert result["documentId"] == "doc-del"

    def test_raises_rpc_error_when_deletion_fails(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_delete

        fake_meta = MagicMock()
        fake_meta.act_id = None

        fake_conn = MagicMock()
        fake_conn.execute.return_value = iter([])

        with (
            patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=fake_meta),
            patch("cairn.rpc_handlers.documents.delete_document", return_value=False),
            patch("cairn.play_db._get_connection", return_value=fake_conn),
        ):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_delete(_mock_db(), document_id="fail-doc")

        assert exc_info.value.code == -32602


# =============================================================================
# handle_documents_get_chunks
# =============================================================================


class TestHandleDocumentsGetChunks:
    """handle_documents_get_chunks returns the chunk blocks for a document."""

    def test_raises_rpc_error_when_document_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.documents import handle_documents_get_chunks

        with patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_documents_get_chunks(_mock_db(), document_id="no-doc")

        assert exc_info.value.code == -32602

    def test_returns_empty_chunks_when_no_blocks_found(self) -> None:
        from cairn.rpc_handlers.documents import handle_documents_get_chunks

        fake_meta = MagicMock()
        fake_meta.document_id = "doc-1"
        fake_meta.file_name = "empty.txt"

        fake_conn = MagicMock()
        fake_conn.execute.return_value = iter([])

        with (
            patch("cairn.rpc_handlers.documents.get_document_metadata", return_value=fake_meta),
            patch("cairn.play_db._get_connection", return_value=fake_conn),
            patch("cairn.play_db.init_db"),
        ):
            result = handle_documents_get_chunks(_mock_db(), document_id="doc-1")

        assert result["documentId"] == "doc-1"
        assert result["chunks"] == []
        assert result["count"] == 0
