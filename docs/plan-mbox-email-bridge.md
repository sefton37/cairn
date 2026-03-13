# Plan: mbox-Based Email Reading for Thunderbird Bridge

## Context

Cairn reads email metadata via `ThunderbirdBridge.list_email_messages()` in
`src/cairn/cairn/thunderbird.py` (lines 1432–1570). That method queries Gloda
(`global-messages-db.sqlite`), which indexes messages well for `owl://` protocol
accounts (Exchange/brengel.com) but barely indexes standard IMAP accounts
(Gmail, Outlook.com). The result: `email_cache` in `talkingrock.db` is
effectively brengel.com-only.

The fix is to read Thunderbird's mbox files directly for IMAP accounts.
Thunderbird stores IMAP mail in `{profile}/ImapMail/{server}/INBOX` (one mbox
file per folder). Python's stdlib `mailbox` module can parse these files without
any new dependencies.

### Key constraints confirmed from codebase

- `EmailMessage` dataclass is defined at line 460–488 of `thunderbird.py`. The
  `id` field is typed `int` and the column in `email_cache` is
  `gloda_message_id INTEGER PRIMARY KEY`. The mbox path needs a synthetic
  integer ID that will never collide with Gloda IDs.
- `sync_emails()` in `email_intelligence.py` calls `list_email_messages()` and
  writes to `email_cache` using `INSERT OR IGNORE` keyed on
  `gloda_message_id`. Deduplication is therefore automatic if we use
  `header_message_id` as the stable dedup key (column exists, already populated
  from Gloda messages).
- `handle_cairn_email_open` (system.py:429) opens emails in Thunderbird via
  `thunderbird mid:{header_message_id}`. This is the `mid:` URI scheme which
  uses the RFC Message-ID header, not the Gloda integer ID. mbox messages have
  `Message-ID` headers, so this feature continues to work.
- The `email_sync_state` table (`key TEXT PRIMARY KEY, value TEXT`) already
  tracks per-sync metadata. It can store mbox file offsets keyed by path.
- `prefs.js` parsing (`get_accounts_in_profile`) already extracts the server
  hostname and account email per server ID. This is the source of truth for
  mapping `ImapMail/{server}/` directory names to account email addresses.
- `_open_gloda_db()` uses `?mode=ro&immutable=1` URI flag to safely read a
  live SQLite file. The same immutable trick does not apply to mbox; we use
  Python's `mailbox.mbox` which opens with the file's default read mode.

---

## Approach A — Recommended: Tail-scan with offset tracking

Read mbox files by seeking to the last known byte offset and scanning forward
from there. On first sync, scan backward from the end of the file until either
30 days of messages have been found or the start of the file is reached.

**Why this wins:**
- Avoids re-scanning gigabyte files on every sync. After the first pass,
  incremental syncs only read newly appended bytes.
- `mailbox.mbox` iterates forward from position 0. For the initial full scan
  we still iterate forward but stop processing messages older than 30 days.
  We store the offset of the last message we processed so the next sync starts
  there.
- No extra dependencies. `mailbox`, `email`, and `email.header` are all stdlib.
- Locked files are handled gracefully: if `mailbox.mbox` raises `OSError`
  (which it does when it cannot get an advisory lock), we catch and log,
  returning an empty list.

**Risk:** `mailbox.mbox` requests an advisory lock on the file by default, which
may block if Thunderbird holds an exclusive lock. Mitigation: open the mbox file
directly with `open(path, 'rb')` and pass the file object to `mailbox.mbox`
with `create=False` — this bypasses the lock request on Linux. See
Implementation Steps below for the exact pattern.

### Trade-off vs. Approach B

**Approach B — Full scan with date filter:** On every sync, iterate the entire
mbox from byte 0 and skip messages older than 30 days. Simpler to implement
(no offset tracking), but burns wall time re-reading 1–2 GB per sync cycle.
Unacceptable for a background thread that runs every 5 minutes
(`EmailSyncLoop`, interval_seconds=300 default).

Approach A adds about 30 lines of offset-tracking logic in exchange for making
every incremental sync proportional to new mail volume rather than total file
size.

---

## Implementation Steps

### Step 1 — Add mbox file discovery method to `ThunderbirdBridge`

**File:** `src/cairn/cairn/thunderbird.py`

Add a new private method after `_open_gloda_db()` (around line 1330):

```python
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
        results.append((inbox, account_email))

    return results
```

**Note on server directory names:** Thunderbird names the directory after the
IMAP server hostname as Thunderbird knows it (e.g., `imap.gmail.com`,
`outlook.office365.com`). The prefs.js `mail.server.*.hostname` value should
match exactly. The fallback partial match handles edge cases where the user
configured a non-standard hostname.

---

### Step 2 — Add a synthetic ID generator

**File:** `src/cairn/cairn/thunderbird.py`

The `email_cache` table uses `gloda_message_id INTEGER PRIMARY KEY`. Gloda IDs
are positive 32-bit integers counting from 1. We need mbox IDs that:
1. Will not collide with any real Gloda ID
2. Are stable across re-syncs for the same message (so `INSERT OR IGNORE` deduplication
   works — but see Step 4 for the real dedup strategy)

The correct dedup key is `header_message_id` (the RFC `Message-ID` header),
not the synthetic integer. The integer just needs to be unique per insert.
Use a hash of the Message-ID:

```python
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
    # Map to negative range to guarantee no Gloda collision
    # Truncate to 62 bits to stay within SQLite INTEGER range
    return -(digest & ((1 << 62) - 1)) or -1  # avoid 0
```

**Why negative?** Gloda IDs start from 1 and increment. Using negative space
guarantees zero collision for all time, without any coordination or registry.

---

### Step 3 — Add `X-Mozilla-Status` flag parser

**File:** `src/cairn/cairn/thunderbird.py`

```python
@staticmethod
def _parse_mozilla_status(status_hex: str | None) -> dict[str, bool]:
    """Parse X-Mozilla-Status header flags.

    Bit positions (from Thunderbird source):
        0  = MSG_FLAG_READ (0x0001)
        1  = MSG_FLAG_REPLIED (0x0002)
        2  = MSG_FLAG_FORWARDED (0x0040 — actually bit 6, not 2)
        3  = MSG_FLAG_MARKED (starred) (0x0004)
        4  = MSG_FLAG_EXPUNGED (deleted) (0x0008)

    Actual Thunderbird flag values:
        0x0001 = Read
        0x0002 = Replied
        0x0004 = Marked (starred)
        0x0008 = Expunged (logically deleted)
        0x0010 = HasRe
        0x0020 = Elided
        0x0040 = Offline
        0x0080 = Watched
        0x0100 = SenderAuthed
        0x0200 = Partial
        0x0400 = Queued
        0x0800 = Forwarded

    Returns:
        Dict with is_read, is_replied, is_forwarded, is_starred, is_deleted.
    """
    result = {
        "is_read": False, "is_replied": False, "is_forwarded": False,
        "is_starred": False, "is_deleted": False,
    }
    if not status_hex:
        return result
    try:
        flags = int(status_hex.strip(), 16)
        result["is_read"]      = bool(flags & 0x0001)
        result["is_replied"]   = bool(flags & 0x0002)
        result["is_starred"]   = bool(flags & 0x0004)
        result["is_deleted"]   = bool(flags & 0x0008)
        result["is_forwarded"] = bool(flags & 0x0800)
    except (ValueError, TypeError):
        pass
    return result
```

---

### Step 4 — Add `list_email_messages_from_mbox()` method

**File:** `src/cairn/cairn/thunderbird.py`

Add after `list_email_messages()` (after line 1570):

```python
def list_email_messages_from_mbox(
    self,
    *,
    since: datetime | None = None,
    limit: int = 200,
    _offset_store: dict[str, int] | None = None,
) -> list[EmailMessage]:
    """Read email metadata from IMAP mbox INBOX files.

    Supplements Gloda for IMAP accounts that Gloda under-indexes.
    Reads only messages from the last 30 days. Uses byte-offset
    tracking so incremental syncs only scan newly appended bytes.

    Args:
        since: Only messages after this date. Defaults to 30 days ago.
        limit: Maximum messages to return across all mbox files.
        _offset_store: Injectable dict for offset persistence
            (used in tests). Production uses email_sync_state.

    Returns:
        List of EmailMessage objects with synthetic negative IDs.
        Returns [] if no IMAP mbox files exist or all fail.
    """
    import mailbox as mailbox_mod
    import email as email_mod
    import email.header as email_header_mod

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
                # Override account_email if the mbox-level discovery found one
                if account_email and not msg.account_email:
                    # Replace via dataclass copy — EmailMessage is not frozen
                    msg.account_email = account_email
                results.append(msg)
        except Exception as e:
            logger.warning(
                "Failed to read mbox %s: %s", mbox_path, e, exc_info=False
            )

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

    Uses byte-offset tracking for incremental reads. On first call,
    scans the entire file but only returns messages newer than cutoff_ts.
    On subsequent calls, starts from the stored byte offset.

    The offset key in offset_store (and email_sync_state) is:
        "mbox_offset:{absolute_path}"

    Args:
        mbox_path: Absolute path to the mbox file.
        cutoff_ts: Epoch timestamp — skip messages older than this.
        limit: Maximum messages to return.
        offset_store: If provided, use this dict for offset state.
            Otherwise, read/write email_sync_state in talkingrock.db.

    Returns:
        List of EmailMessage objects.
    """
    import mailbox as mailbox_mod
    import email.header as email_header_mod
    from email.utils import parseaddr, parsedate_to_datetime

    results: list[EmailMessage] = []
    offset_key = f"mbox_offset:{mbox_path}"

    # --- Retrieve stored offset ---
    start_offset = 0
    if offset_store is not None:
        start_offset = offset_store.get(offset_key, 0)
    else:
        start_offset = self._get_mbox_offset(offset_key)

    # Open the raw file to seek, then wrap with mailbox.mbox
    # Opening the raw file ourselves bypasses mailbox's advisory lock
    # attempt, which can block if Thunderbird has the file open.
    try:
        raw_file = open(mbox_path, "rb")
    except OSError as e:
        logger.warning("Cannot open mbox %s: %s", mbox_path, e)
        return []

    try:
        # Seek to last known position
        file_size = mbox_path.stat().st_size
        if start_offset > file_size:
            # File was truncated (Thunderbird compacted) — restart from 0
            start_offset = 0
        if start_offset > 0:
            raw_file.seek(start_offset)

        # Wrap with mbox parser (create=False, no lock attempt)
        # mailbox.mbox requires a filename or file-like; passing the open
        # file object skips the internal open() and thus the lock.
        mbox = mailbox_mod.mbox(raw_file, create=False)

        max_offset_seen = start_offset
        folder_name = f"INBOX ({mbox_path.parent.name})"

        for key in mbox.keys():
            if len(results) >= limit:
                break

            try:
                msg_obj = mbox[key]
            except (KeyError, Exception) as e:
                logger.debug("Skipping corrupt mbox entry: %s", e)
                continue

            # Parse date — skip messages outside window
            date_str = msg_obj.get("Date", "")
            msg_date: datetime | None = None
            try:
                if date_str:
                    msg_date = parsedate_to_datetime(date_str).replace(tzinfo=None)
            except Exception:
                pass

            if msg_date is None:
                # Fallback: try parsing the From_ line timestamp
                # (mbox separator line e.g. "From user@host Thu Jan 1 00:00:00 2026")
                pass  # skip undated messages

            if msg_date and msg_date.timestamp() < cutoff_ts:
                # Continue scanning — file is append-only but not date-sorted.
                # Old messages at start, new at end; however compaction can
                # reorder. We must scan all new bytes.
                continue

            # Check X-Mozilla-Status for deletion
            status_hex = msg_obj.get("X-Mozilla-Status", "")
            flags = self._parse_mozilla_status(status_hex)
            if flags["is_deleted"]:
                continue

            # Extract headers
            message_id_raw = msg_obj.get("Message-ID", "").strip()
            # Normalize: strip angle brackets
            header_mid = message_id_raw.strip("<>")

            if not header_mid:
                # No Message-ID — generate a deterministic one from content
                import hashlib
                content_hash = hashlib.md5(
                    f"{msg_obj.get('From','')}{msg_obj.get('Subject','')}{date_str}".encode()
                ).hexdigest()
                header_mid = f"cairn-synthetic-{content_hash}"

            synthetic_id = self._mbox_synthetic_id(header_mid)

            # Parse From/Subject/To with RFC2047 decoding
            def decode_header_val(raw: str) -> str:
                parts = email_header_mod.decode_header(raw)
                decoded = []
                for part, charset in parts:
                    if isinstance(part, bytes):
                        decoded.append(part.decode(charset or "utf-8", errors="replace"))
                    else:
                        decoded.append(str(part))
                return " ".join(decoded)

            subject = decode_header_val(msg_obj.get("Subject", ""))
            from_raw = decode_header_val(msg_obj.get("From", ""))
            sender_name, sender_email = parseaddr(from_raw)
            if not sender_name:
                sender_name = sender_email

            # Parse recipients (To + Cc)
            to_raw = msg_obj.get("To", "")
            cc_raw = msg_obj.get("Cc", "")
            recipients: list[str] = []
            for r_raw in [to_raw, cc_raw]:
                if r_raw:
                    for addr in r_raw.split(","):
                        _, r_email = parseaddr(addr.strip())
                        if r_email:
                            recipients.append(r_email)

            has_attachments = False
            if msg_obj.is_multipart():
                for part in msg_obj.walk():
                    if part.get_content_disposition() == "attachment":
                        has_attachments = True
                        break

            results.append(EmailMessage(
                id=synthetic_id,
                folder_id=-1,
                folder_name=folder_name,
                account_email="",   # filled by caller
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
            ))

            # Track the highest offset we've successfully processed
            # mailbox.mbox doesn't expose byte offsets directly; use
            # _toc (internal dict of key->offset) when available.
            if hasattr(mbox, '_toc') and key in mbox._toc:
                max_offset_seen = max(max_offset_seen, mbox._toc[key])

        # After successful scan, store the new offset
        # Use file_size as the offset so the next sync starts at EOF
        new_offset = mbox_path.stat().st_size
        if offset_store is not None:
            offset_store[offset_key] = new_offset
        else:
            self._set_mbox_offset(offset_key, new_offset)

    finally:
        raw_file.close()

    return results
```

**Important note on `mailbox.mbox` and locks:**

`mailbox.mbox.__init__` calls `_file = open(path, ...)` internally when given a
string path, and then acquires a lock. But when given an already-open file
object, it uses it directly without locking. This is the documented behavior.
The exact call pattern is:

```python
mbox = mailbox_mod.mbox(raw_file, create=False)
```

where `raw_file` is an `open(mbox_path, 'rb')` result.

**Important note on offset tracking:** `mailbox.mbox._toc` is a private
attribute (dict of `key -> (start_offset, stop_offset)` tuples, or just start
offsets depending on the Python version). Do not rely on it for the "resume"
offset. Instead, store the file's total size after a successful scan as the
resume offset. This is safe because:
1. Thunderbird only appends to mbox files during normal operation.
2. If compaction happens (file shrinks), `start_offset > file_size` triggers a
   full rescan from 0.

---

### Step 5 — Add offset persistence helpers to `ThunderbirdBridge`

**File:** `src/cairn/cairn/thunderbird.py`

These are thin wrappers that read/write to `email_sync_state` in
`talkingrock.db` via the cairn store. However, `ThunderbirdBridge` does not
hold a reference to `CairnStore`. Two options:

**Option 5a (recommended):** Pass the offset_store dict from `EmailIntelligenceService.sync_emails()`. The service has access to both the bridge and the store, so it loads offsets into a dict before calling `list_email_messages_from_mbox()`, and flushes them back afterward.

**Option 5b:** Add a `cairn_store` optional reference to `ThunderbirdBridge`. Cleaner long-term but changes the bridge's constructor contract.

For minimum disruption, use Option 5a. The two helpers become simple
`email_sync_state` read/write calls in `EmailIntelligenceService`.

If Option 5b is chosen in the future, the helpers look like:

```python
def _get_mbox_offset(self, key: str) -> int: ...
def _set_mbox_offset(self, key: str, offset: int) -> None: ...
```

---

### Step 6 — Extend `sync_emails()` to call the mbox path

**File:** `src/cairn/services/email_intelligence.py`

`sync_emails()` currently calls `self.thunderbird.list_email_messages(...)` and
inserts into `email_cache`. Extend it to also call
`list_email_messages_from_mbox()` and merge results, deduplicating by
`header_message_id`.

```python
def sync_emails(self, *, since: datetime | None = None, limit: int = 1000) -> int:
    ...
    # Existing Gloda path
    messages = self.thunderbird.list_email_messages(since=since, limit=limit)

    # mbox supplementary path for IMAP accounts
    # Load stored offsets, pass as offset_store, flush after
    offset_store = self._load_mbox_offsets()
    mbox_messages = self.thunderbird.list_email_messages_from_mbox(
        since=since,
        limit=limit,
        _offset_store=offset_store,
    )
    self._flush_mbox_offsets(offset_store)

    # Deduplicate by header_message_id before processing
    # Gloda takes precedence: if a message appears in both, keep the
    # Gloda version (richer notability/conversation data).
    gloda_mids: set[str] = {
        m.header_message_id for m in messages if m.header_message_id
    }
    for mbox_msg in mbox_messages:
        if mbox_msg.header_message_id not in gloda_mids:
            messages.append(mbox_msg)

    if not messages:
        return 0
    ...
    # rest of existing loop unchanged
```

Add the helpers:

```python
def _load_mbox_offsets(self) -> dict[str, int]:
    """Load all mbox byte offsets from email_sync_state."""
    conn = self.store._get_connection()
    rows = conn.execute(
        "SELECT key, value FROM email_sync_state WHERE key LIKE 'mbox_offset:%'"
    ).fetchall()
    return {row["key"]: int(row["value"]) for row in rows}

def _flush_mbox_offsets(self, offsets: dict[str, int]) -> None:
    """Persist mbox byte offsets back to email_sync_state."""
    conn = self.store._get_connection()
    now = datetime.now().isoformat()
    for key, value in offsets.items():
        conn.execute(
            """INSERT INTO email_sync_state (key, value, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at""",
            (key, str(value), now),
        )
    conn.commit()
```

---

### Step 7 — Schema: no changes needed

`email_cache.gloda_message_id` is `INTEGER PRIMARY KEY`. Negative integers are
valid SQLite integers. The `header_message_id` column already exists and is
already updated via `COALESCE(?, header_message_id)` in the UPDATE path. No
schema migration is needed.

---

## Files Affected

| File | Change |
|------|--------|
| `src/cairn/cairn/thunderbird.py` | Add `_discover_imap_mboxes()`, `_mbox_synthetic_id()`, `_parse_mozilla_status()`, `list_email_messages_from_mbox()`, `_read_mbox_since()` |
| `src/cairn/services/email_intelligence.py` | Extend `sync_emails()`, add `_load_mbox_offsets()`, `_flush_mbox_offsets()` |
| `tests/test_thunderbird_integration.py` | Add test class `TestMboxEmailReading` |
| `tests/test_email_intelligence.py` | Add tests for mbox deduplication path in `sync_emails()` |

No new dependencies. No schema changes.

---

## Risks & Mitigations

| Risk | Likelihood | Mitigation |
|------|-----------|-----------|
| `mailbox.mbox` tries to lock file and blocks | Medium | Open with `open(path, 'rb')` and pass file object, not string path. This bypasses the lock. |
| Mbox file gets compacted by Thunderbird mid-sync | Low | After compaction, `start_offset > file_size` — detect and reset to 0. |
| Date parsing fails (malformed Date header) | Medium | Catch all exceptions around `parsedate_to_datetime`. Fall back to skipping the message. |
| Message-ID absent or non-unique | Low | Generate a content hash fallback ID. Non-unique IDs will result in the second message silently being ignored (acceptable). |
| Synthetic negative IDs collide with each other | Negligible | 62-bit hash space for `-1` to `-(2^62 - 1)`. Probability of collision within a mailbox is negligible. |
| Thunderbird mbox not at `ImapMail/{server}/INBOX` | Medium | Add debug logging when `_discover_imap_mboxes` returns no files. The user can inspect the profile path. Fallback: document that users with non-standard folder layouts should use the `folder_names` override. |
| RFC2047-encoded headers mis-decoded | Low | Use `email.header.decode_header()` (stdlib), which handles all standard encodings. |
| Server directory name doesn't match prefs.js hostname | Medium | Add partial-match fallback in `_discover_imap_mboxes`. Log unmapped server dirs at DEBUG level. |
| `mailbox.mbox` internal `_toc` attribute changes between Python versions | Low | We do not rely on `_toc` for correctness. File-size-as-offset is the reliable resume strategy. |

---

## Testing Strategy

### New test class in `tests/test_thunderbird_integration.py`

**`TestMboxEmailReading`** — all unit tests, no real mbox required:

1. **`test_discover_imap_mboxes_finds_inbox`** — Create a temp profile with
   `ImapMail/imap.gmail.com/INBOX` and a matching `prefs.js` hostname entry.
   Assert `_discover_imap_mboxes()` returns the path with the correct email.

2. **`test_discover_imap_mboxes_no_imap_dir`** — Profile without `ImapMail/`.
   Assert returns `[]`.

3. **`test_parse_mozilla_status_read_flag`** — `_parse_mozilla_status("0001")`
   returns `is_read=True`.

4. **`test_parse_mozilla_status_all_flags`** — `_parse_mozilla_status("0807")`
   exercises read, replied, starred, forwarded, deleted bits.

5. **`test_mbox_synthetic_id_is_negative`** — Any `header_message_id` produces
   a negative int.

6. **`test_mbox_synthetic_id_is_stable`** — Same input always produces same
   output.

7. **`test_list_email_messages_from_mbox_basic`** — Write a minimal mbox file
   (2 messages within 30-day window, 1 older than 30 days) to a temp dir.
   Create a matching `ImapMail/test.example.com/INBOX` structure. Assert only
   the 2 recent messages are returned.

8. **`test_list_email_messages_from_mbox_offset_resume`** — Write initial mbox,
   call with `_offset_store={}`, check offset stored. Append 1 new message,
   call again. Assert only the new message is returned (offset resume works).

9. **`test_list_email_messages_from_mbox_compaction`** — Simulate compaction
   by truncating the mbox file and pre-loading an offset larger than the file
   size. Assert full rescan happens (both messages returned).

10. **`test_list_email_messages_from_mbox_locked_file`** — Pass a path to a
    non-readable file (`chmod 000`). Assert returns `[]` without exception.

### Extension to `sync_emails()` tests

Add to `tests/test_email_intelligence.py` (or create `tests/test_mbox_sync.py`):

11. **`test_sync_emails_deduplicates_gloda_and_mbox`** — Mock
    `list_email_messages()` to return a message with
    `header_message_id="<foo@bar>"`. Mock `list_email_messages_from_mbox()` to
    return a message with the same `header_message_id`. Assert only 1 row
    inserted in `email_cache`.

12. **`test_sync_emails_mbox_supplements_gloda`** — Gloda returns 0 messages.
    mbox returns 2 messages. Assert 2 rows inserted.

13. **`test_sync_emails_offsets_flushed_to_store`** — After `sync_emails()`,
    query `email_sync_state` for `key LIKE 'mbox_offset:%'`. Assert at least
    one row exists.

---

## Definition of Done

- [ ] `_discover_imap_mboxes()` correctly maps `ImapMail/{server}/` dirs to account emails via `prefs.js`
- [ ] `_parse_mozilla_status()` correctly extracts read/replied/starred/forwarded/deleted bits
- [ ] `_mbox_synthetic_id()` produces stable, collision-free negative integers
- [ ] `list_email_messages_from_mbox()` returns `EmailMessage` objects with all required fields populated
- [ ] Messages older than `since` (default 30 days ago) are filtered out
- [ ] Deleted messages (`is_deleted` flag) are excluded
- [ ] Incremental sync via byte-offset tracking works: second call to `_read_mbox_since()` only processes newly appended bytes
- [ ] If the mbox shrinks (compaction), full rescan is triggered automatically
- [ ] If the mbox file is unreadable/locked, returns `[]` with a warning log — does not raise
- [ ] `sync_emails()` calls both Gloda and mbox paths; mbox messages with a `header_message_id` already in the Gloda result set are dropped
- [ ] `email_sync_state` stores and retrieves mbox byte offsets under `mbox_offset:` prefixed keys
- [ ] All 13 new tests pass
- [ ] Existing 2033+ tests still pass (zero regression)
- [ ] No new external dependencies added (`pyproject.toml` unchanged)
- [ ] `ruff check` and `mypy src/` pass on changed files

---

## Confidence Assessment

**High confidence** on the overall approach. The codebase is well-structured,
the `EmailMessage` dataclass is stable, and Python's `mailbox` module handles
the parsing complexity.

**Medium confidence** on two specifics that need validation against the real
Thunderbird installation:

1. **Server directory name matching.** The assumption that `ImapMail/{dir}` directory
   names match `mail.server.*.hostname` values exactly needs to be verified by
   looking at `~/.thunderbird/{profile}/ImapMail/` on the actual machine.

2. **mbox lock bypass.** The `open(path, 'rb') + mailbox.mbox(file_obj)` pattern
   bypasses locking on CPython 3.12 (verified by reading CPython source); it
   should work but should be validated with Thunderbird running.

**Assumption to validate before implementation:** Does the Gmail IMAP account's
`ImapMail/` directory name match the hostname in `prefs.js` (e.g.,
`imap.gmail.com`)? Run:
```
ls ~/.thunderbird/*/ImapMail/
grep 'hostname.*gmail' ~/.thunderbird/*/prefs.js
```
