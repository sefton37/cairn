"""Tests for _format_health_report in cairn_integration.py.

The function formats a cairn_health_report tool result into a human-readable
string without calling an LLM — small models hallucinate hardware reports.

Coverage areas:
- Findings present via surfaced_messages: prefix, title, details are rendered
- Fallback to full_results when surfaced_messages is empty
- All Clear message when no non-healthy findings exist
- Empty tool_result dict does not raise
- Unknown severity defaults to [WARNING] prefix
"""

from __future__ import annotations

import pytest

from cairn.atomic_ops.cairn_integration import _format_health_report


# =============================================================================
# Happy path — surfaced_messages present
# =============================================================================


class TestSurfacedMessages:
    """When surfaced_messages is populated it is used as the findings list."""

    def test_uses_surfaced_messages_not_full_results(self) -> None:
        """surfaced_messages takes priority over full_results."""
        tool_result = {
            "surfaced_messages": [
                {
                    "severity": "warning",
                    "title": "High CPU",
                    "details": "CPU at 92%",
                    "finding_key": "cpu_high",
                }
            ],
            "full_results": [
                {
                    "severity": "critical",
                    "title": "Disk Full",
                    "details": "/ at 100%",
                    "finding_key": "disk_full",
                }
            ],
            "summary": {"checks_run": 5, "finding_count": 1, "overall_severity": "warning"},
        }

        report = _format_health_report(tool_result)

        assert "High CPU" in report
        assert "Disk Full" not in report

    def test_severity_warning_prefix_is_rendered(self) -> None:
        """A finding with severity 'warning' shows [WARNING] prefix."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "title": "Swap in use", "details": "4 GB swapped"}
            ],
            "summary": {"checks_run": 3, "finding_count": 1},
        }

        report = _format_health_report(tool_result)

        assert "[WARNING]" in report

    def test_severity_critical_prefix_is_rendered(self) -> None:
        """A finding with severity 'critical' shows [CRITICAL] prefix."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "critical", "title": "OOM Risk", "details": "Memory at 99%"}
            ],
            "summary": {"checks_run": 2, "finding_count": 1},
        }

        report = _format_health_report(tool_result)

        assert "[CRITICAL]" in report

    def test_title_appears_in_output(self) -> None:
        """The finding title is included in the report."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "title": "Load Average High", "details": ""}
            ],
        }

        report = _format_health_report(tool_result)

        assert "Load Average High" in report

    def test_details_appear_in_output_when_present(self) -> None:
        """Finding details are indented and included when non-empty."""
        tool_result = {
            "surfaced_messages": [
                {
                    "severity": "warning",
                    "title": "Fan Speed",
                    "details": "Fan running at 4200 RPM",
                }
            ],
        }

        report = _format_health_report(tool_result)

        assert "Fan running at 4200 RPM" in report

    def test_details_omitted_when_empty_string(self) -> None:
        """Empty details string produces no extra line for that finding."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "title": "No Detail Finding", "details": ""}
            ],
        }

        report = _format_health_report(tool_result)

        lines = report.splitlines()
        # The details line must not appear — only header line and footer line
        detail_lines = [l for l in lines if l.startswith("  ")]
        assert detail_lines == []

    def test_header_shows_finding_count(self) -> None:
        """Header line includes the number of findings from summary."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "title": "Issue A", "details": ""},
                {"severity": "critical", "title": "Issue B", "details": ""},
            ],
            "summary": {"checks_run": 10, "finding_count": 2},
        }

        report = _format_health_report(tool_result)

        assert "2 finding(s)" in report

    def test_footer_shows_checks_run_and_finding_count(self) -> None:
        """Footer line reports checks run and finding count from summary."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "title": "Temp High", "details": ""}
            ],
            "summary": {"checks_run": 7, "finding_count": 1},
        }

        report = _format_health_report(tool_result)

        assert "7 checks run" in report
        assert "1 findings" in report


# =============================================================================
# Fallback to full_results
# =============================================================================


class TestFallbackToFullResults:
    """When surfaced_messages is absent or empty, non-healthy full_results are used."""

    def test_empty_surfaced_messages_falls_back_to_full_results(self) -> None:
        """Empty surfaced_messages list causes full_results to supply findings."""
        tool_result = {
            "surfaced_messages": [],
            "full_results": [
                {"severity": "critical", "title": "Disk Nearly Full", "details": "95% used"},
                {"severity": "healthy", "title": "CPU OK", "details": ""},
            ],
            "summary": {"checks_run": 2, "finding_count": 1},
        }

        report = _format_health_report(tool_result)

        assert "Disk Nearly Full" in report

    def test_healthy_items_excluded_from_fallback(self) -> None:
        """full_results items with severity 'healthy' are filtered out."""
        tool_result = {
            "surfaced_messages": [],
            "full_results": [
                {"severity": "healthy", "title": "Memory OK", "details": ""},
                {"severity": "healthy", "title": "CPU OK", "details": ""},
            ],
        }

        report = _format_health_report(tool_result)

        assert "Memory OK" not in report
        assert "CPU OK" not in report

    def test_absent_surfaced_messages_key_falls_back_to_full_results(self) -> None:
        """Missing surfaced_messages key is treated the same as an empty list."""
        tool_result = {
            "full_results": [
                {"severity": "warning", "title": "Entropy Low", "details": "Only 128 bytes"}
            ],
        }

        report = _format_health_report(tool_result)

        assert "Entropy Low" in report

    def test_fallback_checks_run_derived_from_full_results_length(self) -> None:
        """When summary is absent, checks_run falls back to len(full_results)."""
        tool_result = {
            "full_results": [
                {"severity": "warning", "title": "Temp", "details": ""},
                {"severity": "healthy", "title": "RAM", "details": ""},
                {"severity": "healthy", "title": "Net", "details": ""},
            ],
        }

        report = _format_health_report(tool_result)

        assert "3 checks run" in report


# =============================================================================
# All Clear
# =============================================================================


class TestAllClear:
    """When there are no findings the report says All Clear."""

    def test_all_clear_header_when_no_findings(self) -> None:
        """No findings produces 'All Clear' header."""
        tool_result = {
            "surfaced_messages": [],
            "full_results": [
                {"severity": "healthy", "title": "CPU", "details": ""},
                {"severity": "healthy", "title": "Memory", "details": ""},
            ],
            "summary": {"checks_run": 2, "finding_count": 0},
        }

        report = _format_health_report(tool_result)

        assert "All Clear" in report

    def test_all_clear_still_shows_footer(self) -> None:
        """All Clear report still reports how many checks were run."""
        tool_result = {
            "surfaced_messages": [],
            "full_results": [],
            "summary": {"checks_run": 4, "finding_count": 0},
        }

        report = _format_health_report(tool_result)

        assert "4 checks run" in report
        assert "0 findings" in report

    def test_no_severity_prefixes_when_all_clear(self) -> None:
        """No [WARNING] or [CRITICAL] prefix appears when there are no findings."""
        tool_result = {
            "surfaced_messages": [],
            "full_results": [{"severity": "healthy", "title": "OK", "details": ""}],
        }

        report = _format_health_report(tool_result)

        assert "[WARNING]" not in report
        assert "[CRITICAL]" not in report


# =============================================================================
# Empty tool_result
# =============================================================================


class TestEmptyToolResult:
    """An empty dict must not raise — graceful defaults apply."""

    def test_empty_dict_does_not_raise(self) -> None:
        """_format_health_report({}) completes without exception."""
        report = _format_health_report({})

        assert isinstance(report, str)

    def test_empty_dict_produces_all_clear(self) -> None:
        """With no data, the report shows All Clear."""
        report = _format_health_report({})

        assert "All Clear" in report

    def test_empty_dict_footer_shows_zero_checks(self) -> None:
        """Footer defaults to 0 checks when full_results is absent."""
        report = _format_health_report({})

        assert "0 checks run" in report


# =============================================================================
# Unknown severity defaults to [WARNING]
# =============================================================================


class TestUnknownSeverity:
    """Severity values not in the prefix map fall back to [WARNING]."""

    def test_unknown_severity_uses_warning_prefix(self) -> None:
        """A severity string not in _SEVERITY_PREFIX maps to [WARNING]."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "notice", "title": "Something odd", "details": ""}
            ],
        }

        report = _format_health_report(tool_result)

        assert "[WARNING]" in report

    def test_missing_severity_key_uses_warning_prefix(self) -> None:
        """A finding dict with no 'severity' key defaults to [WARNING]."""
        tool_result = {
            "surfaced_messages": [
                {"title": "No Severity Key", "details": "Details here"}
            ],
        }

        report = _format_health_report(tool_result)

        assert "[WARNING]" in report

    def test_missing_title_uses_unknown_issue_fallback(self) -> None:
        """A finding dict with no 'title' key shows 'Unknown issue'."""
        tool_result = {
            "surfaced_messages": [
                {"severity": "warning", "details": "Something happened"}
            ],
        }

        report = _format_health_report(tool_result)

        assert "Unknown issue" in report
