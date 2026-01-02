"""Firefox browser integration for ReOS.

Provides read-only access to Firefox browsing history, bookmarks, and open tabs.
Also supports opening URLs in Firefox.

Privacy note: This module reads local Firefox data. No data is sent externally.
All browsing data stays on the user's machine.
"""

from __future__ import annotations

import json
import lzma
import shutil
import sqlite3
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


class FirefoxError(Exception):
    """Error accessing Firefox data."""


@dataclass(frozen=True)
class HistoryEntry:
    """A single browser history entry."""

    url: str
    title: str | None
    visit_time: datetime
    visit_count: int
    domain: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "visit_time": self.visit_time.isoformat(),
            "visit_count": self.visit_count,
            "domain": self.domain,
        }


@dataclass(frozen=True)
class Bookmark:
    """A Firefox bookmark."""

    url: str
    title: str | None
    added_time: datetime | None
    folder: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "added_time": self.added_time.isoformat() if self.added_time else None,
            "folder": self.folder,
        }


@dataclass(frozen=True)
class OpenTab:
    """A currently open Firefox tab."""

    url: str
    title: str | None
    last_accessed: datetime | None
    window_index: int
    tab_index: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url,
            "title": self.title,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
            "window_index": self.window_index,
            "tab_index": self.tab_index,
        }


def _extract_domain(url: str) -> str:
    """Extract domain from URL."""
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url)
        return parsed.netloc or url
    except Exception:
        return url


def _firefox_time_to_datetime(firefox_time: int | None) -> datetime | None:
    """Convert Firefox timestamp (microseconds since epoch) to datetime."""
    if firefox_time is None or firefox_time == 0:
        return None
    try:
        # Firefox uses microseconds since epoch
        return datetime.fromtimestamp(firefox_time / 1_000_000)
    except (ValueError, OSError):
        return None


# =============================================================================
# Profile Discovery
# =============================================================================


def find_firefox_root() -> Path | None:
    """Find the Firefox profile root directory.

    Checks standard locations for Firefox profiles on Linux.
    Supports standard install, Snap, and Flatpak.

    Returns:
        Path to Firefox profile root, or None if not found.
    """
    home = Path.home()

    # Standard locations to check
    candidates = [
        home / ".mozilla" / "firefox",  # Standard Linux
        home / "snap" / "firefox" / "common" / ".mozilla" / "firefox",  # Snap
        home / ".var" / "app" / "org.mozilla.firefox" / ".mozilla" / "firefox",  # Flatpak
    ]

    for candidate in candidates:
        if candidate.exists() and candidate.is_dir():
            return candidate

    return None


def list_profiles() -> list[dict[str, Any]]:
    """List all Firefox profiles.

    Returns:
        List of profile info dicts with name, path, and whether default.
    """
    root = find_firefox_root()
    if root is None:
        return []

    profiles = []
    profiles_ini = root / "profiles.ini"

    if profiles_ini.exists():
        # Parse profiles.ini
        import configparser

        config = configparser.ConfigParser()
        config.read(profiles_ini)

        for section in config.sections():
            if section.startswith("Profile"):
                name = config.get(section, "Name", fallback="")
                path = config.get(section, "Path", fallback="")
                is_relative = config.getboolean(section, "IsRelative", fallback=True)
                is_default = config.getboolean(section, "Default", fallback=False)

                if path:
                    if is_relative:
                        profile_path = root / path
                    else:
                        profile_path = Path(path)

                    if profile_path.exists():
                        profiles.append({
                            "name": name,
                            "path": str(profile_path),
                            "is_default": is_default,
                            "has_places_db": (profile_path / "places.sqlite").exists(),
                        })

    # Fallback: scan for profile directories
    if not profiles:
        for entry in root.iterdir():
            if entry.is_dir() and (entry / "places.sqlite").exists():
                profiles.append({
                    "name": entry.name,
                    "path": str(entry),
                    "is_default": "default" in entry.name.lower(),
                    "has_places_db": True,
                })

    return profiles


def get_default_profile() -> Path | None:
    """Get the default Firefox profile path.

    Returns:
        Path to default profile, or None if not found.
    """
    profiles = list_profiles()

    # First, look for explicitly marked default
    for profile in profiles:
        if profile["is_default"]:
            return Path(profile["path"])

    # Fall back to first profile with places.sqlite
    for profile in profiles:
        if profile["has_places_db"]:
            return Path(profile["path"])

    return None


def firefox_available() -> bool:
    """Check if Firefox is installed and has profile data."""
    return get_default_profile() is not None


def get_firefox_status() -> dict[str, Any]:
    """Get Firefox installation and profile status.

    Returns:
        Dict with availability, profile info, and database status.
    """
    root = find_firefox_root()
    if root is None:
        return {
            "available": False,
            "reason": "Firefox profile directory not found",
            "profiles": [],
        }

    profiles = list_profiles()
    if not profiles:
        return {
            "available": False,
            "reason": "No Firefox profiles found",
            "root": str(root),
            "profiles": [],
        }

    default_profile = get_default_profile()
    return {
        "available": True,
        "root": str(root),
        "profile_count": len(profiles),
        "default_profile": str(default_profile) if default_profile else None,
        "profiles": profiles,
    }


# =============================================================================
# History Access
# =============================================================================


def _copy_db_for_reading(db_path: Path) -> Path:
    """Copy database to temp location to avoid locking issues.

    Firefox keeps the database locked while running, so we copy it.
    """
    if not db_path.exists():
        raise FirefoxError(f"Database not found: {db_path}")

    temp_dir = Path(tempfile.gettempdir()) / "reos_firefox"
    temp_dir.mkdir(exist_ok=True)

    temp_db = temp_dir / f"{db_path.stem}_{db_path.parent.name}.sqlite"
    shutil.copy2(db_path, temp_db)

    # Also copy WAL and SHM files if they exist (for consistency)
    for suffix in ["-wal", "-shm"]:
        wal_file = db_path.parent / f"{db_path.name}{suffix}"
        if wal_file.exists():
            shutil.copy2(wal_file, temp_dir / f"{temp_db.name}{suffix}")

    return temp_db


def get_history(
    *,
    limit: int = 100,
    days: int | None = None,
    query: str | None = None,
    profile_path: Path | None = None,
) -> list[HistoryEntry]:
    """Get browsing history from Firefox.

    Args:
        limit: Maximum number of entries to return.
        days: Only return entries from the last N days.
        query: Filter by URL or title containing this string.
        profile_path: Specific profile path, or None for default.

    Returns:
        List of HistoryEntry objects, most recent first.
    """
    profile = profile_path or get_default_profile()
    if profile is None:
        raise FirefoxError("No Firefox profile found")

    places_db = profile / "places.sqlite"
    temp_db = _copy_db_for_reading(places_db)

    try:
        conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query
        sql = """
            SELECT
                p.url,
                p.title,
                h.visit_date,
                p.visit_count,
                p.url as domain_source
            FROM moz_places p
            JOIN moz_historyvisits h ON p.id = h.place_id
            WHERE p.url NOT LIKE 'place:%'
        """
        params: list[Any] = []

        if days is not None:
            # Firefox uses microseconds since epoch
            cutoff = (datetime.now().timestamp() - days * 86400) * 1_000_000
            sql += " AND h.visit_date > ?"
            params.append(int(cutoff))

        if query is not None:
            sql += " AND (p.url LIKE ? OR p.title LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])

        sql += " ORDER BY h.visit_date DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        entries = []
        for row in rows:
            entries.append(
                HistoryEntry(
                    url=row["url"],
                    title=row["title"],
                    visit_time=_firefox_time_to_datetime(row["visit_date"]) or datetime.now(),
                    visit_count=row["visit_count"] or 1,
                    domain=_extract_domain(row["url"]),
                )
            )

        return entries

    finally:
        # Clean up temp file
        try:
            temp_db.unlink(missing_ok=True)
            for suffix in ["-wal", "-shm"]:
                (temp_db.parent / f"{temp_db.name}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


def get_most_visited(
    *,
    limit: int = 20,
    days: int | None = 7,
    profile_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Get most visited domains.

    Args:
        limit: Maximum number of domains to return.
        days: Only consider visits from the last N days.
        profile_path: Specific profile path, or None for default.

    Returns:
        List of dicts with domain, visit_count, and sample_urls.
    """
    profile = profile_path or get_default_profile()
    if profile is None:
        raise FirefoxError("No Firefox profile found")

    places_db = profile / "places.sqlite"
    temp_db = _copy_db_for_reading(places_db)

    try:
        conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # Build query for domain aggregation
        sql = """
            SELECT
                p.url,
                p.title,
                COUNT(*) as visit_count
            FROM moz_places p
            JOIN moz_historyvisits h ON p.id = h.place_id
            WHERE p.url NOT LIKE 'place:%'
              AND p.url NOT LIKE 'about:%'
              AND p.url NOT LIKE 'moz-extension:%'
        """
        params: list[Any] = []

        if days is not None:
            cutoff = (datetime.now().timestamp() - days * 86400) * 1_000_000
            sql += " AND h.visit_date > ?"
            params.append(int(cutoff))

        sql += " GROUP BY p.id ORDER BY visit_count DESC LIMIT ?"
        params.append(limit * 3)  # Get more to aggregate by domain

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        # Aggregate by domain
        domain_stats: dict[str, dict[str, Any]] = {}
        for row in rows:
            domain = _extract_domain(row["url"])
            if domain not in domain_stats:
                domain_stats[domain] = {
                    "domain": domain,
                    "visit_count": 0,
                    "sample_urls": [],
                    "sample_titles": [],
                }
            domain_stats[domain]["visit_count"] += row["visit_count"]
            if len(domain_stats[domain]["sample_urls"]) < 3:
                domain_stats[domain]["sample_urls"].append(row["url"])
                if row["title"]:
                    domain_stats[domain]["sample_titles"].append(row["title"])

        # Sort by visit count and limit
        sorted_domains = sorted(
            domain_stats.values(), key=lambda x: x["visit_count"], reverse=True
        )[:limit]

        return sorted_domains

    finally:
        try:
            temp_db.unlink(missing_ok=True)
            for suffix in ["-wal", "-shm"]:
                (temp_db.parent / f"{temp_db.name}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


# =============================================================================
# Bookmarks
# =============================================================================


def get_bookmarks(
    *,
    limit: int = 100,
    query: str | None = None,
    folder: str | None = None,
    profile_path: Path | None = None,
) -> list[Bookmark]:
    """Get Firefox bookmarks.

    Args:
        limit: Maximum number of bookmarks to return.
        query: Filter by URL or title containing this string.
        folder: Filter by folder name.
        profile_path: Specific profile path, or None for default.

    Returns:
        List of Bookmark objects.
    """
    profile = profile_path or get_default_profile()
    if profile is None:
        raise FirefoxError("No Firefox profile found")

    places_db = profile / "places.sqlite"
    temp_db = _copy_db_for_reading(places_db)

    try:
        conn = sqlite3.connect(f"file:{temp_db}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        sql = """
            SELECT
                p.url,
                b.title,
                b.dateAdded,
                parent.title as folder_name
            FROM moz_bookmarks b
            JOIN moz_places p ON b.fk = p.id
            LEFT JOIN moz_bookmarks parent ON b.parent = parent.id
            WHERE b.type = 1  -- Regular bookmarks only
              AND p.url NOT LIKE 'place:%'
        """
        params: list[Any] = []

        if query is not None:
            sql += " AND (p.url LIKE ? OR b.title LIKE ?)"
            params.extend([f"%{query}%", f"%{query}%"])

        if folder is not None:
            sql += " AND parent.title LIKE ?"
            params.append(f"%{folder}%")

        sql += " ORDER BY b.dateAdded DESC LIMIT ?"
        params.append(limit)

        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        bookmarks = []
        for row in rows:
            bookmarks.append(
                Bookmark(
                    url=row["url"],
                    title=row["title"],
                    added_time=_firefox_time_to_datetime(row["dateAdded"]),
                    folder=row["folder_name"],
                )
            )

        return bookmarks

    finally:
        try:
            temp_db.unlink(missing_ok=True)
            for suffix in ["-wal", "-shm"]:
                (temp_db.parent / f"{temp_db.name}{suffix}").unlink(missing_ok=True)
        except OSError:
            pass


# =============================================================================
# Open Tabs (Current Session)
# =============================================================================


def _decompress_jsonlz4(file_path: Path) -> dict[str, Any]:
    """Decompress Firefox's jsonlz4 format.

    Firefox uses a custom compression format: 8-byte header + lz4 compressed JSON.
    """
    with open(file_path, "rb") as f:
        # Read and verify magic header
        magic = f.read(8)
        if magic[:8] != b"mozLz40\0":
            raise FirefoxError(f"Invalid jsonlz4 file: {file_path}")

        # Read compressed data
        compressed = f.read()

    # Decompress using lz4
    try:
        import lz4.block

        decompressed = lz4.block.decompress(compressed)
        return json.loads(decompressed)
    except ImportError:
        raise FirefoxError("lz4 library not installed. Run: pip install lz4")


def get_open_tabs(*, profile_path: Path | None = None) -> list[OpenTab]:
    """Get currently open tabs from Firefox session.

    Note: This reads the session recovery file, which may be slightly behind
    the actual browser state. Firefox updates this periodically.

    Args:
        profile_path: Specific profile path, or None for default.

    Returns:
        List of OpenTab objects for all windows and tabs.
    """
    profile = profile_path or get_default_profile()
    if profile is None:
        raise FirefoxError("No Firefox profile found")

    # Session data is in sessionstore-backups/recovery.jsonlz4
    session_dir = profile / "sessionstore-backups"
    recovery_file = session_dir / "recovery.jsonlz4"

    # Fall back to previous.jsonlz4 if recovery doesn't exist
    if not recovery_file.exists():
        recovery_file = session_dir / "previous.jsonlz4"

    if not recovery_file.exists():
        # Try the old location
        recovery_file = profile / "sessionstore.jsonlz4"

    if not recovery_file.exists():
        return []

    try:
        session_data = _decompress_jsonlz4(recovery_file)
    except Exception as e:
        raise FirefoxError(f"Failed to read session data: {e}") from e

    tabs = []
    for window_idx, window in enumerate(session_data.get("windows", [])):
        for tab_idx, tab in enumerate(window.get("tabs", [])):
            # Get the current entry (active page in tab history)
            entries = tab.get("entries", [])
            current_idx = tab.get("index", 1) - 1  # 1-indexed

            if entries and 0 <= current_idx < len(entries):
                entry = entries[current_idx]
                url = entry.get("url", "")
                title = entry.get("title")

                # Skip internal pages
                if url.startswith(("about:", "moz-extension:", "chrome:")):
                    continue

                last_accessed = tab.get("lastAccessed")
                tabs.append(
                    OpenTab(
                        url=url,
                        title=title,
                        last_accessed=datetime.fromtimestamp(last_accessed / 1000)
                        if last_accessed
                        else None,
                        window_index=window_idx,
                        tab_index=tab_idx,
                    )
                )

    return tabs


def get_open_tabs_summary(*, profile_path: Path | None = None) -> dict[str, Any]:
    """Get a summary of currently open tabs.

    Returns:
        Dict with tab count, domains, and tab list.
    """
    try:
        tabs = get_open_tabs(profile_path=profile_path)
    except FirefoxError:
        return {
            "available": False,
            "reason": "Could not read session data (Firefox may not be running or lz4 not installed)",
            "tabs": [],
        }

    # Group by domain
    domain_counts: dict[str, int] = {}
    for tab in tabs:
        domain = _extract_domain(tab.url)
        domain_counts[domain] = domain_counts.get(domain, 0) + 1

    # Sort domains by count
    top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return {
        "available": True,
        "tab_count": len(tabs),
        "window_count": len(set(t.window_index for t in tabs)),
        "top_domains": [{"domain": d, "count": c} for d, c in top_domains],
        "tabs": [t.to_dict() for t in tabs],
    }


# =============================================================================
# Browser Control
# =============================================================================


def open_url(url: str, *, new_window: bool = False, private: bool = False) -> dict[str, Any]:
    """Open a URL in Firefox.

    Args:
        url: The URL to open.
        new_window: Open in a new window instead of a new tab.
        private: Open in a private/incognito window.

    Returns:
        Dict with success status and any error message.
    """
    # Validate URL
    if not url:
        return {"success": False, "error": "URL is required"}

    # Basic URL validation
    if not url.startswith(("http://", "https://", "file://", "about:")):
        # Assume it's a search or needs https
        if "." in url and " " not in url:
            url = f"https://{url}"
        else:
            # Treat as search query
            from urllib.parse import quote

            url = f"https://www.google.com/search?q={quote(url)}"

    # Build command
    cmd = ["firefox"]

    if private:
        cmd.append("--private-window")
    elif new_window:
        cmd.append("--new-window")
    else:
        cmd.append("--new-tab")

    cmd.append(url)

    try:
        # Start Firefox in background
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        return {
            "success": True,
            "url": url,
            "new_window": new_window,
            "private": private,
        }
    except FileNotFoundError:
        # Try xdg-open as fallback
        try:
            subprocess.Popen(
                ["xdg-open", url],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            return {
                "success": True,
                "url": url,
                "method": "xdg-open",
            }
        except FileNotFoundError:
            return {"success": False, "error": "Firefox not found and xdg-open failed"}
    except Exception as e:
        return {"success": False, "error": str(e)}


def search_web(query: str, *, engine: str = "google") -> dict[str, Any]:
    """Open a web search in Firefox.

    Args:
        query: The search query.
        engine: Search engine to use ('google', 'duckduckgo', 'bing').

    Returns:
        Dict with success status.
    """
    from urllib.parse import quote

    engines = {
        "google": "https://www.google.com/search?q=",
        "duckduckgo": "https://duckduckgo.com/?q=",
        "bing": "https://www.bing.com/search?q=",
        "github": "https://github.com/search?q=",
        "stackoverflow": "https://stackoverflow.com/search?q=",
    }

    base_url = engines.get(engine.lower(), engines["google"])
    url = f"{base_url}{quote(query)}"

    result = open_url(url)
    result["query"] = query
    result["engine"] = engine
    return result
