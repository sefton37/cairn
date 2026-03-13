#!/usr/bin/env python3
"""One-time migration script: consolidate three SQLite databases into talkingrock.db.

Merges:
  ~/.reos-data/reos.db         — Events, sessions, classifications, repos, etc.
  ~/.reos-data/play/play.db    — Acts, scenes, blocks, live conversations/messages
  ~/.reos-data/play/.cairn/cairn.db — Metadata overlays, contacts, activity log, etc.

Target:
  ~/.talkingrock/talkingrock.db

Conflict resolutions:
  - conversations/messages: reos.db versions are LEGACY; copied as legacy_conversations
    and legacy_messages. play.db versions (live system) keep their names.
  - schema_version: play.db version kept as-is; reos.db's copied as reos_schema_version.
  - FTS virtual tables (names ending in _fts or starting with sqlite_): skipped — the
    app's migration system rebuilds them on first run.

Usage:
    python3 scripts/migrate_to_talkingrock.py
    python3 scripts/migrate_to_talkingrock.py --dry-run
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REOS_DATA = Path.home() / ".reos-data"
REOS_DB = REOS_DATA / "reos.db"
PLAY_DB = REOS_DATA / "play" / "play.db"
CAIRN_DB = REOS_DATA / "play" / ".cairn" / "cairn.db"
ENCRYPTED_MARKER = REOS_DATA / ".encrypted"

TALKINGROCK_DIR = Path.home() / ".talkingrock"
TARGET_DB = TALKINGROCK_DIR / "talkingrock.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def log(msg: str) -> None:
    print(msg, flush=True)


def abort(msg: str) -> None:
    print(f"\nERROR: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def get_tables(conn: sqlite3.Connection) -> list[str]:
    """Return all non-virtual, non-internal table names."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    return [r[0] for r in rows]


def is_fts_table(name: str) -> bool:
    """Return True if the table is an FTS virtual table or an FTS shadow table."""
    if name.endswith("_fts"):
        return True
    # FTS shadow tables: <base>_fts_content, _fts_data, _fts_idx, _fts_docsize, _fts_config
    parts = name.rsplit("_fts_", 1)
    if len(parts) == 2:
        return True
    if name.startswith("sqlite_"):
        return True
    return False


def is_virtual_table(conn: sqlite3.Connection, name: str) -> bool:
    """Return True if the table is a virtual table (e.g. FTS)."""
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    if row is None:
        return False
    sql = row[0] or ""
    return "USING fts" in sql.upper() or "VIRTUAL TABLE" in sql.upper()


def get_row_count(conn: sqlite3.Connection, table: str) -> int:
    try:
        return conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()[0]  # noqa: S608
    except Exception:
        return -1


def copy_table(
    source_conn: sqlite3.Connection,
    dest_conn: sqlite3.Connection,
    source_name: str,
    dest_name: str,
    dry_run: bool,
) -> int:
    """Copy a table from source_conn into dest_conn.

    Creates the table in dest if it doesn't exist, then inserts all rows.
    Returns the number of rows copied (or -1 on error).
    """
    # Get the CREATE TABLE statement from source
    row = source_conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (source_name,)
    ).fetchone()
    if row is None or row[0] is None:
        log(f"    WARNING: no sql found for table '{source_name}', skipping")
        return 0

    create_sql: str = row[0]

    # Rewrite the table name in the CREATE statement if renaming
    if dest_name != source_name:
        # Replace the first occurrence of the source name after CREATE TABLE
        create_sql = create_sql.replace(
            f'"{source_name}"', f'"{dest_name}"', 1
        )
        create_sql = create_sql.replace(
            f"`{source_name}`", f"`{dest_name}`", 1
        )
        # Plain name replacement (must be careful with word boundaries)
        # Use a targeted replace on the name token right after TABLE
        import re
        create_sql = re.sub(
            r"(?i)(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?)" + re.escape(source_name) + r"\b",
            rf"\g<1>{dest_name}",
            create_sql,
            count=1,
        )

    # Check if destination table already exists
    existing = dest_conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (dest_name,)
    ).fetchone()

    if dry_run:
        row_count = get_row_count(source_conn, source_name)
        if existing:
            dest_count = get_row_count(dest_conn, dest_name)
            if dest_count > 0 or row_count == 0:
                log(f"    [dry-run] SKIP (already exists with {dest_count} rows): {dest_name}")
            else:
                log(f"    [dry-run] MERGE into empty table: {source_name} → {dest_name} ({row_count} rows)")
        else:
            log(f"    [dry-run] COPY: {source_name} → {dest_name} ({row_count} rows)")
        return row_count

    if existing:
        # Table already exists — but if it's empty and source has data, merge rows in
        dest_count = get_row_count(dest_conn, dest_name)
        src_count = get_row_count(source_conn, source_name)
        if dest_count > 0 or src_count == 0:
            log(f"    SKIP (already exists with {dest_count} rows): {dest_name}")
            return dest_count
        # Table exists but is empty; source has data — insert rows
        rows = source_conn.execute(f"SELECT * FROM [{source_name}]").fetchall()  # noqa: S608
        if rows:
            placeholders = ", ".join(["?"] * len(rows[0]))
            dest_conn.executemany(
                f"INSERT OR IGNORE INTO [{dest_name}] VALUES ({placeholders})",  # noqa: S608
                rows,
            )
            dest_conn.commit()
        log(f"    MERGED into existing empty table: {dest_name} ({len(rows)} rows)")
        return len(rows)

    # Create the table
    dest_conn.execute(create_sql)

    # Copy rows using INSERT OR IGNORE to be safe on constraint conflicts
    rows = source_conn.execute(f"SELECT * FROM [{source_name}]").fetchall()  # noqa: S608
    if rows:
        placeholders = ", ".join(["?"] * len(rows[0]))
        dest_conn.executemany(
            f"INSERT OR IGNORE INTO [{dest_name}] VALUES ({placeholders})",  # noqa: S608
            rows,
        )

    dest_conn.commit()
    return len(rows)


def copy_indexes(
    source_conn: sqlite3.Connection,
    dest_conn: sqlite3.Connection,
    source_table: str,
    dest_table: str,
    dry_run: bool,
) -> None:
    """Copy indexes from source table to dest table."""
    rows = source_conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL",
        (source_table,),
    ).fetchall()

    for idx_name, idx_sql in rows:
        if idx_sql is None:
            continue
        # Rewrite table name and index name if renaming
        new_idx_name = idx_name if dest_table == source_table else f"{dest_table}_{idx_name}"
        new_idx_sql = idx_sql.replace(
            f" {idx_name} ", f" {new_idx_name} "
        )
        if dest_table != source_table:
            new_idx_sql = new_idx_sql.replace(
                f" ON {source_table} ", f" ON {dest_table} "
            ).replace(
                f' ON "{source_table}" ', f' ON "{dest_table}" '
            ).replace(
                f" ON [{source_table}] ", f" ON [{dest_table}] "
            )

        existing = dest_conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name=?", (new_idx_name,)
        ).fetchone()
        if existing:
            continue

        if dry_run:
            log(f"      [dry-run] INDEX: {new_idx_name}")
            continue

        try:
            dest_conn.execute(new_idx_sql)
            dest_conn.commit()
        except sqlite3.OperationalError as e:
            log(f"      WARNING: could not create index '{new_idx_name}': {e}")


# ---------------------------------------------------------------------------
# Source validation
# ---------------------------------------------------------------------------


def validate_sources() -> None:
    """Abort loudly if expected source files are missing."""
    if not REOS_DATA.exists():
        abort(f"Source directory not found: {REOS_DATA}")

    missing = []
    for p in [REOS_DB, PLAY_DB, CAIRN_DB]:
        if not p.exists():
            missing.append(str(p))

    if missing:
        abort("Expected source databases not found:\n  " + "\n  ".join(missing))

    log("Sources validated:")
    log(f"  reos.db  : {REOS_DB}")
    log(f"  play.db  : {PLAY_DB}")
    log(f"  cairn.db : {CAIRN_DB}")


# ---------------------------------------------------------------------------
# Migration steps
# ---------------------------------------------------------------------------


def migrate_play_db(dest_conn: sqlite3.Connection, dry_run: bool) -> dict[str, int]:
    """Step 1: play.db is the base — copy all non-FTS tables."""
    log("\n[1/4] Copying play.db tables (base database)...")
    counts: dict[str, int] = {}

    src = sqlite3.connect(str(PLAY_DB))
    try:
        tables = get_tables(src)
        for table in tables:
            if is_fts_table(table) or is_virtual_table(src, table):
                log(f"    SKIP (FTS/virtual): {table}")
                continue
            n = copy_table(src, dest_conn, table, table, dry_run)
            copy_indexes(src, dest_conn, table, table, dry_run)
            counts[table] = n
            log(f"    OK: {table} ({n} rows)")
    finally:
        src.close()

    return counts


def migrate_reos_db(dest_conn: sqlite3.Connection, dry_run: bool) -> dict[str, int]:
    """Step 2: reos.db — copy tables with conflict renaming."""
    log("\n[2/4] Copying reos.db tables...")
    counts: dict[str, int] = {}

    # Tables to rename
    RENAMES = {
        "conversations": "legacy_conversations",
        "messages": "legacy_messages",
        "schema_version": "reos_schema_version",
    }

    src = sqlite3.connect(str(REOS_DB))
    try:
        tables = get_tables(src)
        for table in tables:
            if is_fts_table(table) or is_virtual_table(src, table):
                log(f"    SKIP (FTS/virtual): {table}")
                continue

            dest_name = RENAMES.get(table, table)
            if dest_name != table:
                log(f"    RENAME: {table} → {dest_name}")

            n = copy_table(src, dest_conn, table, dest_name, dry_run)
            copy_indexes(src, dest_conn, table, dest_name, dry_run)
            counts[dest_name] = n
            log(f"    OK: {dest_name} ({n} rows)")
    finally:
        src.close()

    return counts


def migrate_cairn_db(dest_conn: sqlite3.Connection, dry_run: bool) -> dict[str, int]:
    """Step 3: cairn.db — copy all tables directly (no conflicts)."""
    log("\n[3/4] Copying cairn.db tables...")
    counts: dict[str, int] = {}

    src = sqlite3.connect(str(CAIRN_DB))
    try:
        tables = get_tables(src)
        for table in tables:
            if is_fts_table(table) or is_virtual_table(src, table):
                log(f"    SKIP (FTS/virtual): {table}")
                continue
            n = copy_table(src, dest_conn, table, table, dry_run)
            copy_indexes(src, dest_conn, table, table, dry_run)
            counts[table] = n
            log(f"    OK: {table} ({n} rows)")
    finally:
        src.close()

    return counts


def copy_filesystem_assets(dry_run: bool) -> None:
    """Step 4: Copy non-database files and per-user subdirectories."""
    log("\n[4/4] Copying filesystem assets...")

    # Per-user subdirectories: everything in ~/.reos-data/ that is a directory
    # but NOT 'play' or 'backups' (which we handle separately below)
    skip_dirs = {"play", "backups"}

    for item in REOS_DATA.iterdir():
        if item.is_dir() and item.name not in skip_dirs:
            dest = TALKINGROCK_DIR / item.name
            if dry_run:
                log(f"  [dry-run] COPY DIR: {item} → {dest}")
            else:
                if dest.exists():
                    log(f"  SKIP (exists): {dest}")
                else:
                    shutil.copytree(str(item), str(dest))
                    log(f"  COPIED DIR: {item.name}/")

    # Individual files in ~/.reos-data/ (skip the db files, skip play/)
    skip_files = {"reos.db"}
    for item in REOS_DATA.iterdir():
        if item.is_file() and item.name not in skip_files:
            dest = TALKINGROCK_DIR / item.name
            if dry_run:
                log(f"  [dry-run] COPY FILE: {item.name}")
            else:
                if dest.exists():
                    log(f"  SKIP (exists): {dest.name}")
                else:
                    shutil.copy2(str(item), str(dest))
                    log(f"  COPIED FILE: {item.name}")

    # backups/ directory
    backups_src = REOS_DATA / "backups"
    if backups_src.exists():
        backups_dest = TALKINGROCK_DIR / "backups"
        if dry_run:
            log("  [dry-run] COPY DIR: backups/")
        else:
            if backups_dest.exists():
                log("  SKIP (exists): backups/")
            else:
                shutil.copytree(str(backups_src), str(backups_dest))
                log("  COPIED DIR: backups/")

    # .encrypted marker
    if ENCRYPTED_MARKER.exists():
        dest_marker = TALKINGROCK_DIR / ".encrypted"
        if dry_run:
            log("  [dry-run] COPY FILE: .encrypted")
        else:
            if not dest_marker.exists():
                shutil.copy2(str(ENCRYPTED_MARKER), str(dest_marker))
                log("  COPIED FILE: .encrypted")


def migrate_keyring(dry_run: bool) -> None:
    """Attempt to copy keyring entries from com.reos.providers to com.talkingrock.providers."""
    log("\n[optional] Migrating keyring entries...")
    try:
        import keyring  # type: ignore[import]
    except ImportError:
        log("  SKIP: keyring library not available")
        return

    try:
        # Common provider key names used by Cairn/ReOS
        key_names = ["ollama", "api_key", "salt", "encryption_key"]
        old_service = "com.reos.providers"
        new_service = "com.talkingrock.providers"
        migrated = 0

        for key in key_names:
            try:
                value = keyring.get_password(old_service, key)
                if value is not None:
                    if dry_run:
                        log(f"  [dry-run] KEYRING: {old_service}/{key} → {new_service}/{key}")
                    else:
                        existing = keyring.get_password(new_service, key)
                        if existing is None:
                            keyring.set_password(new_service, key, value)
                            log(f"  MIGRATED: {key}")
                            migrated += 1
                        else:
                            log(f"  SKIP (already exists): {new_service}/{key}")
            except Exception as e:
                log(f"  WARNING: could not migrate key '{key}': {e}")

        if migrated == 0 and not dry_run:
            log("  No keyring entries found to migrate (normal if using file-based secrets)")

    except Exception as e:
        log(f"  WARNING: keyring migration failed: {e}")


# ---------------------------------------------------------------------------
# Verification summary
# ---------------------------------------------------------------------------


def print_verification_summary(dest_conn: sqlite3.Connection) -> None:
    log("\n" + "=" * 60)
    log("VERIFICATION SUMMARY")
    log("=" * 60)
    log(f"Database: {TARGET_DB}")

    tables = get_tables(dest_conn)
    log(f"\nTotal tables: {len(tables)}")
    log("")

    # Group by source for clarity
    legacy_names = {"legacy_conversations", "legacy_messages", "reos_schema_version"}
    reos_legacy = [t for t in tables if t in legacy_names]
    play_tables = sorted([t for t in tables if t not in reos_legacy])

    for table in play_tables + reos_legacy:
        count = get_row_count(dest_conn, table)
        tag = " (reos legacy)" if table in reos_legacy else ""
        log(f"  {table:<45} {count:>8} rows{tag}")

    log("")
    log("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Migrate ~/.reos-data/ databases to ~/.talkingrock/talkingrock.db"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )
    args = parser.parse_args()
    dry_run: bool = args.dry_run

    if dry_run:
        log("DRY RUN MODE — no changes will be made\n")

    # --- Phase 0: Validate sources ---
    validate_sources()

    # --- Phase 1: Check idempotency ---
    if TARGET_DB.exists():
        log(f"\nAlready migrated: {TARGET_DB} exists.")
        log("If you want to re-run, remove ~/.talkingrock/ first.")
        sys.exit(0)

    # --- Phase 2: Create target directory ---
    if not dry_run:
        TALKINGROCK_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        log(f"\nCreated: {TALKINGROCK_DIR} (mode 0700)")
    else:
        log(f"\n[dry-run] Would create: {TALKINGROCK_DIR} (mode 0700)")

    # --- Phase 3: Build unified database ---
    # Use play.db as the base (file copy preserves WAL state and page size)
    if not dry_run:
        log(f"\nCopying play.db as base → {TARGET_DB}")
        shutil.copy2(str(PLAY_DB), str(TARGET_DB))
        dest_conn = sqlite3.connect(str(TARGET_DB))
        dest_conn.execute("PRAGMA journal_mode=WAL")
        # Disable FK checks during migration — renamed tables break FK references
        dest_conn.execute("PRAGMA foreign_keys=OFF")
    else:
        log(f"\n[dry-run] Would copy play.db as base → {TARGET_DB}")
        # For dry-run, open play.db read-only to enumerate tables
        dest_conn = sqlite3.connect(str(PLAY_DB))

    try:
        all_counts: dict[str, int] = {}

        if dry_run:
            # In dry-run, show play.db tables that would be the base
            log("\n[1/4] play.db tables (already in base copy):")
            src = sqlite3.connect(str(PLAY_DB))
            try:
                for table in get_tables(src):
                    if is_fts_table(table) or is_virtual_table(src, table):
                        log(f"    SKIP (FTS/virtual): {table}")
                        continue
                    n = get_row_count(src, table)
                    log(f"    OK: {table} ({n} rows)")
                    all_counts[table] = n
            finally:
                src.close()

            # Show reos.db tables
            counts = migrate_reos_db(dest_conn, dry_run=True)
            all_counts.update(counts)

            # Show cairn.db tables
            counts = migrate_cairn_db(dest_conn, dry_run=True)
            all_counts.update(counts)
        else:
            # play.db is already in the base copy; we just need to add reos.db and cairn.db
            log("\n[1/4] play.db is the base copy — already in target.")

            counts = migrate_reos_db(dest_conn, dry_run=False)
            all_counts.update(counts)

            counts = migrate_cairn_db(dest_conn, dry_run=False)
            all_counts.update(counts)

    finally:
        if not dry_run:
            dest_conn.close()
        else:
            # dest_conn was opened on play.db read-only; close it
            dest_conn.close()

    # --- Phase 4: Copy filesystem assets ---
    copy_filesystem_assets(dry_run)

    # --- Phase 5: Keyring migration ---
    migrate_keyring(dry_run)

    # --- Phase 6: Verification summary ---
    if not dry_run:
        final_conn = sqlite3.connect(str(TARGET_DB))
        try:
            print_verification_summary(final_conn)
        finally:
            final_conn.close()
    else:
        log("\n[dry-run] Skipping verification summary (no database written)")

    log("\n" + "=" * 60)
    if dry_run:
        log("DRY RUN COMPLETE — no changes were made.")
    else:
        log("MIGRATION COMPLETE")
        log("")
        log("Next steps:")
        log("  1. Update app config to use ~/.talkingrock/talkingrock.db")
        log("  2. Run the app once — it will apply v18 migration (schema_version rename)")
        log("  3. Verify FTS tables are rebuilt by the app's migration system")
        log("  4. Once verified, you may archive ~/.reos-data/")
    log("=" * 60)


if __name__ == "__main__":
    main()
