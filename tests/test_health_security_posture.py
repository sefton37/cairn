"""Tests for Security Posture health check.

Run with: PYTHONPATH=src pytest tests/test_health_security_posture.py -v --no-cov
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from cairn.cairn.health.checks.security_posture import SecurityPostureCheck
from cairn.cairn.health.runner import Severity


def test_no_cloud_api_keys_returns_healthy(monkeypatch, tmp_path: Path):
    """Check should return healthy when no cloud API keys are set."""
    # Clear all environment variables
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GOOGLE_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    # Create a secure data directory
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "local-only confirmed" in results[0].title
    assert results[0].finding_key == "security_posture:ok"


def test_anthropic_api_key_returns_warning(monkeypatch, tmp_path: Path):
    """Check should return warning when ANTHROPIC_API_KEY is set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test123")

    # Create secure data directory
    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API key warning + permissions healthy
    assert len(results) == 2
    api_key_result = [r for r in results if "API key" in r.title][0]
    assert api_key_result.severity == Severity.WARNING
    assert "ANTHROPIC_API_KEY" in api_key_result.title
    assert "local-only operation" in api_key_result.details
    assert "ANTHROPIC_API_KEY" in api_key_result.finding_key


def test_multiple_api_keys_returns_warning_listing_all(monkeypatch, tmp_path: Path):
    """Check should list all detected cloud API keys in warning."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-test")
    monkeypatch.setenv("COHERE_API_KEY", "cohere-test")

    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API key warning + permissions healthy
    assert len(results) == 2
    api_key_result = [r for r in results if "API key" in r.title][0]
    assert api_key_result.severity == Severity.WARNING
    assert "ANTHROPIC_API_KEY" in api_key_result.title
    assert "OPENAI_API_KEY" in api_key_result.title
    assert "COHERE_API_KEY" in api_key_result.title


def test_empty_api_key_treated_as_not_set(monkeypatch, tmp_path: Path):
    """Check should treat empty string API key value as not set."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "")

    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Empty string is falsy, so os.environ.get returns truthy check fails
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY


def test_data_dir_with_0700_returns_healthy(monkeypatch, tmp_path: Path):
    """Check should return healthy for data directory with 0700 permissions."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "secure_data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "local-only confirmed" in results[0].title


def test_data_dir_with_0755_returns_warning(monkeypatch, tmp_path: Path):
    """Check should return warning for data directory with group/other access."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "open_data"
    data_dir.mkdir()
    os.chmod(data_dir, 0o755)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API keys healthy + permissions warning
    assert len(results) == 2
    perms_result = [r for r in results if "permissions" in r.title][0]
    assert perms_result.severity == Severity.WARNING
    assert "permissions too open" in perms_result.title
    assert "0o755" in perms_result.title
    assert "chmod 700" in perms_result.details


def test_data_dir_does_not_exist_returns_healthy(monkeypatch, tmp_path: Path):
    """Check should return healthy when data directory doesn't exist yet."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "nonexistent"

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return combined healthy result when all checks pass
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "local-only confirmed" in results[0].title
    assert results[0].finding_key == "security_posture:ok"


def test_data_dir_stat_fails_returns_healthy(monkeypatch, tmp_path: Path):
    """Check should return healthy gracefully when stat() fails."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    check = SecurityPostureCheck(data_dir=data_dir)

    # Mock stat to raise OSError after exists() check passes
    original_stat = Path.stat

    def stat_with_error(self, *args, **kwargs):
        # Allow exists() check to pass (first call)
        # Then raise error for the actual stat() call
        if not hasattr(stat_with_error, "called_count"):
            stat_with_error.called_count = 0
        stat_with_error.called_count += 1

        if stat_with_error.called_count > 1:
            raise OSError("Permission denied")
        return original_stat(self, *args, **kwargs)

    with patch.object(Path, "stat", stat_with_error):
        results = check.run()

    # Should return combined healthy result (API keys healthy + perms check failed gracefully)
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "local-only confirmed" in results[0].title
    assert results[0].finding_key == "security_posture:ok"


def test_no_data_dir_configured_returns_healthy(monkeypatch):
    """Check should return healthy when data_dir is not configured."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    # Don't pass data_dir, mock settings import to fail
    check = SecurityPostureCheck(data_dir=None)

    # The implementation catches Exception, so any exception during settings import is caught
    # We can just mock sys.modules to make the import fail
    import sys
    with patch.dict(sys.modules, {"cairn.settings": None}):
        results = check.run()

    # Should return combined healthy result (all checks pass)
    assert len(results) == 1
    assert results[0].severity == Severity.HEALTHY
    assert "local-only confirmed" in results[0].title
    assert results[0].finding_key == "security_posture:ok"


def test_combined_api_key_and_permissions_issues(monkeypatch, tmp_path: Path):
    """Check should return individual results when multiple issues found."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    os.chmod(data_dir, 0o755)

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results (one for API key, one for permissions)
    # Not the combined healthy result
    assert len(results) == 2
    assert all(r.severity == Severity.WARNING for r in results)
    assert any("OPENAI_API_KEY" in r.title for r in results)
    assert any("permissions too open" in r.title for r in results)


def test_all_cloud_api_key_types_detected(monkeypatch, tmp_path: Path):
    """Check should detect all documented cloud API key types."""
    keys_to_test = [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "AZURE_OPENAI_API_KEY",
        "COHERE_API_KEY",
        "HUGGINGFACE_API_KEY",
    ]

    data_dir = tmp_path / "data"
    data_dir.mkdir(mode=0o700)

    for key in keys_to_test:
        monkeypatch.setenv(key, f"test-{key.lower()}")

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API key warning + permissions healthy
    assert len(results) == 2
    api_key_result = [r for r in results if "API key" in r.title][0]
    assert api_key_result.severity == Severity.WARNING
    for key in keys_to_test:
        assert key in api_key_result.title


def test_check_name_property():
    """Check should have correct name property."""
    check = SecurityPostureCheck()
    assert check.name == "security_posture"


def test_finding_keys_use_check_name_prefix():
    """All finding keys should start with check name."""
    check = SecurityPostureCheck()

    # Test various paths through the check
    results = check.run()

    for result in results:
        assert result.finding_key.startswith("security_posture:")


def test_data_dir_with_group_access_only(monkeypatch, tmp_path: Path):
    """Check should warn when only group has access (no other)."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    os.chmod(data_dir, 0o750)  # Owner rwx, group rx, other none

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API keys healthy + permissions warning
    assert len(results) == 2
    perms_result = [r for r in results if "permissions" in r.title][0]
    assert perms_result.severity == Severity.WARNING
    assert "permissions too open" in perms_result.title


def test_data_dir_with_other_access_only(monkeypatch, tmp_path: Path):
    """Check should warn when only other has access (no group)."""
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        monkeypatch.delenv(key, raising=False)

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    os.chmod(data_dir, 0o705)  # Owner rwx, group none, other rx

    check = SecurityPostureCheck(data_dir=data_dir)
    results = check.run()

    # Should return 2 results: API keys healthy + permissions warning
    assert len(results) == 2
    perms_result = [r for r in results if "permissions" in r.title][0]
    assert perms_result.severity == Severity.WARNING
    assert "permissions too open" in perms_result.title
