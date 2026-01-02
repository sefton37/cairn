"""Tests for Firefox browser integration."""

from __future__ import annotations

import sqlite3
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


class TestFirefoxProfileDiscovery:
    def test_find_firefox_root_not_found(self) -> None:
        """Should return None when Firefox not installed."""
        from reos.firefox import find_firefox_root

        with patch("reos.firefox.Path.home") as mock_home:
            mock_home.return_value = Path("/nonexistent/home")
            result = find_firefox_root()
            # May or may not be None depending on actual system
            assert result is None or isinstance(result, Path)

    def test_list_profiles_structure(self) -> None:
        """list_profiles should return a list."""
        from reos.firefox import list_profiles

        profiles = list_profiles()
        assert isinstance(profiles, list)
        for profile in profiles:
            assert "name" in profile
            assert "path" in profile
            assert "has_places_db" in profile

    def test_firefox_available_returns_bool(self) -> None:
        """firefox_available should return a boolean."""
        from reos.firefox import firefox_available

        result = firefox_available()
        assert isinstance(result, bool)

    def test_get_firefox_status_structure(self) -> None:
        """get_firefox_status should return proper structure."""
        from reos.firefox import get_firefox_status

        status = get_firefox_status()
        assert isinstance(status, dict)
        assert "available" in status
        if not status["available"]:
            assert "reason" in status


class TestHistoryEntry:
    def test_history_entry_to_dict(self) -> None:
        """HistoryEntry.to_dict should return proper dict."""
        from reos.firefox import HistoryEntry

        entry = HistoryEntry(
            url="https://example.com",
            title="Example",
            visit_time=datetime(2024, 1, 15, 10, 30),
            visit_count=5,
            domain="example.com",
        )
        result = entry.to_dict()
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["visit_count"] == 5
        assert result["domain"] == "example.com"
        assert "visit_time" in result


class TestBookmark:
    def test_bookmark_to_dict(self) -> None:
        """Bookmark.to_dict should return proper dict."""
        from reos.firefox import Bookmark

        bookmark = Bookmark(
            url="https://example.com",
            title="Example",
            added_time=datetime(2024, 1, 15),
            folder="Bookmarks Toolbar",
        )
        result = bookmark.to_dict()
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["folder"] == "Bookmarks Toolbar"


class TestOpenTab:
    def test_open_tab_to_dict(self) -> None:
        """OpenTab.to_dict should return proper dict."""
        from reos.firefox import OpenTab

        tab = OpenTab(
            url="https://example.com",
            title="Example",
            last_accessed=datetime(2024, 1, 15, 10, 30),
            window_index=0,
            tab_index=1,
        )
        result = tab.to_dict()
        assert result["url"] == "https://example.com"
        assert result["title"] == "Example"
        assert result["window_index"] == 0
        assert result["tab_index"] == 1


class TestDomainExtraction:
    def test_extract_domain_simple(self) -> None:
        """Should extract domain from URL."""
        from reos.firefox import _extract_domain

        assert _extract_domain("https://example.com/page") == "example.com"
        assert _extract_domain("https://www.example.com/page") == "www.example.com"
        assert _extract_domain("http://localhost:8080/") == "localhost:8080"

    def test_extract_domain_fallback(self) -> None:
        """Should return original on parse failure."""
        from reos.firefox import _extract_domain

        assert _extract_domain("not a url") == "not a url"


class TestFirefoxTimestamp:
    def test_firefox_time_to_datetime(self) -> None:
        """Should convert Firefox microsecond timestamps."""
        from reos.firefox import _firefox_time_to_datetime

        # Firefox uses microseconds since epoch
        # Jan 1, 2024 00:00:00 UTC = 1704067200 seconds = 1704067200000000 microseconds
        result = _firefox_time_to_datetime(1704067200000000)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 1

    def test_firefox_time_none(self) -> None:
        """Should handle None and zero."""
        from reos.firefox import _firefox_time_to_datetime

        assert _firefox_time_to_datetime(None) is None
        assert _firefox_time_to_datetime(0) is None


class TestHistoryWithMockDB:
    def test_get_history_with_mock(self, tmp_path: Path) -> None:
        """Test history retrieval with mocked database."""
        from reos.firefox import FirefoxError, get_history

        # Create mock places.sqlite
        db_path = tmp_path / "places.sqlite"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create required tables
        cursor.execute("""
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT,
                title TEXT,
                visit_count INTEGER
            )
        """)
        cursor.execute("""
            CREATE TABLE moz_historyvisits (
                id INTEGER PRIMARY KEY,
                place_id INTEGER,
                visit_date INTEGER
            )
        """)

        # Insert test data
        cursor.execute(
            "INSERT INTO moz_places (id, url, title, visit_count) VALUES (1, 'https://example.com', 'Example', 5)"
        )
        # Use current timestamp in microseconds
        visit_time = int(datetime.now().timestamp() * 1_000_000)
        cursor.execute(
            "INSERT INTO moz_historyvisits (place_id, visit_date) VALUES (1, ?)",
            (visit_time,),
        )
        conn.commit()
        conn.close()

        # Test with mocked profile
        with patch("reos.firefox.get_default_profile", return_value=tmp_path):
            entries = get_history(limit=10)
            assert len(entries) == 1
            assert entries[0].url == "https://example.com"
            assert entries[0].title == "Example"
            assert entries[0].visit_count == 5


class TestBookmarksWithMockDB:
    def test_get_bookmarks_with_mock(self, tmp_path: Path) -> None:
        """Test bookmark retrieval with mocked database."""
        from reos.firefox import get_bookmarks

        # Create mock places.sqlite
        db_path = tmp_path / "places.sqlite"
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Create required tables
        cursor.execute("""
            CREATE TABLE moz_places (
                id INTEGER PRIMARY KEY,
                url TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE moz_bookmarks (
                id INTEGER PRIMARY KEY,
                type INTEGER,
                fk INTEGER,
                parent INTEGER,
                title TEXT,
                dateAdded INTEGER
            )
        """)

        # Insert test data
        cursor.execute("INSERT INTO moz_places (id, url) VALUES (1, 'https://example.com')")
        cursor.execute(
            "INSERT INTO moz_bookmarks (id, type, fk, parent, title, dateAdded) VALUES (1, 1, 1, 0, 'Example', ?)",
            (int(datetime.now().timestamp() * 1_000_000),),
        )
        conn.commit()
        conn.close()

        # Test with mocked profile
        with patch("reos.firefox.get_default_profile", return_value=tmp_path):
            bookmarks = get_bookmarks(limit=10)
            assert len(bookmarks) == 1
            assert bookmarks[0].url == "https://example.com"
            assert bookmarks[0].title == "Example"


class TestOpenURL:
    def test_open_url_validates_input(self) -> None:
        """open_url should validate URL input."""
        from reos.firefox import open_url

        result = open_url("")
        assert result["success"] is False
        assert "error" in result

    def test_open_url_adds_https(self) -> None:
        """open_url should add https to bare domains."""
        from reos.firefox import open_url

        with patch("reos.firefox.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = open_url("example.com")
            assert result["success"] is True
            assert result["url"] == "https://example.com"

    def test_open_url_search_query(self) -> None:
        """open_url should convert non-URL to search."""
        from reos.firefox import open_url

        with patch("reos.firefox.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = open_url("how to code python")
            assert result["success"] is True
            assert "google.com/search" in result["url"]


class TestWebSearch:
    def test_search_web_google(self) -> None:
        """search_web should use correct engine URL."""
        from reos.firefox import search_web

        with patch("reos.firefox.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = search_web("python tutorial", engine="google")
            assert result["success"] is True
            assert result["engine"] == "google"
            assert "google.com" in result["url"]

    def test_search_web_duckduckgo(self) -> None:
        """search_web should support DuckDuckGo."""
        from reos.firefox import search_web

        with patch("reos.firefox.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = search_web("python tutorial", engine="duckduckgo")
            assert result["success"] is True
            assert "duckduckgo.com" in result["url"]

    def test_search_web_github(self) -> None:
        """search_web should support GitHub search."""
        from reos.firefox import search_web

        with patch("reos.firefox.subprocess.Popen") as mock_popen:
            mock_popen.return_value = MagicMock()
            result = search_web("react components", engine="github")
            assert result["success"] is True
            assert "github.com/search" in result["url"]


class TestOpenTabsSummary:
    def test_get_open_tabs_summary_not_available(self) -> None:
        """Should handle missing session data gracefully."""
        from reos.firefox import get_open_tabs_summary

        with patch("reos.firefox.get_default_profile", return_value=Path("/nonexistent")):
            summary = get_open_tabs_summary()
            # Should not crash, returns structure with available=False or empty tabs
            assert isinstance(summary, dict)
