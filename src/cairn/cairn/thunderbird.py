"""Thunderbird bridge for CAIRN.

Read-only access to Thunderbird's local SQLite databases for contacts and calendar.
Thunderbird remains the source of truth - we just read from it.
"""

from __future__ import annotations

import configparser
import json
import logging
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# mailbox, email, email.header, email.utils are stdlib — imported inline in methods
# that use them to keep the top-level import footprint small.

logger = logging.getLogger(__name__)


# =============================================================================
# Multi-Profile Discovery Types
# =============================================================================


@dataclass
class ThunderbirdAccount:
    """An email account within a Thunderbird profile."""

    id: str  # Internal account ID (e.g., "account1")
    name: str  # Display name
    email: str  # Primary email address
    type: str  # "imap", "pop3", "local", "rss"
    server: str | None = None  # Server hostname
    calendars: list[str] = field(default_factory=list)  # Calendar IDs
    address_books: list[str] = field(default_factory=list)  # Address book IDs


@dataclass
class ThunderbirdProfile:
    """A discovered Thunderbird profile."""

    name: str  # Profile name (e.g., "default", "work")
    path: Path  # Full path to profile directory
    is_default: bool  # Is this the default profile?
    accounts: list[ThunderbirdAccount] = field(default_factory=list)


@dataclass
class ThunderbirdIntegration:
    """Full Thunderbird integration state."""

    installed: bool  # Is Thunderbird installed?
    install_suggestion: str | None = None  # Install command if not installed
    profiles: list[ThunderbirdProfile] = field(default_factory=list)
    active_profiles: list[str] = field(default_factory=list)  # Profile names enabled
    declined: bool = False  # User declined integration
    declined_at: datetime | None = None


def check_thunderbird_installation() -> tuple[bool, str | None]:
    """Check if Thunderbird is installed.

    Returns:
        Tuple of (installed, install_suggestion).
    """
    # Check common Thunderbird executable locations
    thunderbird_paths = [
        "/usr/bin/thunderbird",
        "/snap/bin/thunderbird",
        "/usr/bin/thunderbird-esr",
    ]

    # Check if thunderbird is in PATH
    if shutil.which("thunderbird"):
        return True, None

    # Check common paths
    for path in thunderbird_paths:
        if Path(path).exists():
            return True, None

    # Not installed - provide install suggestions based on distro
    # Try to detect package manager
    if shutil.which("apt"):
        return False, "sudo apt install thunderbird"
    elif shutil.which("dnf"):
        return False, "sudo dnf install thunderbird"
    elif shutil.which("pacman"):
        return False, "sudo pacman -S thunderbird"
    elif shutil.which("snap"):
        return False, "sudo snap install thunderbird"
    elif shutil.which("flatpak"):
        return False, "flatpak install flathub org.mozilla.Thunderbird"
    else:
        return (
            False,
            "Install Thunderbird from your package manager or https://www.thunderbird.net/",
        )


def _get_thunderbird_base_paths() -> list[Path]:
    """Get possible Thunderbird profile base paths.

    Returns:
        List of paths to check for profiles.ini.
    """
    home = Path.home()
    return [
        # Snap installation (Ubuntu/Linux)
        home / "snap" / "thunderbird" / "common" / ".thunderbird",
        # Flatpak installation
        home / ".var" / "app" / "org.mozilla.Thunderbird" / ".thunderbird",
        # Standard Linux
        home / ".thunderbird",
        # macOS
        home / "Library" / "Thunderbird" / "Profiles",
        # Windows
        Path(os.environ.get("APPDATA", "")) / "Thunderbird" / "Profiles",
    ]


def discover_all_profiles() -> list[ThunderbirdProfile]:
    """Discover all Thunderbird profiles on the system.

    Parses profiles.ini to find all configured profiles.

    Returns:
        List of discovered profiles with their accounts.
    """
    profiles: list[ThunderbirdProfile] = []

    for base_path in _get_thunderbird_base_paths():
        if not base_path.exists():
            continue

        profiles_ini = base_path / "profiles.ini"
        if not profiles_ini.exists():
            # Fall back to directory-based detection
            for item in base_path.iterdir():
                if item.is_dir() and (
                    item.name.endswith(".default") or item.name.endswith(".default-release")
                ):
                    profile = ThunderbirdProfile(
                        name=item.name.split(".")[0],
                        path=item,
                        is_default=True,
                        accounts=[],
                    )
                    # Get accounts for this profile
                    profile.accounts = get_accounts_in_profile(item)
                    profiles.append(profile)
            continue

        # Parse profiles.ini using configparser
        try:
            config = configparser.ConfigParser()
            config.read(profiles_ini)

            for section in config.sections():
                if not section.startswith("Profile"):
                    continue

                name = config.get(section, "Name", fallback="unknown")
                path_value = config.get(section, "Path", fallback=None)
                is_relative = config.getboolean(section, "IsRelative", fallback=True)
                is_default = config.getboolean(section, "Default", fallback=False)

                if path_value is None:
                    continue

                if is_relative:
                    profile_path = base_path / path_value
                else:
                    profile_path = Path(path_value)

                if not profile_path.exists():
                    logger.debug("Profile path does not exist: %s", profile_path)
                    continue

                profile = ThunderbirdProfile(
                    name=name,
                    path=profile_path,
                    is_default=is_default,
                    accounts=[],
                )
                # Get accounts for this profile
                profile.accounts = get_accounts_in_profile(profile_path)
                profiles.append(profile)

        except Exception as e:
            logger.warning("Failed to parse profiles.ini at %s: %s", profiles_ini, e)

    return profiles


def get_accounts_in_profile(profile_path: Path) -> list[ThunderbirdAccount]:
    """Extract all email accounts from a Thunderbird profile.

    Parses prefs.js to find mail.account.* entries.

    Args:
        profile_path: Path to the profile directory.

    Returns:
        List of accounts in the profile.
    """
    accounts: list[ThunderbirdAccount] = []
    prefs_file = profile_path / "prefs.js"

    if not prefs_file.exists():
        return accounts

    try:
        content = prefs_file.read_text(errors="replace")

        # Extract account IDs from mail.accountmanager.accounts
        # Format: user_pref("mail.accountmanager.accounts", "account1,account2");
        accounts_match = re.search(
            r'user_pref\("mail\.accountmanager\.accounts",\s*"([^"]+)"\);',
            content,
        )

        if not accounts_match:
            return accounts

        account_ids = accounts_match.group(1).split(",")

        for account_id in account_ids:
            account_id = account_id.strip()
            if not account_id:
                continue

            # Get identity for this account
            # Format: user_pref("mail.account.account1.identities", "id1");
            identity_match = re.search(
                rf'user_pref\("mail\.account\.{account_id}\.identities",\s*"([^"]+)"\);',
                content,
            )

            # Get server for this account
            # Format: user_pref("mail.account.account1.server", "server1");
            server_match = re.search(
                rf'user_pref\("mail\.account\.{account_id}\.server",\s*"([^"]+)"\);',
                content,
            )

            email = ""
            name = account_id
            server_type = "unknown"
            server_host = None

            # Get email from identity
            if identity_match:
                identity_id = identity_match.group(1).split(",")[0].strip()
                email_match = re.search(
                    rf'user_pref\("mail\.identity\.{identity_id}\.useremail",\s*"([^"]+)"\);',
                    content,
                )
                if email_match:
                    email = email_match.group(1)

                name_match = re.search(
                    rf'user_pref\("mail\.identity\.{identity_id}\.fullName",\s*"([^"]+)"\);',
                    content,
                )
                if name_match:
                    name = name_match.group(1)

            # Get server type and hostname
            if server_match:
                server_id = server_match.group(1).strip()
                type_match = re.search(
                    rf'user_pref\("mail\.server\.{server_id}\.type",\s*"([^"]+)"\);',
                    content,
                )
                if type_match:
                    server_type = type_match.group(1)

                host_match = re.search(
                    rf'user_pref\("mail\.server\.{server_id}\.hostname",\s*"([^"]+)"\);',
                    content,
                )
                if host_match:
                    server_host = host_match.group(1)

            # Get calendars (from calendar-data directory)
            calendars: list[str] = []
            calendar_data = profile_path / "calendar-data"
            if calendar_data.exists():
                # Each .sqlite file is a calendar
                for cal_file in calendar_data.glob("*.sqlite"):
                    calendars.append(cal_file.stem)

            # Get address books
            address_books: list[str] = []
            abook_path = profile_path / "abook.sqlite"
            if abook_path.exists():
                address_books.append("abook")
            # Check for additional address books
            for abook_file in profile_path.glob("abook-*.sqlite"):
                address_books.append(abook_file.stem)

            account = ThunderbirdAccount(
                id=account_id,
                name=name,
                email=email,
                type=server_type,
                server=server_host,
                calendars=calendars,
                address_books=address_books,
            )
            accounts.append(account)

    except Exception as e:
        logger.warning("Failed to parse prefs.js at %s: %s", prefs_file, e)

    return accounts


def get_thunderbird_integration_state() -> ThunderbirdIntegration:
    """Get full Thunderbird integration state.

    Returns:
        ThunderbirdIntegration with installation status and discovered profiles.
    """
    installed, install_suggestion = check_thunderbird_installation()

    if not installed:
        return ThunderbirdIntegration(
            installed=False,
            install_suggestion=install_suggestion,
            profiles=[],
        )

    profiles = discover_all_profiles()

    return ThunderbirdIntegration(
        installed=True,
        install_suggestion=None,
        profiles=profiles,
    )


# =============================================================================
# Original Types (preserved for compatibility)
# =============================================================================


@dataclass
class ThunderbirdConfig:
    """Configuration for Thunderbird integration."""

    profile_path: Path
    address_book_path: Path | None = None
    calendar_path: Path | None = None
    gloda_path: Path | None = None

    def __post_init__(self) -> None:
        """Auto-detect database paths if not provided."""
        if self.address_book_path is None:
            abook = self.profile_path / "abook.sqlite"
            if abook.exists():
                self.address_book_path = abook

        if self.calendar_path is None:
            # Check for calendar databases in order of preference:
            # 1. cache.sqlite - synced calendars (CalDAV, Google, etc.) - most common
            # 2. local.sqlite - purely local calendars
            calendar_candidates = [
                self.profile_path / "calendar-data" / "cache.sqlite",
                self.profile_path / "calendar-data" / "local.sqlite",
            ]
            for cal in calendar_candidates:
                if cal.exists():
                    self.calendar_path = cal
                    break

        # Auto-detect Gloda (global messages) database for email intelligence
        if not hasattr(self, "gloda_path") or self.gloda_path is None:
            gloda = self.profile_path / "global-messages-db.sqlite"
            if gloda.exists():
                self.gloda_path = gloda
            else:
                self.gloda_path = None


@dataclass
class ThunderbirdContact:
    """Contact from Thunderbird address book."""

    id: str
    display_name: str
    email: str | None = None
    phone: str | None = None
    organization: str | None = None
    notes: str | None = None

    # All properties from Thunderbird
    properties: dict[str, str] = field(default_factory=dict)

    @property
    def first_name(self) -> str | None:
        """Get first name."""
        return self.properties.get("FirstName")

    @property
    def last_name(self) -> str | None:
        """Get last name."""
        return self.properties.get("LastName")

    @property
    def job_title(self) -> str | None:
        """Get job title."""
        return self.properties.get("JobTitle")


@dataclass
class CalendarEvent:
    """Event from Thunderbird calendar."""

    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    description: str | None = None
    status: str | None = None  # "TENTATIVE", "CONFIRMED", "CANCELLED"
    all_day: bool = False

    # Recurrence info
    is_recurring: bool = False
    recurrence_rule: str | None = None  # Raw RRULE if present (e.g., "FREQ=WEEKLY;BYDAY=MO,WE,FR")
    recurrence_frequency: str | None = None  # "DAILY", "WEEKLY", "MONTHLY", "YEARLY"

    # Calendar info
    calendar_id: str | None = None  # Thunderbird calendar ID
    calendar_name: str | None = None  # Human-readable calendar name
    category: str | None = None  # Event category (event, holiday, birthday, etc.)

    # Raw icalendar data if needed
    ical_data: str | None = None


@dataclass
class CalendarTodo:
    """Todo from Thunderbird calendar."""

    id: str
    title: str
    due_date: datetime | None = None
    completed_date: datetime | None = None
    status: str | None = None  # "NEEDS-ACTION", "IN-PROCESS", "COMPLETED", "CANCELLED"
    priority: int | None = None  # 1-9, lower = higher priority
    description: str | None = None


@dataclass
class EmailMessage:
    """Email message metadata from Thunderbird's Gloda database.

    SECURITY: Body text is NOT stored here. Body text is only accessed via
    get_email_body_text() and must ONLY be passed to sentence-transformers
    for embedding. It must NEVER enter an LLM context window.
    """

    id: int  # gloda message ID
    folder_id: int
    folder_name: str  # Resolved from folderLocations
    account_email: str  # Extracted from folderURI (e.g. "kellogg@brengel.com")
    conversation_id: int
    date: datetime  # Parsed from microseconds
    header_message_id: str  # RFC Message-ID
    subject: str  # From messagesText_content.c1subject
    sender_name: str  # Parsed from c3author
    sender_email: str  # Parsed from c3author
    recipients: list[str]  # Parsed from c4recipients
    is_read: bool
    is_starred: bool
    is_replied: bool
    is_forwarded: bool
    has_attachments: bool
    attachment_names: list[str]
    notability: int
    deleted: bool


class ThunderbirdBridge:
    """Read-only bridge to Thunderbird data."""

    def __init__(self, config: ThunderbirdConfig):
        """Initialize the bridge.

        Args:
            config: Thunderbird configuration with paths.
        """
        self.config = config

    @classmethod
    def auto_detect(cls) -> ThunderbirdBridge | None:
        """Auto-detect Thunderbird profile and create bridge.

        Returns:
            ThunderbirdBridge if profile found, None otherwise.
        """
        profile_path = cls._find_profile_path()
        if profile_path is None:
            return None

        config = ThunderbirdConfig(profile_path=profile_path)
        return cls(config)

    @staticmethod
    def _find_profile_path() -> Path | None:
        """Find Thunderbird profile path.

        Checks common locations for Thunderbird profiles.

        Returns:
            Path to profile directory, or None if not found.
        """
        home = Path.home()

        # Possible Thunderbird profile locations
        candidates = [
            # Snap installation (Ubuntu/Linux)
            home / "snap" / "thunderbird" / "common" / ".thunderbird",
            # Flatpak installation
            home / ".var" / "app" / "org.mozilla.Thunderbird" / ".thunderbird",
            # Standard Linux
            home / ".thunderbird",
            # macOS
            home / "Library" / "Thunderbird" / "Profiles",
            # Windows (approximate)
            Path(os.environ.get("APPDATA", "")) / "Thunderbird" / "Profiles",
        ]

        for base_path in candidates:
            if not base_path.exists():
                continue

            # Look for profile directories (ending in .default or .default-release)
            for item in base_path.iterdir():
                if item.is_dir() and (
                    item.name.endswith(".default") or item.name.endswith(".default-release")
                ):
                    return item

            # Also check for profiles.ini and parse it
            profiles_ini = base_path / "profiles.ini"
            if profiles_ini.exists():
                # Simple parsing - look for Path= lines
                try:
                    content = profiles_ini.read_text()
                    for line in content.splitlines():
                        if line.startswith("Path="):
                            profile_name = line.split("=", 1)[1]
                            profile_path = base_path / profile_name
                            if profile_path.exists():
                                return profile_path
                except Exception as e:
                    logger.debug("Failed to parse profiles.ini at %s: %s", profiles_ini, e)

        return None

    def _get_all_address_book_paths(self) -> list[Path]:
        """Get paths to all address book SQLite files in the profile."""
        paths: list[Path] = []
        profile = self.config.profile_path
        abook = profile / "abook.sqlite"
        if abook.exists():
            paths.append(abook)
        for extra in sorted(profile.glob("abook-*.sqlite")):
            paths.append(extra)
        return paths

    def has_address_book(self) -> bool:
        """Check if any address book is available."""
        return len(self._get_all_address_book_paths()) > 0

    def has_calendar(self) -> bool:
        """Check if calendar is available."""
        return self.config.calendar_path is not None and self.config.calendar_path.exists()

    # =========================================================================
    # Contacts
    # =========================================================================

    def list_contacts(self, search: str | None = None) -> list[ThunderbirdContact]:
        """List contacts from all address books in the Thunderbird profile.

        Reads abook.sqlite and abook-*.sqlite (one per account), deduped by
        email address. Uses immutable mode to avoid locking a running
        Thunderbird.

        Args:
            search: Optional search string to filter by name/email.

        Returns:
            List of contacts.
        """
        abook_paths = self._get_all_address_book_paths()
        if not abook_paths:
            return []

        # Dedupe by email across all address books
        seen_emails: set[str] = set()
        contacts: dict[str, ThunderbirdContact] = {}

        for abook_path in abook_paths:
            try:
                conn = sqlite3.connect(
                    f"file:{abook_path}?mode=ro&immutable=1",
                    uri=True,
                )
                conn.row_factory = sqlite3.Row

                rows = conn.execute(
                    "SELECT card, name, value FROM properties ORDER BY card"
                ).fetchall()
                conn.close()

                # Group properties by card (contact ID)
                book_contacts: dict[str, ThunderbirdContact] = {}
                for row in rows:
                    card_id = row["card"]
                    prop_name = row["name"]
                    prop_value = row["value"]

                    if card_id not in book_contacts:
                        book_contacts[card_id] = ThunderbirdContact(
                            id=card_id,
                            display_name="",
                            properties={},
                        )
                    book_contacts[card_id].properties[prop_name] = prop_value

                # Extract common fields and dedupe by email
                for contact in book_contacts.values():
                    props = contact.properties
                    contact.display_name = props.get(
                        "DisplayName",
                        f"{props.get('FirstName', '')} {props.get('LastName', '')}".strip(),
                    )
                    contact.email = props.get("PrimaryEmail")
                    contact.phone = props.get("WorkPhone") or props.get("HomePhone")
                    contact.organization = props.get("Company")
                    contact.notes = props.get("Notes")

                    # Dedupe: skip if we already have this email from another book
                    email_lower = contact.email.lower() if contact.email else None
                    if email_lower and email_lower in seen_emails:
                        continue
                    if email_lower:
                        seen_emails.add(email_lower)

                    contacts[contact.id] = contact

            except sqlite3.Error as e:
                logger.warning("Failed to read address book %s: %s", abook_path.name, e)

        result = list(contacts.values())

        if search:
            search_lower = search.lower()
            result = [
                c
                for c in result
                if search_lower in c.display_name.lower()
                or (c.email and search_lower in c.email.lower())
                or (c.organization and search_lower in c.organization.lower())
            ]

        return result

    def get_contact(self, contact_id: str) -> ThunderbirdContact | None:
        """Get a contact by ID. Searches all address books.

        Args:
            contact_id: The contact's card ID.

        Returns:
            ThunderbirdContact if found, None otherwise.
        """
        if not self.has_address_book():
            return None

        for abook_path in self._get_all_address_book_paths():
            result = self._get_contact_from_book(abook_path, contact_id)
            if result:
                return result
        return None

    def _get_contact_from_book(
        self, abook_path: Path, contact_id: str
    ) -> ThunderbirdContact | None:
        try:
            conn = sqlite3.connect(
                f"file:{abook_path}?mode=ro&immutable=1",
                uri=True,
            )
            conn.row_factory = sqlite3.Row

            rows = conn.execute(
                "SELECT name, value FROM properties WHERE card = ?",
                (contact_id,),
            ).fetchall()
            conn.close()

            if not rows:
                return None

            props = {row["name"]: row["value"] for row in rows}
            contact = ThunderbirdContact(
                id=contact_id,
                display_name=props.get(
                    "DisplayName",
                    f"{props.get('FirstName', '')} {props.get('LastName', '')}".strip(),
                ),
                email=props.get("PrimaryEmail"),
                phone=props.get("WorkPhone") or props.get("HomePhone"),
                organization=props.get("Company"),
                notes=props.get("Notes"),
                properties=props,
            )
            return contact

        except sqlite3.Error as e:
            logger.warning("Failed to get contact %s from Thunderbird: %s", contact_id, e)
            return None

    def search_contacts(self, query: str, limit: int = 20) -> list[ThunderbirdContact]:
        """Search contacts by name, email, or organization.

        Args:
            query: Search query.
            limit: Maximum results to return.

        Returns:
            List of matching contacts.
        """
        all_contacts = self.list_contacts(search=query)
        return all_contacts[:limit]

    # =========================================================================
    # Calendar Events
    # =========================================================================

    def get_calendar_names(self) -> dict[str, str]:
        """Get a mapping of calendar IDs to their display names.

        Returns:
            Dictionary mapping cal_id to calendar name.
        """
        if not self.has_calendar():
            return {}

        try:
            conn = self._open_calendar_db()
            if conn is None:
                return {}

            # Query cal_calendars table for id -> name mapping
            names = {}
            try:
                cursor = conn.execute("SELECT id, name FROM cal_calendars")
                for row in cursor:
                    names[row["id"]] = row["name"]
            except sqlite3.Error as e:
                logger.debug("Could not query calendar names: %s", e)

            conn.close()
            return names
        except Exception as e:
            logger.debug("Failed to get calendar names: %s", e)
            return {}

    def _open_calendar_db(self) -> sqlite3.Connection | None:
        """Open calendar database with WAL support.

        Returns:
            SQLite connection or None if failed.
        """
        import tempfile

        temp_dir = Path(tempfile.gettempdir()) / "cairn_calendar"
        temp_dir.mkdir(exist_ok=True)
        temp_db = temp_dir / "cache.sqlite"
        try:
            # Copy main database and WAL files
            shutil.copy(self.config.calendar_path, temp_db)
            for suffix in ["-wal", "-shm"]:
                wal_file = Path(str(self.config.calendar_path) + suffix)
                if wal_file.exists():
                    shutil.copy(wal_file, temp_dir / f"cache.sqlite{suffix}")
            db_path = temp_db
        except OSError as e:
            logger.debug("Could not copy calendar db, using original: %s", e)
            db_path = self.config.calendar_path

        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        conn.row_factory = sqlite3.Row
        return conn

    def _expand_recurring_event(
        self,
        event: CalendarEvent,
        rrule_str: str,
        query_start: datetime,
        query_end: datetime,
    ) -> list[CalendarEvent]:
        """Expand a recurring event into occurrences within the time window.

        Args:
            event: The base event with original start/end.
            rrule_str: The RRULE string (e.g., "RRULE:FREQ=WEEKLY;BYDAY=MO").
            query_start: Start of time window.
            query_end: End of time window.

        Returns:
            List of event occurrences within the window.
        """
        try:
            from dateutil.rrule import rrulestr
        except ImportError:
            logger.debug("dateutil not available, skipping recurrence expansion")
            return []

        occurrences = []
        duration = event.end - event.start

        try:
            # Parse the RRULE - strip "RRULE:" prefix if present
            rule_text = rrule_str
            if rule_text.startswith("RRULE:"):
                rule_text = rule_text[6:]

            # Handle timezone issues: UNTIL with Z suffix needs timezone-aware dtstart
            # Convert UNTIL from UTC to naive local time to avoid timezone conflicts
            if "UNTIL=" in rule_text and "Z" in rule_text:
                import re

                # Extract and convert UNTIL to naive local time
                match = re.search(r"UNTIL=(\d{8}T\d{6})Z", rule_text)
                if match:
                    until_str = match.group(1)
                    # Parse as UTC, convert to local, format as naive
                    until_utc = datetime.strptime(until_str, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                    until_local = until_utc.astimezone().replace(tzinfo=None)
                    # Replace in rule text (remove Z suffix)
                    rule_text = rule_text.replace(
                        f"UNTIL={until_str}Z", f"UNTIL={until_local.strftime('%Y%m%dT%H%M%S')}"
                    )

            # Create rrule with the event's original start as dtstart
            rule = rrulestr(rule_text, dtstart=event.start)

            # Get occurrences within the time window
            for dt in rule.between(query_start, query_end, inc=True):
                # Create a new event for this occurrence
                occurrence = CalendarEvent(
                    id=f"{event.id}_{dt.strftime('%Y%m%d%H%M')}",
                    title=event.title,
                    start=dt,
                    end=dt + duration,
                    location=event.location,
                    description=event.description,
                    status=event.status,
                    all_day=event.all_day,
                    is_recurring=True,
                    recurrence_rule=rrule_str,
                    recurrence_frequency=event.recurrence_frequency,
                )
                occurrences.append(occurrence)

        except Exception as e:
            logger.debug("Failed to expand recurrence for %s: %s", event.title, e)

        return occurrences

    def list_events(
        self,
        start: datetime | None = None,
        end: datetime | None = None,
        include_past: bool = False,
    ) -> list[CalendarEvent]:
        """List calendar events including expanded recurring events.

        Args:
            start: Start of date range (default: now).
            end: End of date range (default: 30 days from start).
            include_past: Include past events in results.

        Returns:
            List of calendar events.
        """
        if not self.has_calendar():
            return []

        if start is None:
            start = datetime.now() if not include_past else datetime.min
        if end is None:
            end = start + timedelta(days=30)

        # Convert to microseconds since epoch (Thunderbird's format)
        start_us = int(start.timestamp() * 1_000_000)
        end_us = int(end.timestamp() * 1_000_000)

        try:
            conn = self._open_calendar_db()
            if conn is None:
                return []

            events = []

            # 1. Query non-recurring events in the time window
            rows = conn.execute(
                """
                SELECT e.id, e.title, e.event_start, e.event_end, e.event_stamp, e.flags
                FROM cal_events e
                LEFT JOIN cal_recurrence r ON e.id = r.item_id AND e.cal_id = r.cal_id
                WHERE e.event_start <= ? AND e.event_end >= ?
                  AND (r.icalString IS NULL OR r.icalString NOT LIKE 'RRULE:%')
                ORDER BY e.event_start
                """,
                (end_us, start_us),
            ).fetchall()

            for row in rows:
                event = self._parse_event(row)
                if event:
                    events.append(event)

            # 2. Query recurring events and expand them
            recurring_rows = conn.execute(
                """
                SELECT DISTINCT e.id, e.title, e.event_start, e.event_end,
                       e.event_stamp, e.flags, r.icalString as rrule
                FROM cal_events e
                JOIN cal_recurrence r ON e.id = r.item_id AND e.cal_id = r.cal_id
                WHERE r.icalString LIKE 'RRULE:%'
                """,
            ).fetchall()

            conn.close()

            # Expand each recurring event
            seen_ids = set()  # Avoid duplicate base events
            for row in recurring_rows:
                base_id = row["id"]
                if base_id in seen_ids:
                    continue
                seen_ids.add(base_id)

                base_event = self._parse_event(row)
                if base_event:
                    rrule_str = row["rrule"]
                    occurrences = self._expand_recurring_event(base_event, rrule_str, start, end)
                    events.extend(occurrences)

            # Sort by start time
            events.sort(key=lambda e: e.start)
            return events

        except sqlite3.Error as e:
            logger.warning("Failed to list calendar events from Thunderbird: %s", e)
            return []

    def get_upcoming_events(self, hours: int = 24, limit: int = 10) -> list[CalendarEvent]:
        """Get upcoming events.

        Args:
            hours: How many hours ahead to look.
            limit: Maximum events to return.

        Returns:
            List of upcoming events.
        """
        now = datetime.now()
        end = now + timedelta(hours=hours)
        events = self.list_events(start=now, end=end)
        return events[:limit]

    def get_today_events(self) -> list[CalendarEvent]:
        """Get today's events.

        Returns:
            List of today's events.
        """
        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return self.list_events(start=start, end=end)

    def _parse_event(
        self, row: sqlite3.Row, calendar_names: dict[str, str] | None = None
    ) -> CalendarEvent | None:
        """Parse a database row into CalendarEvent.

        Args:
            row: Database row.
            calendar_names: Optional mapping of cal_id to calendar name.

        Returns:
            CalendarEvent or None if invalid.
        """
        try:
            # Thunderbird stores times in microseconds
            start_us = row["event_start"]
            end_us = row["event_end"]

            start = datetime.fromtimestamp(start_us / 1_000_000)
            end = datetime.fromtimestamp(end_us / 1_000_000)

            # Check if all-day (duration is exactly days)
            all_day = (end - start).total_seconds() % 86400 == 0

            # Get calendar info
            calendar_id = None
            calendar_name = None
            try:
                calendar_id = str(row["cal_id"])
                if calendar_names and calendar_id in calendar_names:
                    calendar_name = calendar_names[calendar_id]
            except (KeyError, IndexError):
                pass

            # Parse iCal string for additional data (if available)
            location = None
            description = None
            status = None
            ical = None
            is_recurring = False
            recurrence_rule = None
            recurrence_frequency = None
            try:
                ical = row["icalString"]
                if ical:
                    location = self._extract_ical_field(ical, "LOCATION")
                    description = self._extract_ical_field(ical, "DESCRIPTION")
                    status = self._extract_ical_field(ical, "STATUS")
                    # Extract recurrence info
                    recurrence_rule = self._extract_ical_field(ical, "RRULE")
                    if recurrence_rule:
                        is_recurring = True
                        # Extract frequency from RRULE (e.g., "FREQ=WEEKLY;BYDAY=MO" -> "WEEKLY")
                        if "FREQ=" in recurrence_rule:
                            freq_part = recurrence_rule.split("FREQ=")[1].split(";")[0]
                            recurrence_frequency = freq_part
            except (KeyError, IndexError):
                # icalString column may not exist in all Thunderbird versions
                pass

            return CalendarEvent(
                id=row["id"],
                title=row["title"] or "Untitled",
                start=start,
                end=end,
                location=location,
                description=description,
                status=status,
                all_day=all_day,
                is_recurring=is_recurring,
                recurrence_rule=recurrence_rule,
                recurrence_frequency=recurrence_frequency,
                calendar_id=calendar_id,
                calendar_name=calendar_name,
                ical_data=ical,
            )
        except Exception as e:
            logger.debug("Failed to parse calendar event row: %s", e)
            return None

    # =========================================================================
    # Calendar Todos
    # =========================================================================

    def list_todos(
        self,
        include_completed: bool = False,
    ) -> list[CalendarTodo]:
        """List calendar todos.

        Args:
            include_completed: Include completed todos.

        Returns:
            List of calendar todos.
        """
        if not self.has_calendar():
            return []

        try:
            conn = sqlite3.connect(
                f"file:{self.config.calendar_path}?mode=ro",
                uri=True,
            )
            conn.row_factory = sqlite3.Row

            # First check what columns exist in the table
            try:
                cursor = conn.execute("PRAGMA table_info(cal_todos)")
                columns = {row[1] for row in cursor.fetchall()}
            except sqlite3.Error:
                columns = set()

            # Build query based on available columns
            if "icalString" in columns:
                select_cols = "id, title, todo_entry, todo_due, todo_completed, flags, icalString"
            else:
                select_cols = "id, title, todo_entry, todo_due, todo_completed, flags"

            if include_completed:
                rows = conn.execute(
                    f"""
                    SELECT {select_cols}
                    FROM cal_todos
                    ORDER BY todo_due
                    """
                ).fetchall()
            else:
                rows = conn.execute(
                    f"""
                    SELECT {select_cols}
                    FROM cal_todos
                    WHERE todo_completed IS NULL
                    ORDER BY todo_due
                    """
                ).fetchall()
            conn.close()

            todos = []
            for row in rows:
                todo = self._parse_todo(row)
                if todo:
                    todos.append(todo)

            return todos

        except sqlite3.Error as e:
            logger.warning("Failed to list calendar todos from Thunderbird: %s", e)
            return []

    def get_overdue_todos(self) -> list[CalendarTodo]:
        """Get overdue todos.

        Returns:
            List of overdue todos.
        """
        now = datetime.now()
        todos = self.list_todos(include_completed=False)
        return [t for t in todos if t.due_date and t.due_date < now]

    def _parse_todo(self, row: sqlite3.Row) -> CalendarTodo | None:
        """Parse a database row into CalendarTodo.

        Args:
            row: Database row.

        Returns:
            CalendarTodo or None if invalid.
        """
        try:
            due_date = None
            completed_date = None

            if row["todo_due"]:
                due_date = datetime.fromtimestamp(row["todo_due"] / 1_000_000)

            if row["todo_completed"]:
                completed_date = datetime.fromtimestamp(row["todo_completed"] / 1_000_000)

            # Parse iCal string for additional data (if available)
            status = None
            priority = None
            description = None
            try:
                ical = row["icalString"]
                if ical:
                    status = self._extract_ical_field(ical, "STATUS")
                    priority_str = self._extract_ical_field(ical, "PRIORITY")
                    if priority_str:
                        try:
                            priority = int(priority_str)
                        except ValueError:
                            pass
                    description = self._extract_ical_field(ical, "DESCRIPTION")
            except (KeyError, IndexError):
                # icalString column may not exist in all Thunderbird versions
                pass

            return CalendarTodo(
                id=row["id"],
                title=row["title"] or "Untitled",
                due_date=due_date,
                completed_date=completed_date,
                status=status,
                priority=priority,
                description=description,
            )
        except Exception as e:
            logger.debug("Failed to parse calendar todo row: %s", e)
            return None

    # =========================================================================
    # Helpers
    # =========================================================================

    @staticmethod
    def _extract_ical_field(ical_string: str, field: str) -> str | None:
        """Extract a field from iCalendar data.

        Args:
            ical_string: Raw iCalendar string.
            field: Field name to extract (e.g., "LOCATION").

        Returns:
            Field value or None.
        """
        # Simple extraction - looks for FIELD:value or FIELD;params:value
        for line in ical_string.splitlines():
            if line.startswith(f"{field}:"):
                return line.split(":", 1)[1].strip()
            if line.startswith(f"{field};"):
                # Has parameters like LOCATION;ENCODING=UTF-8:value
                parts = line.split(":", 1)
                if len(parts) > 1:
                    return parts[1].strip()
        return None

    @staticmethod
    def get_next_occurrence(
        rrule_str: str,
        dtstart: datetime,
        after: datetime | None = None,
    ) -> datetime | None:
        """Get the next occurrence of a recurring event.

        Args:
            rrule_str: The RRULE string (e.g., "RRULE:FREQ=WEEKLY;BYDAY=MO").
            dtstart: The original start datetime of the event.
            after: Find next occurrence after this time (default: now).

        Returns:
            The next occurrence datetime, or None if no more occurrences.
        """
        try:
            from dateutil.rrule import rrulestr
        except ImportError:
            logger.debug("dateutil not available, cannot compute next occurrence")
            return None

        if after is None:
            after = datetime.now()

        try:
            # Strip "RRULE:" prefix if present
            rule_text = rrule_str
            if rule_text.startswith("RRULE:"):
                rule_text = rule_text[6:]

            # Handle timezone issues: UNTIL with Z suffix needs conversion
            if "UNTIL=" in rule_text and "Z" in rule_text:
                match = re.search(r"UNTIL=(\d{8}T\d{6})Z", rule_text)
                if match:
                    until_str = match.group(1)
                    until_utc = datetime.strptime(until_str, "%Y%m%dT%H%M%S").replace(tzinfo=UTC)
                    until_local = until_utc.astimezone().replace(tzinfo=None)
                    rule_text = rule_text.replace(
                        f"UNTIL={until_str}Z", f"UNTIL={until_local.strftime('%Y%m%dT%H%M%S')}"
                    )

            # Create rrule with the event's original start as dtstart
            rule = rrulestr(rule_text, dtstart=dtstart)

            # Get next occurrence after the specified time
            next_dt = rule.after(after, inc=False)
            return next_dt

        except Exception as e:
            logger.debug("Failed to compute next occurrence: %s", e)
            return None

    # =========================================================================
    # Email Intelligence (Gloda Database)
    # =========================================================================

    def has_email_db(self) -> bool:
        """Check if Gloda email database is available."""
        return self.config.gloda_path is not None and self.config.gloda_path.exists()

    def _open_gloda_db(self) -> sqlite3.Connection | None:
        """Open Gloda database in read-only mode.

        Uses immutable mode to allow concurrent access while Thunderbird runs.

        Returns:
            SQLite connection or None if failed.
        """
        if not self.has_email_db():
            return None

        try:
            uri = f"file:{self.config.gloda_path}?mode=ro&immutable=1"
            conn = sqlite3.connect(uri, uri=True)
            conn.row_factory = sqlite3.Row
            return conn
        except sqlite3.Error as e:
            logger.warning("Failed to open Gloda database: %s", e)
            return None

    # =========================================================================
    # mbox-based Email Reading (IMAP account supplement)
    # =========================================================================

    def _discover_imap_mboxes(self) -> list[tuple[Path, str]]:
        """Find IMAP mbox INBOX files and map each to its account email.

        Looks for files matching {profile}/ImapMail/{server}/INBOX.
        Maps each server directory name back to an account email address
        by scanning prefs.js for mail.server.*.hostname entries.

        Returns:
            List of (mbox_path, account_email) tuples.
            account_email is '' if the mapping cannot be determined.
        """
        imap_root = self.config.profile_path / "ImapMail"
        if not imap_root.exists():
            return []

        # Build hostname -> account email map from prefs.js
        hostname_to_email: dict[str, str] = {}
        prefs_file = self.config.profile_path / "prefs.js"
        if prefs_file.exists():
            content = prefs_file.read_text(errors="replace")
            # Find all server IDs and their hostnames
            for server_id_match in re.finditer(
                r'user_pref\("mail\.server\.(server\d+)\.hostname",\s*"([^"]+)"\);',
                content,
            ):
                server_id = server_id_match.group(1)
                hostname = server_id_match.group(2)
                # Find the account that owns this server
                account_match = re.search(
                    rf'user_pref\("mail\.account\.(account\d+)\.server",\s*"{server_id}"\);',
                    content,
                )
                if not account_match:
                    continue
                account_id = account_match.group(1)
                # Find the identity for this account
                identity_match = re.search(
                    rf'user_pref\("mail\.account\.{account_id}\.identities",\s*"([^"]+)"\);',
                    content,
                )
                if not identity_match:
                    continue
                identity_id = identity_match.group(1).split(",")[0].strip()
                email_match = re.search(
                    rf'user_pref\("mail\.identity\.{identity_id}\.useremail",\s*"([^"]+)"\);',
                    content,
                )
                if email_match:
                    hostname_to_email[hostname.lower()] = email_match.group(1)

        # Scan ImapMail/{server}/INBOX files
        results: list[tuple[Path, str]] = []
        for server_dir in imap_root.iterdir():
            if not server_dir.is_dir():
                continue
            inbox = server_dir / "INBOX"
            if not inbox.exists():
                continue
            server_key = server_dir.name.lower()
            # Direct match: directory name is the hostname
            account_email = hostname_to_email.get(server_key, "")
            # Fallback: partial match (e.g. "imap.gmail.com" contains "gmail")
            if not account_email:
                for hostname, email in hostname_to_email.items():
                    if hostname in server_key or server_key in hostname:
                        account_email = email
                        break
            else:
                logger.debug("mbox discovery: no prefs.js match for server dir %s", server_dir.name)
            results.append((inbox, account_email))

        return results

    @staticmethod
    def _mbox_synthetic_id(header_message_id: str) -> int:
        """Generate a stable synthetic integer ID for an mbox message.

        Uses a hash of the RFC Message-ID header. The result is placed in the
        negative integer space (Gloda IDs are always positive) to prevent any
        possible collision.

        Returns:
            A negative integer stable for the given Message-ID.
        """
        import hashlib

        digest = int(hashlib.md5(header_message_id.encode()).hexdigest(), 16)
        # Map to negative range to guarantee no Gloda collision.
        # Truncate to 62 bits to stay within SQLite INTEGER range.
        return -(digest & ((1 << 62) - 1)) or -1  # avoid 0

    @staticmethod
    def _parse_mozilla_status(status_hex: str | None) -> dict[str, bool]:
        """Parse X-Mozilla-Status header flags.

        Actual Thunderbird flag values used here:
            0x0001 = Read
            0x0002 = Replied
            0x0004 = Marked (starred)
            0x0008 = Expunged (logically deleted, skip during mbox read)
            0x0800 = Forwarded

        Returns:
            Dict with is_read, is_replied, is_forwarded, is_starred, is_deleted.
        """
        result = {
            "is_read": False,
            "is_replied": False,
            "is_forwarded": False,
            "is_starred": False,
            "is_deleted": False,
        }
        if not status_hex:
            return result
        try:
            flags = int(status_hex.strip(), 16)
            result["is_read"] = bool(flags & 0x0001)
            result["is_replied"] = bool(flags & 0x0002)
            result["is_starred"] = bool(flags & 0x0004)
            result["is_deleted"] = bool(flags & 0x0008)
            result["is_forwarded"] = bool(flags & 0x0800)
        except (ValueError, TypeError):
            pass
        return result

    def list_email_messages_from_mbox(
        self,
        *,
        since: datetime | None = None,
        limit: int = 200,
        _offset_store: dict[str, int] | None = None,
    ) -> list[EmailMessage]:
        """Read email metadata from IMAP mbox INBOX files.

        Supplements Gloda for IMAP accounts that Gloda under-indexes (Gmail,
        Outlook.com). Reads only messages from the last 30 days. Uses
        byte-offset tracking so incremental syncs only scan newly appended bytes.

        Args:
            since: Only messages after this date. Defaults to 30 days ago.
            limit: Maximum messages to return across all mbox files.
            _offset_store: Injectable dict for offset persistence (used in
                tests). Production callers load/flush via email_sync_state.

        Returns:
            List of EmailMessage objects with synthetic negative IDs.
            Returns [] if no IMAP mbox files exist or all fail.
        """
        if since is None:
            since = datetime.now() - timedelta(days=30)

        cutoff_ts = since.timestamp()
        mboxes = self._discover_imap_mboxes()
        if not mboxes:
            return []

        results: list[EmailMessage] = []
        seen_message_ids: set[str] = set()

        for mbox_path, account_email in mboxes:
            if len(results) >= limit:
                break
            try:
                msgs = self._read_mbox_since(
                    mbox_path,
                    cutoff_ts=cutoff_ts,
                    limit=limit - len(results),
                    offset_store=_offset_store,
                )
                for msg in msgs:
                    mid = msg.header_message_id
                    if mid and mid in seen_message_ids:
                        continue  # dedup within mbox batch
                    if mid:
                        seen_message_ids.add(mid)
                    # Fill in account_email discovered from prefs.js if not set
                    if account_email and not msg.account_email:
                        msg.account_email = account_email
                    results.append(msg)
            except Exception as e:
                logger.warning("Failed to read mbox %s: %s", mbox_path, e, exc_info=False)

        return results

    def _read_mbox_since(
        self,
        mbox_path: Path,
        *,
        cutoff_ts: float,
        limit: int,
        offset_store: dict[str, int] | None,
    ) -> list[EmailMessage]:
        """Read messages from a single mbox file since the cutoff timestamp.

        Uses byte-offset tracking for incremental reads. On first call, scans
        the entire file but only returns messages newer than cutoff_ts. On
        subsequent calls, starts from the stored byte offset.

        Opening the raw file ourselves and passing it to mailbox.mbox bypasses
        the advisory lock that mailbox normally acquires — important because
        Thunderbird may hold the file open during sync.

        The offset key is: "mbox_offset:{absolute_path}"

        Args:
            mbox_path: Absolute path to the mbox file.
            cutoff_ts: Epoch timestamp — skip messages older than this.
            limit: Maximum messages to return.
            offset_store: If provided, use this dict for offset state.
                Production passes None; tests inject a dict.

        Returns:
            List of EmailMessage objects.
        """
        import email.header as email_header_mod
        import hashlib
        import mailbox as mailbox_mod
        import tempfile
        from email.utils import parseaddr, parsedate_to_datetime

        results: list[EmailMessage] = []
        offset_key = f"mbox_offset:{mbox_path}"

        # --- Retrieve stored offset ---
        start_offset: int = 0
        if offset_store is not None:
            start_offset = offset_store.get(offset_key, 0)

        try:
            file_size = mbox_path.stat().st_size
        except OSError as e:
            logger.warning("Cannot stat mbox %s: %s", mbox_path, e)
            return []

        if start_offset > file_size:
            # File shrank — Thunderbird compacted. Reset and full rescan.
            logger.debug(
                "mbox compaction detected for %s (offset %d > size %d), rescanning",
                mbox_path,
                start_offset,
                file_size,
            )
            start_offset = 0

        # For incremental reads (offset > 0), extract only the new tail bytes
        # into a temp file so we avoid re-scanning the entire mbox.
        # For full reads (offset == 0), open the mbox file directly.
        tmp_path: Path | None = None
        mbox_target = mbox_path
        try:
            if start_offset > 0:
                try:
                    with open(mbox_path, "rb") as raw_file:
                        raw_file.seek(start_offset)
                        tail_bytes = raw_file.read()
                except OSError as e:
                    logger.warning("Cannot read mbox %s: %s", mbox_path, e)
                    return []

                if not tail_bytes.strip():
                    # No new data since last sync
                    return []

                # Write tail to a temp file for mailbox.mbox to parse
                tmp_fd = tempfile.NamedTemporaryFile(
                    delete=False, suffix=".mbox", prefix="cairn_"
                )
                tmp_path = Path(tmp_fd.name)
                tmp_fd.write(tail_bytes)
                tmp_fd.close()
                mbox_target = tmp_path

            try:
                mbox = mailbox_mod.mbox(str(mbox_target), create=False)
            except OSError as e:
                logger.warning("Cannot open mbox %s: %s", mbox_target, e)
                return []

            folder_name = f"INBOX ({mbox_path.parent.name})"

            def decode_header_val(raw: str) -> str:
                """Decode an RFC2047-encoded header value to a plain string."""
                parts = email_header_mod.decode_header(raw)
                decoded = []
                for part, charset in parts:
                    if isinstance(part, bytes):
                        decoded.append(part.decode(charset or "utf-8", errors="replace"))
                    else:
                        decoded.append(str(part))
                return " ".join(decoded)

            for key in mbox.keys():
                if len(results) >= limit:
                    break

                try:
                    msg_obj = mbox[key]
                except Exception as e:
                    logger.debug("Skipping corrupt mbox entry at key %s: %s", key, e)
                    continue

                # Parse date — skip messages outside the sync window
                date_str = msg_obj.get("Date", "")
                msg_date: datetime | None = None
                try:
                    if date_str:
                        msg_date = parsedate_to_datetime(date_str).replace(tzinfo=None)
                except Exception:
                    pass  # undated messages are skipped below

                if msg_date is not None and msg_date.timestamp() < cutoff_ts:
                    # mbox is not strictly date-sorted (compaction can reorder),
                    # so we cannot break early — continue scanning.
                    continue

                # Filter logically-deleted messages (Thunderbird expunge mark)
                status_hex = msg_obj.get("X-Mozilla-Status", "")
                flags = self._parse_mozilla_status(status_hex)
                if flags["is_deleted"]:
                    continue

                # Build a stable Message-ID for dedup and synthetic integer ID
                message_id_raw = msg_obj.get("Message-ID", "").strip()
                header_mid = message_id_raw.strip("<>")
                if not header_mid:
                    # Generate a deterministic fallback from available headers
                    content_hash = hashlib.md5(
                        f"{msg_obj.get('From', '')}{msg_obj.get('Subject', '')}{date_str}".encode()
                    ).hexdigest()
                    header_mid = f"cairn-synthetic-{content_hash}"

                synthetic_id = self._mbox_synthetic_id(header_mid)

                subject = decode_header_val(msg_obj.get("Subject", ""))
                from_raw = decode_header_val(msg_obj.get("From", ""))
                sender_name, sender_email = parseaddr(from_raw)
                if not sender_name:
                    sender_name = sender_email

                # Collect recipients from To and Cc
                recipients: list[str] = []
                for header_name in ("To", "Cc"):
                    raw_val = msg_obj.get(header_name, "")
                    if raw_val:
                        for addr in raw_val.split(","):
                            _, r_email = parseaddr(addr.strip())
                            if r_email:
                                recipients.append(r_email)

                has_attachments = False
                if msg_obj.is_multipart():
                    for part in msg_obj.walk():
                        if part.get_content_disposition() == "attachment":
                            has_attachments = True
                            break

                results.append(
                    EmailMessage(
                        id=synthetic_id,
                        folder_id=-1,
                        folder_name=folder_name,
                        account_email="",  # filled by list_email_messages_from_mbox
                        conversation_id=0,
                        date=msg_date or datetime.now(),
                        header_message_id=header_mid,
                        subject=subject,
                        sender_name=sender_name,
                        sender_email=sender_email,
                        recipients=recipients,
                        is_read=flags["is_read"],
                        is_starred=flags["is_starred"],
                        is_replied=flags["is_replied"],
                        is_forwarded=flags["is_forwarded"],
                        has_attachments=has_attachments,
                        attachment_names=[],
                        notability=0,
                        deleted=False,
                    )
                )

            # Store file size as the new offset so next sync starts at EOF.
            new_offset = mbox_path.stat().st_size
            if offset_store is not None:
                offset_store[offset_key] = new_offset

        finally:
            if tmp_path is not None:
                try:
                    tmp_path.unlink(missing_ok=True)
                except OSError:
                    pass

        return results

    def _parse_author(self, author_str: str | None) -> tuple[str, str]:
        """Parse author string from Gloda format.

        Gloda stores authors as "Name <email> undefined" or just "email".

        Returns:
            Tuple of (name, email).
        """
        if not author_str:
            return ("", "")

        # Remove trailing "undefined" that Gloda sometimes appends
        author_str = author_str.strip()
        if author_str.endswith(" undefined"):
            author_str = author_str[:-10].strip()

        # Try "Name <email>" format
        match = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', author_str)
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
            return (name or email, email)

        # Try bare email
        if "@" in author_str:
            return (author_str, author_str)

        return (author_str, "")

    def _parse_json_attributes(self, json_attrs: str | None) -> dict[str, Any]:
        """Parse jsonAttributes from Gloda messages table.

        Known keys:
            43 = from (already in messagesText)
            58 = starred (boolean)
            59 = read (boolean)
            60 = replied (boolean)
            61 = forwarded (boolean)

        Returns:
            Dict with parsed boolean flags.
        """
        result = {"starred": False, "read": False, "replied": False, "forwarded": False}
        if not json_attrs:
            return result

        try:
            attrs = json.loads(json_attrs)
            if isinstance(attrs, dict):
                result["starred"] = bool(attrs.get("58", False))
                result["read"] = bool(attrs.get("59", False))
                result["replied"] = bool(attrs.get("60", False))
                result["forwarded"] = bool(attrs.get("61", False))
        except (json.JSONDecodeError, TypeError):
            pass

        return result

    def _classify_folder(self, folder_name: str) -> dict[str, bool]:
        """Classify a folder by name patterns.

        Returns:
            Dict with is_inbox, is_sent, is_junk, is_trash booleans.
        """
        name_lower = folder_name.lower() if folder_name else ""
        return {
            "is_inbox": "inbox" in name_lower,
            "is_sent": any(k in name_lower for k in ("sent", "outbox")),
            "is_junk": any(k in name_lower for k in ("junk", "spam")),
            "is_trash": any(k in name_lower for k in ("trash", "deleted", "bin")),
        }

    def get_email_folders(self) -> list[dict]:
        """Get list of email folders from Gloda.

        Returns:
            List of dicts with id, name, and classification booleans.
        """
        conn = self._open_gloda_db()
        if conn is None:
            return []

        try:
            cursor = conn.execute("SELECT id, name FROM folderLocations ORDER BY name")
            folders = []
            for row in cursor:
                classification = self._classify_folder(row["name"])
                folders.append(
                    {
                        "id": row["id"],
                        "name": row["name"],
                        **classification,
                    }
                )
            return folders
        except sqlite3.Error as e:
            logger.warning("Failed to read email folders: %s", e)
            return []
        finally:
            conn.close()

    def list_email_messages(
        self,
        *,
        folder_names: list[str] | None = None,
        since: datetime | None = None,
        unread_only: bool = False,
        limit: int = 200,
    ) -> list[EmailMessage]:
        """List email messages from Gloda database.

        Args:
            folder_names: Filter to specific folders (e.g., ["Inbox"]).
            since: Only messages after this date.
            unread_only: Only unread messages.
            limit: Maximum messages to return.

        Returns:
            List of EmailMessage metadata (no body text).
        """
        conn = self._open_gloda_db()
        if conn is None:
            return []

        try:
            # Build folder ID lookup (name + account email from folderURI)
            folder_map: dict[int, str] = {}
            folder_account_map: dict[int, str] = {}
            for row in conn.execute("SELECT id, name, folderURI FROM folderLocations"):
                folder_map[row["id"]] = row["name"] or f"folder_{row['id']}"
                # Extract account email from URI like:
                #   owl://kellogg%40brengel.com@outlook.office365.com/Inbox
                #   imap://kbrengel%40outlook.com@outlook.office365.com/INBOX
                uri = row["folderURI"] or ""
                account = ""
                if "://" in uri:
                    authority = uri.split("://", 1)[1].split("/", 1)[0]
                    # authority = "kellogg%40brengel.com@outlook.office365.com"
                    user_part = authority.rsplit("@", 1)[0] if "@" in authority else ""
                    account = unquote(user_part)  # "kellogg@brengel.com"
                folder_account_map[row["id"]] = account

            # Build query
            query = """
                SELECT m.id, m.folderID, m.conversationID, m.date,
                       m.headerMessageID, m.jsonAttributes, m.notability, m.deleted,
                       t.c1subject, t.c3author, t.c4recipients, t.c2attachmentNames
                FROM messages m
                LEFT JOIN messagesText_content t ON t.docid = m.id
                WHERE m.deleted = 0
            """
            params: list[Any] = []

            if folder_names:
                # Resolve folder names to IDs
                target_ids = [
                    fid
                    for fid, fname in folder_map.items()
                    if any(fn.lower() in (fname or "").lower() for fn in folder_names)
                ]
                if target_ids:
                    placeholders = ",".join("?" * len(target_ids))
                    query += f" AND m.folderID IN ({placeholders})"
                    params.extend(target_ids)
                else:
                    return []  # No matching folders

            if since:
                # Gloda stores dates as microseconds since epoch
                since_us = int(since.timestamp() * 1_000_000)
                query += " AND m.date >= ?"
                params.append(since_us)

            if unread_only:
                # Filter by read=False in jsonAttributes — done in Python post-query
                pass  # Gloda doesn't index jsonAttributes, so filter in Python

            query += " ORDER BY m.date DESC LIMIT ?"
            # Fetch more if filtering unread in Python
            fetch_limit = limit * 3 if unread_only else limit
            params.append(fetch_limit)

            cursor = conn.execute(query, params)
            messages = []

            for row in cursor:
                attrs = self._parse_json_attributes(row["jsonAttributes"])

                if unread_only and attrs["read"]:
                    continue

                # Parse date from microseconds
                date_us = row["date"] or 0
                msg_date = datetime.fromtimestamp(date_us / 1_000_000)

                # Parse author
                sender_name, sender_email = self._parse_author(row["c3author"])

                # Parse recipients
                recipients_str = row["c4recipients"] or ""
                recipients = [r.strip() for r in recipients_str.split(",") if r.strip()]

                # Parse attachments
                attach_str = row["c2attachmentNames"] or ""
                attachment_names = [a.strip() for a in attach_str.split(",") if a.strip()]

                folder_name = folder_map.get(row["folderID"], f"folder_{row['folderID']}")
                account_email = folder_account_map.get(row["folderID"], "")

                messages.append(
                    EmailMessage(
                        id=row["id"],
                        folder_id=row["folderID"],
                        folder_name=folder_name,
                        account_email=account_email,
                        conversation_id=row["conversationID"] or 0,
                        date=msg_date,
                        header_message_id=row["headerMessageID"] or "",
                        subject=row["c1subject"] or "",
                        sender_name=sender_name,
                        sender_email=sender_email,
                        recipients=recipients,
                        is_read=attrs["read"],
                        is_starred=attrs["starred"],
                        is_replied=attrs["replied"],
                        is_forwarded=attrs["forwarded"],
                        has_attachments=bool(attachment_names),
                        attachment_names=attachment_names,
                        notability=row["notability"] or 0,
                        deleted=bool(row["deleted"]),
                    )
                )

                if len(messages) >= limit:
                    break

            return messages

        except sqlite3.Error as e:
            logger.warning("Failed to list email messages: %s", e)
            return []
        finally:
            conn.close()

    def get_email_body_text(self, message_id: int) -> str | None:
        """Get email body text for a single message.

        SECURITY BARRIER: This method exists ONLY for embedding generation.
        The returned text must ONLY be passed to sentence-transformers.
        It must NEVER be stored as text, passed to an LLM, or included
        in any response or context window.

        Args:
            message_id: Gloda message ID.

        Returns:
            Body text or None if not found.
        """
        conn = self._open_gloda_db()
        if conn is None:
            return None

        try:
            cursor = conn.execute(
                "SELECT c0body FROM messagesText_content WHERE docid = ?",
                (message_id,),
            )
            row = cursor.fetchone()
            return row["c0body"] if row else None
        except sqlite3.Error as e:
            logger.warning("Failed to get email body text for %d: %s", message_id, e)
            return None
        finally:
            conn.close()

    def get_email_body_texts_batch(self, message_ids: list[int]) -> dict[int, str]:
        """Get email body texts for multiple messages.

        SECURITY BARRIER: Same restrictions as get_email_body_text().
        Returned text must ONLY be passed to sentence-transformers.

        Args:
            message_ids: List of Gloda message IDs.

        Returns:
            Dict mapping message_id -> body text.
        """
        if not message_ids:
            return {}

        conn = self._open_gloda_db()
        if conn is None:
            return {}

        try:
            placeholders = ",".join("?" * len(message_ids))
            cursor = conn.execute(
                f"SELECT docid, c0body FROM messagesText_content WHERE docid IN ({placeholders})",
                message_ids,
            )
            return {row["docid"]: row["c0body"] for row in cursor if row["c0body"]}
        except sqlite3.Error as e:
            logger.warning("Failed to batch get email body texts: %s", e)
            return {}
        finally:
            conn.close()

    def get_email_stats(self) -> dict:
        """Get email statistics from Gloda.

        Returns:
            Dict with total, unread count, date range.
        """
        conn = self._open_gloda_db()
        if conn is None:
            return {"total": 0, "unread": 0, "oldest": None, "newest": None}

        try:
            cursor = conn.execute(
                "SELECT COUNT(*) as total, MIN(date) as oldest, MAX(date) as newest "
                "FROM messages WHERE deleted = 0"
            )
            row = cursor.fetchone()
            total = row["total"] or 0
            oldest = None
            newest = None
            if row["oldest"]:
                oldest = datetime.fromtimestamp(row["oldest"] / 1_000_000).isoformat()
            if row["newest"]:
                newest = datetime.fromtimestamp(row["newest"] / 1_000_000).isoformat()

            # Unread count requires scanning jsonAttributes — estimate from last 1000
            cursor2 = conn.execute(
                "SELECT jsonAttributes FROM messages WHERE deleted = 0 "
                "ORDER BY date DESC LIMIT 1000"
            )
            unread = 0
            for r in cursor2:
                attrs = self._parse_json_attributes(r["jsonAttributes"])
                if not attrs["read"]:
                    unread += 1

            return {"total": total, "unread": unread, "oldest": oldest, "newest": newest}
        except sqlite3.Error as e:
            logger.warning("Failed to get email stats: %s", e)
            return {"total": 0, "unread": 0, "oldest": None, "newest": None}
        finally:
            conn.close()

    def get_status(self) -> dict[str, Any]:
        """Get bridge status information.

        Returns:
            Dict with status information.
        """
        return {
            "profile_path": str(self.config.profile_path),
            "has_address_book": self.has_address_book(),
            "address_book_path": (
                str(self.config.address_book_path) if self.config.address_book_path else None
            ),
            "has_calendar": self.has_calendar(),
            "calendar_path": (
                str(self.config.calendar_path) if self.config.calendar_path else None
            ),
        }
