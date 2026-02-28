"""Tests for Software Currency health check.

Run with: PYTHONPATH=src pytest tests/test_health_software_currency.py -v --no-cov
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from cairn.cairn.health.checks.software_currency import SoftwareCurrencyCheck
from cairn.cairn.health.runner import Severity


def test_provider_available_returns_healthy():
    """Check should return healthy when Ollama provider is available."""
    check = SoftwareCurrencyCheck()

    mock_health = {"available": True}
    with patch(
        "cairn.providers.factory.check_provider_health",
        return_value=mock_health,
    ):
        results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Ollama provider is available" in results[0].title
    assert results[0].finding_key == "software_currency:ollama:ok"


def test_provider_unavailable_returns_warning():
    """Check should return warning when provider is not available."""
    check = SoftwareCurrencyCheck()

    mock_health = {"available": False, "error": "Connection refused"}
    with patch(
        "cairn.providers.factory.check_provider_health",
        return_value=mock_health,
    ):
        results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "Ollama provider is not available" in results[0].title
    assert "Connection refused" in results[0].details
    assert results[0].finding_key == "software_currency:ollama:unavailable"


def test_provider_unavailable_without_error_message():
    """Check should handle missing error key gracefully."""
    check = SoftwareCurrencyCheck()

    mock_health = {"available": False}
    with patch(
        "cairn.providers.factory.check_provider_health",
        return_value=mock_health,
    ):
        results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "Unknown error" in results[0].details


def test_import_error_returns_healthy():
    """Check should return healthy when provider module cannot be imported."""
    check = SoftwareCurrencyCheck()

    # Mock the import statement itself to raise ImportError
    import sys
    with patch.dict(sys.modules, {"cairn.providers.factory": None}):
        results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "Provider health check not available" in results[0].title
    assert results[0].finding_key == "software_currency:no_provider"


def test_generic_exception_returns_warning():
    """Check should return warning on unexpected exceptions."""
    check = SoftwareCurrencyCheck()

    with patch(
        "cairn.providers.factory.check_provider_health",
        side_effect=RuntimeError("Unexpected error"),
    ):
        results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.WARNING
    assert "Could not check provider health" in results[0].title
    assert "Unexpected error" in results[0].details
    assert results[0].finding_key == "software_currency:error"


def test_check_name_property():
    """Check should have correct name property."""
    check = SoftwareCurrencyCheck()
    assert check.name == "software_currency"


def test_run_returns_list():
    """run() should always return a list of results."""
    check = SoftwareCurrencyCheck()

    mock_health = {"available": True}
    with patch(
        "cairn.providers.factory.check_provider_health",
        return_value=mock_health,
    ):
        results = check.run()

    assert isinstance(results, list)
    assert all(hasattr(r, "severity") for r in results)


def test_check_uses_factory_check_provider_health():
    """Check should use check_provider_health from factory module."""
    check = SoftwareCurrencyCheck()

    mock_check = MagicMock(return_value={"available": True})
    with patch(
        "cairn.providers.factory.check_provider_health",
        mock_check,
    ):
        check.run()

    mock_check.assert_called_once_with()
