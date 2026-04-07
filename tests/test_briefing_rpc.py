"""Unit tests for the briefing/ RPC handler functions.

Tests verify:
- handle_briefing_get returns current briefing or None when stale/absent
- handle_briefing_generate forces generation and returns fresh briefing
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _mock_db() -> MagicMock:
    return MagicMock()


def _make_service(current=None, generated=None) -> MagicMock:
    svc = MagicMock()
    if current is not None:
        current_briefing = MagicMock()
        current_briefing.to_dict.return_value = current
        svc.get_current.return_value = current_briefing
    else:
        svc.get_current.return_value = None

    if generated is not None:
        gen_briefing = MagicMock()
        gen_briefing.to_dict.return_value = generated
        svc.generate.return_value = gen_briefing

    return svc


# =============================================================================
# handle_briefing_get
# =============================================================================


class TestHandleBriefingGet:
    """handle_briefing_get returns cached briefing or None."""

    def test_returns_none_when_no_current_briefing(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_get

        svc = _make_service(current=None)

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            result = handle_briefing_get(_mock_db())

        assert result == {"briefing": None}

    def test_returns_briefing_dict_when_current_briefing_exists(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_get

        fake_briefing_data = {"summary": "All is well", "created_at": "2026-01-01T00:00:00Z"}
        svc = _make_service(current=fake_briefing_data)

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            result = handle_briefing_get(_mock_db())

        assert result["briefing"] == fake_briefing_data

    def test_calls_service_get_current(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_get

        svc = _make_service(current=None)

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            handle_briefing_get(_mock_db())

        svc.get_current.assert_called_once()


# =============================================================================
# handle_briefing_generate
# =============================================================================


class TestHandleBriefingGenerate:
    """handle_briefing_generate forces a fresh briefing via the service."""

    def test_returns_generated_briefing_dict(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_generate

        fake_briefing_data = {"summary": "New briefing", "created_at": "2026-01-02T00:00:00Z"}
        svc = _make_service(generated=fake_briefing_data)

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            result = handle_briefing_generate(_mock_db())

        assert result["briefing"] == fake_briefing_data

    def test_passes_manual_trigger_by_default(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_generate

        svc = _make_service(generated={"summary": "ok"})

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            handle_briefing_generate(_mock_db())

        svc.generate.assert_called_once_with(trigger="manual")

    def test_passes_custom_trigger_to_service(self) -> None:
        from cairn.rpc_handlers.briefing import handle_briefing_generate

        svc = _make_service(generated={"summary": "startup briefing"})

        with patch("cairn.rpc_handlers.briefing._get_service", return_value=svc):
            handle_briefing_generate(_mock_db(), trigger="app_start")

        svc.generate.assert_called_once_with(trigger="app_start")
