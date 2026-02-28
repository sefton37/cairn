"""Integration smoke tests for the Health Pulse framework.

Verifies end-to-end wiring: schema init, check registration, MCP tools,
RPC handler shapes, and behavior mode routing.

Run with: PYTHONPATH=src pytest tests/test_health_integration.py -v --no-cov
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cairn.cairn.store import CairnStore


@pytest.fixture
def store(tmp_path: Path) -> CairnStore:
    """Create a CairnStore with health tables initialized."""
    db_path = tmp_path / "cairn.db"
    return CairnStore(db_path)


# =========================================================================
# Schema wiring
# =========================================================================


def test_health_tables_created_by_cairn_store(store: CairnStore):
    """CairnStore init should create all health-related tables."""
    conn = store._get_connection()
    tables = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }

    # Anti-Nag tables
    assert "health_surfacing_log" in tables
    assert "health_check_config" in tables

    # Snapshot tables
    assert "health_snapshots" in tables
    assert "pattern_drift_events" in tables


def test_health_check_config_seeded(store: CairnStore):
    """Default health check config should be seeded."""
    conn = store._get_connection()
    rows = conn.execute("SELECT check_name FROM health_check_config").fetchall()
    check_names = {r[0] for r in rows}

    # Phase 1 checks should be in defaults
    assert "context_freshness" in check_names
    assert "act_vitality" in check_names
    assert "data_integrity" in check_names


# =========================================================================
# Runner + check registration
# =========================================================================


def test_runner_registers_all_phase_1_checks(store: CairnStore):
    """HealthCheckRunner should accept all Phase 1 checks."""
    from cairn.cairn.health.checks.act_vitality import ActVitalityCheck
    from cairn.cairn.health.checks.context_freshness import (
        ContextFreshnessCheck,
    )
    from cairn.cairn.health.checks.data_integrity import DataIntegrityCheck
    from cairn.cairn.health.runner import HealthCheckRunner

    runner = HealthCheckRunner()
    runner.register(ContextFreshnessCheck(store))
    runner.register(ActVitalityCheck(store))
    runner.register(DataIntegrityCheck(store.db_path))

    results = runner.run_all_checks()
    check_names = {r.check_name for r in results}

    assert "context_freshness" in check_names
    assert "act_vitality" in check_names
    assert "data_integrity" in check_names


def test_runner_registers_all_checks_without_error(store: CairnStore):
    """All Phase 1-4 checks should register without import errors."""
    from cairn.cairn.health.checks.act_vitality import ActVitalityCheck
    from cairn.cairn.health.checks.context_freshness import (
        ContextFreshnessCheck,
    )
    from cairn.cairn.health.checks.correction_intake import (
        CorrectionIntakeCheck,
    )
    from cairn.cairn.health.checks.data_integrity import DataIntegrityCheck
    from cairn.cairn.health.checks.pattern_currency import PatternCurrencyCheck
    from cairn.cairn.health.checks.preference_alignment import (
        PreferenceAlignmentCheck,
    )
    from cairn.cairn.health.checks.security_posture import (
        SecurityPostureCheck,
    )
    from cairn.cairn.health.checks.signal_quality import SignalQualityCheck
    from cairn.cairn.health.checks.software_currency import (
        SoftwareCurrencyCheck,
    )
    from cairn.cairn.health.runner import HealthCheckRunner

    runner = HealthCheckRunner()
    mock_db = MagicMock()

    # Phase 1
    runner.register(ContextFreshnessCheck(store))
    runner.register(ActVitalityCheck(store))
    runner.register(DataIntegrityCheck(store.db_path))

    # Phase 2
    runner.register(CorrectionIntakeCheck(mock_db))
    runner.register(SignalQualityCheck(mock_db))
    runner.register(PreferenceAlignmentCheck(store))

    # Phase 3
    runner.register(PatternCurrencyCheck(mock_db))

    # Phase 4
    runner.register(SoftwareCurrencyCheck())
    runner.register(SecurityPostureCheck())

    # Should run without crashing (some checks may warn on mock db)
    results = runner.run_all_checks()
    assert len(results) >= 9  # At least one result per check


# =========================================================================
# MCP tool wiring
# =========================================================================


def test_mcp_tools_include_all_health_tools():
    """list_tools() should include all 3 health MCP tools."""
    from cairn.cairn.mcp_tools import list_tools

    tools = list_tools()
    tool_names = {t.name for t in tools}

    assert "cairn_health_report" in tool_names
    assert "cairn_acknowledge_health" in tool_names
    assert "cairn_health_history" in tool_names


def test_mcp_health_report_returns_expected_shape(store: CairnStore):
    """cairn_health_report should return full_results, surfaced, summary."""
    from cairn.cairn.mcp_tools import CairnToolHandler

    handler = CairnToolHandler(store=store)
    result = handler.call_tool("cairn_health_report", {})

    assert "full_results" in result
    assert "surfaced_messages" in result
    assert "summary" in result
    assert isinstance(result["full_results"], list)
    assert isinstance(result["summary"], dict)


def test_mcp_health_history_returns_expected_shape(store: CairnStore):
    """cairn_health_history should return snapshots list."""
    from cairn.cairn.mcp_tools import CairnToolHandler

    handler = CairnToolHandler(store=store)
    result = handler.call_tool("cairn_health_history", {})

    assert "snapshots" in result
    assert isinstance(result["snapshots"], list)
    # No snapshots yet → should have a message
    assert "message" in result


def test_mcp_health_history_with_data(store: CairnStore):
    """cairn_health_history should return snapshot data when available."""
    from cairn.cairn.health.snapshot import create_daily_snapshot
    from cairn.cairn.mcp_tools import CairnToolHandler

    # Create a snapshot
    conn = store._get_connection()
    create_daily_snapshot(conn, {"test_metric": 42})

    handler = CairnToolHandler(store=store)
    result = handler.call_tool("cairn_health_history", {})

    assert "snapshots" in result
    assert len(result["snapshots"]) == 1
    assert result["count"] == 1
    assert result["snapshots"][0]["metrics"]["test_metric"] == 42


# =========================================================================
# RPC handler shapes
# =========================================================================


def test_rpc_health_status_returns_expected_shape(tmp_path: Path):
    """health/status RPC should return severity, counts."""
    from cairn.rpc_handlers.health import handle_health_status

    play_path = tmp_path / "play"
    play_path.mkdir()
    cairn_dir = play_path / ".cairn"
    cairn_dir.mkdir()
    CairnStore(cairn_dir / "cairn.db")

    mock_db = MagicMock()
    with patch(
        "cairn.rpc_handlers.health.get_current_play_path",
        return_value=str(play_path),
    ):
        result = handle_health_status(mock_db)

    assert "overall_severity" in result
    assert "finding_count" in result
    assert "unacknowledged_count" in result
    assert result["overall_severity"] in ("healthy", "warning", "critical")


def test_rpc_health_findings_returns_expected_shape(tmp_path: Path):
    """health/findings RPC should return findings list."""
    from cairn.rpc_handlers.health import handle_health_findings

    play_path = tmp_path / "play"
    play_path.mkdir()
    cairn_dir = play_path / ".cairn"
    cairn_dir.mkdir()
    CairnStore(cairn_dir / "cairn.db")

    mock_db = MagicMock()
    with patch(
        "cairn.rpc_handlers.health.get_current_play_path",
        return_value=str(play_path),
    ):
        result = handle_health_findings(mock_db)

    assert "findings" in result
    assert "overall_severity" in result
    assert "finding_count" in result
    assert isinstance(result["findings"], list)


# =========================================================================
# Behavior mode routing
# =========================================================================


def test_health_behavior_mode_selects_report_by_default():
    """Health mode should select cairn_health_report for generic queries."""
    from cairn.cairn.behavior_modes import _health_tool_selector

    ctx = MagicMock()
    ctx.user_input = "how am I doing?"

    assert _health_tool_selector(ctx) == "cairn_health_report"


def test_health_behavior_mode_selects_history_for_trends():
    """Health mode should select cairn_health_history for trend queries."""
    from cairn.cairn.behavior_modes import _health_tool_selector

    ctx = MagicMock()

    for query in [
        "show me health history",
        "health trends",
        "how have things changed over time",
        "show health snapshot",
    ]:
        ctx.user_input = query
        assert _health_tool_selector(ctx) == "cairn_health_history", (
            f"Failed for: {query}"
        )


def test_health_arg_extractor_parses_days():
    """Health arg extractor should parse days from user input."""
    from cairn.cairn.behavior_modes import _health_arg_extractor

    ctx = MagicMock()
    ctx.user_input = "show health trends for 60 days"

    args = _health_arg_extractor(ctx)
    assert args == {"days": 60}


def test_health_arg_extractor_returns_empty_for_no_number():
    """Health arg extractor should return empty dict with no number."""
    from cairn.cairn.behavior_modes import _health_arg_extractor

    ctx = MagicMock()
    ctx.user_input = "show me health history"

    args = _health_arg_extractor(ctx)
    assert args == {}


# =========================================================================
# Anti-Nag wiring
# =========================================================================


def test_anti_nag_round_trip(store: CairnStore):
    """Anti-Nag should log, retrieve, and acknowledge findings."""
    from cairn.cairn.health.anti_nag import AntiNagProtocol

    conn = store._get_connection()
    anti_nag = AntiNagProtocol(conn)

    # Should be surfaceable
    assert anti_nag.should_surface("test_check", "warning", "test:key")

    # Log it
    log_id = anti_nag.log_surfaced(
        "test_check", "warning", "test:key", "Test title", "Test details"
    )
    assert log_id

    # Should have unacknowledged
    assert anti_nag.get_unacknowledged_count() >= 1

    # Acknowledge
    assert anti_nag.acknowledge(log_id)

    # Should be acknowledged now
    row = conn.execute(
        "SELECT acknowledged FROM health_surfacing_log WHERE log_id = ?",
        (log_id,),
    ).fetchone()
    assert row[0] == 1
