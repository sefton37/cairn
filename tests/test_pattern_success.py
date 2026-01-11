"""Tests for pattern success tracking.

Tests the PatternStats class and pattern trust calculation
without requiring database integration.
"""

from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from reos.code_mode.intention import Action, ActionType
from reos.code_mode.optimization.pattern_success import (
    PatternStats,
    PatternSuccessTracker,
)


class TestPatternStats:
    """Test PatternStats dataclass."""

    def test_create_pattern_stats(self) -> None:
        """Basic pattern stats creation."""
        stats = PatternStats(
            pattern_hash="abc123",
            description="add import statement",
        )

        assert stats.pattern_hash == "abc123"
        assert stats.description == "add import statement"
        assert stats.attempts == 0
        assert stats.successes == 0
        assert stats.failures == 0

    def test_success_rate_empty(self) -> None:
        """Success rate with no attempts should be 0.5 (prior)."""
        stats = PatternStats(pattern_hash="test", description="test")

        assert stats.success_rate == 0.5

    def test_success_rate_calculation(self) -> None:
        """Success rate should be successes / attempts."""
        stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=10,
            successes=8,
            failures=2,
        )

        assert stats.success_rate == 0.8

    def test_record_success(self) -> None:
        """Recording success should increment counts."""
        stats = PatternStats(pattern_hash="test", description="test")

        stats.record_success()

        assert stats.attempts == 1
        assert stats.successes == 1
        assert stats.failures == 0
        assert stats.last_success is not None

    def test_record_failure(self) -> None:
        """Recording failure should increment counts."""
        stats = PatternStats(pattern_hash="test", description="test")

        stats.record_failure()

        assert stats.attempts == 1
        assert stats.successes == 0
        assert stats.failures == 1
        assert stats.last_failure is not None

    def test_multiple_outcomes(self) -> None:
        """Multiple success/failure recordings."""
        stats = PatternStats(pattern_hash="test", description="test")

        stats.record_success()
        stats.record_success()
        stats.record_failure()
        stats.record_success()

        assert stats.attempts == 4
        assert stats.successes == 3
        assert stats.failures == 1
        assert stats.success_rate == 0.75


class TestPatternTrustLevel:
    """Test trust level calculation with various factors."""

    def test_trust_level_high_success(self) -> None:
        """High success rate with many attempts = high trust."""
        stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=20,
            successes=19,
            failures=1,
            last_success=datetime.now(timezone.utc),
        )

        # 95% success, recent, many attempts
        assert stats.trust_level >= 0.85

    def test_trust_level_few_attempts(self) -> None:
        """Few attempts should reduce trust."""
        stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=2,
            successes=2,
            failures=0,
            last_success=datetime.now(timezone.utc),
        )

        # 100% success but only 2 attempts
        # Should be lower due to insufficient data
        assert stats.trust_level < 0.8

    def test_trust_level_moderate_attempts(self) -> None:
        """Moderate attempts (3-9) should have partial penalty."""
        stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=5,
            successes=5,
            failures=0,
            last_success=datetime.now(timezone.utc),
        )

        # 100% success with 5 attempts
        trust = stats.trust_level
        # Should be > few attempts trust but < many attempts trust
        assert 0.7 < trust < 0.95

    def test_trust_level_capped_at_95(self) -> None:
        """Trust should never exceed 0.95 (never fully trust)."""
        stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=1000,
            successes=1000,
            failures=0,
            last_success=datetime.now(timezone.utc),
        )

        # Perfect success rate, many attempts
        assert stats.trust_level <= 0.95

    def test_trust_decays_without_recent_success(self) -> None:
        """Trust should decay if last success was long ago."""
        recent_stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=20,
            successes=18,
            failures=2,
            last_success=datetime.now(timezone.utc),
        )

        old_stats = PatternStats(
            pattern_hash="test",
            description="test",
            attempts=20,
            successes=18,
            failures=2,
            last_success=datetime.now(timezone.utc) - timedelta(days=60),
        )

        # Same success rate, but old success = lower trust
        assert old_stats.trust_level < recent_stats.trust_level


class TestPatternStatsSerialization:
    """Test serialization and deserialization."""

    def test_to_dict(self) -> None:
        """to_dict should include all fields."""
        now = datetime.now(timezone.utc)
        stats = PatternStats(
            pattern_hash="abc123",
            description="test pattern",
            attempts=10,
            successes=8,
            failures=2,
            first_seen=now,
            last_success=now,
        )

        data = stats.to_dict()

        assert data["pattern_hash"] == "abc123"
        assert data["description"] == "test pattern"
        assert data["attempts"] == 10
        assert data["successes"] == 8
        assert data["failures"] == 2
        assert data["success_rate"] == 0.8
        assert "trust_level" in data

    def test_from_dict(self) -> None:
        """from_dict should restore PatternStats."""
        data = {
            "pattern_hash": "xyz789",
            "description": "restored pattern",
            "attempts": 15,
            "successes": 12,
            "failures": 3,
            "first_seen": "2025-01-01T00:00:00+00:00",
            "last_success": "2025-01-10T00:00:00+00:00",
            "last_failure": "2025-01-05T00:00:00+00:00",
        }

        stats = PatternStats.from_dict(data)

        assert stats.pattern_hash == "xyz789"
        assert stats.description == "restored pattern"
        assert stats.attempts == 15
        assert stats.successes == 12
        assert stats.failures == 3

    def test_roundtrip(self) -> None:
        """Serialize then deserialize should preserve data."""
        original = PatternStats(
            pattern_hash="roundtrip",
            description="test roundtrip",
            attempts=5,
            successes=4,
            failures=1,
        )
        original.record_success()

        data = original.to_dict()
        restored = PatternStats.from_dict(data)

        assert restored.pattern_hash == original.pattern_hash
        assert restored.attempts == original.attempts
        assert restored.successes == original.successes


class TestPatternTrackerHashing:
    """Test pattern hashing logic using mock database."""

    def test_hash_pattern_deterministic(self) -> None:
        """Same action should produce same hash."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        action = Action(
            type=ActionType.EDIT,
            content="import os",
            target="utils.py",
        )

        hash1 = tracker._hash_pattern(action)
        hash2 = tracker._hash_pattern(action)

        assert hash1 == hash2

    def test_hash_different_actions(self) -> None:
        """Different actions should produce different hashes."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        action1 = Action(
            type=ActionType.EDIT,
            content="import os",
            target="utils.py",
        )
        action2 = Action(
            type=ActionType.CREATE,
            content="class MyClass: pass",
            target="models.py",
        )

        hash1 = tracker._hash_pattern(action1)
        hash2 = tracker._hash_pattern(action2)

        assert hash1 != hash2

    def test_hash_similar_patterns(self) -> None:
        """Similar patterns (same extension) should hash similarly."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        action1 = Action(
            type=ActionType.EDIT,
            content="import os",
            target="utils.py",
        )
        action2 = Action(
            type=ActionType.EDIT,
            content="import os",
            target="helpers.py",
        )

        # Same type, same content, same extension pattern
        hash1 = tracker._hash_pattern(action1)
        hash2 = tracker._hash_pattern(action2)

        # Should be same (both are EDIT on *.py with same content)
        assert hash1 == hash2


class TestPatternTrackerNormalization:
    """Test content normalization for pattern matching."""

    def test_normalize_removes_string_literals(self) -> None:
        """String literals should be normalized."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        content = 'print("Hello World")'
        normalized = tracker._normalize_content(content)

        assert "Hello World" not in normalized
        assert '""' in normalized

    def test_normalize_removes_numbers(self) -> None:
        """Numbers should be normalized to N."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        content = "x = 12345"
        normalized = tracker._normalize_content(content)

        assert "12345" not in normalized
        assert "N" in normalized

    def test_normalize_collapses_whitespace(self) -> None:
        """Whitespace should be collapsed."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        content = "def   foo(   x,   y   ):"
        normalized = tracker._normalize_content(content)

        assert "   " not in normalized


class TestPatternTrackerIntegration:
    """Test pattern tracker with mock database."""

    def test_record_and_retrieve(self) -> None:
        """Record outcome and check trust level."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        action = Action(
            type=ActionType.EDIT,
            content="import json",
            target="utils.py",
        )

        # Record several successes
        for _ in range(10):
            tracker.record_outcome(action, success=True)

        trust = tracker.get_trust_level(action)

        # Should have high trust after 10 successes
        assert trust > 0.7

    def test_should_skip_verification(self) -> None:
        """should_skip_verification requires >0.9 trust."""
        mock_db = MockDatabase()
        tracker = PatternSuccessTracker(mock_db, "/repo")

        action = Action(
            type=ActionType.EDIT,
            content="import os",
            target="test.py",
        )

        # Initially, no data = 0.5 trust
        assert tracker.should_skip_verification(action) is False

        # Add many successes
        for _ in range(20):
            tracker.record_outcome(action, success=True)

        # Now should be able to skip
        # (Note: depends on trust calculation, may still be False if capped)
        trust = tracker.get_trust_level(action)
        skip = tracker.should_skip_verification(action)

        # If trust > 0.9, should skip
        assert (trust > 0.9) == skip


class MockDatabase:
    """Mock database for testing without real SQLite."""

    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}
        self._data: dict[str, dict] = {}

    def execute(self, sql: str, params: tuple = ()) -> None:
        """Execute SQL (store in memory)."""
        if "CREATE TABLE" in sql:
            # Table creation - no-op
            pass
        elif "INSERT OR REPLACE" in sql:
            # Store in memory by pattern_hash
            if len(params) >= 2:
                key = f"{params[0]}:{params[1]}"  # pattern_hash:repo_path
                self._data[key] = {
                    "pattern_hash": params[0],
                    "repo_path": params[1],
                    "description": params[2] if len(params) > 2 else "",
                    "attempts": params[3] if len(params) > 3 else 0,
                    "successes": params[4] if len(params) > 4 else 0,
                    "failures": params[5] if len(params) > 5 else 0,
                    "first_seen": params[6] if len(params) > 6 else None,
                    "last_success": params[7] if len(params) > 7 else None,
                    "last_failure": params[8] if len(params) > 8 else None,
                }

    def fetchone(self, sql: str, params: tuple = ()) -> dict | None:
        """Fetch one row."""
        if len(params) >= 2:
            key = f"{params[0]}:{params[1]}"
            return self._data.get(key)
        return None

    def fetchall(self, sql: str, params: tuple = ()) -> list:
        """Fetch all matching rows."""
        return list(self._data.values())
