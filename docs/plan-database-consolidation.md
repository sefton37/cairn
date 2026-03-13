# Plan: Database Consolidation — Three DBs into One

## Context

Three SQLite databases currently serve Cairn's persistence layer:

| Database | Path on disk | Defined in | Purpose |
|----------|-------------|------------|---------|
| `reos.db` | `~/.reos-data/reos.db` | `src/cairn/db.py:25` | Events, sessions, classifications, repos, app_state, agent_personas, conversations (legacy), messages (legacy), code intelligence tables |
| `play.db` | `~/.reos-data/play/play.db` | `src/cairn/play_db.py:65` | Acts, scenes, blocks, memories, conversations (live), messages (live), FTS tables, cc_agents, priority learning |
| `cairn.db` | `~/.reos-data/play/.cairn/cairn.db` | `src/cairn/cairn/store.py:62` | Metadata overlays, contact_links, activity_log, priority_queue, coherence_traces, email intelligence, health tables |

The three-database structure is an artifact of ReOS/RIVA extraction history (2026-02-28). The `reos.db` filename and `~/.reos-data/` path were deliberately preserved at that time to avoid data loss; that compatibility window has now elapsed and consolidation is appropriate.

**Target state:** One database at `~/.talkingrock/talkingrock.db`, with the data directory renamed from `~/.reos-data/` to `~/.talkingrock/`.

---

## Critical Problem: Table Name Conflicts

The three databases share three table names whose schemas are **incompatible**:

| Table | reos.db schema | play.db schema | Verdict |
|-------|----------------|----------------|---------|
| `conversations` | `id, title, started_at, last_active_at, context_summary` — lightweight, for legacy chat | `id, block_id, status, started_at, last_message_at, …, compression_model` — full lifecycle | Incompatible |
| `messages` | `id, conversation_id, role, content, message_type, metadata, created_at` — generic | `id, conversation_id, block_id, role, content, position, …, active_act_id` — Play-linked | Incompatible |
| `schema_version` | `version, applied_at, description, checksum` — migration runner format | `version INTEGER PRIMARY KEY` — integer-only | Incompatible |

The `conversations` and `messages` tables in `reos.db` appear to be dead code: the live conversation lifecycle runs entirely in `play.db` (confirmed by `src/cairn/services/conversation_service.py`, `memory_service.py`, and the `play_db.py` v12 migration comment). However, this must be verified before discarding.

**Resolution required for each conflict before writing any code:**
1. `conversations`/`messages` in `reos.db`: Confirm they contain no live data that isn't already in `play.db`. If confirmed dead, drop them. If live, rename to `legacy_conversations` / `legacy_messages`.
2. `schema_version`: Use a single unified migration runner. Both tables can coexist under different names (`schema_version` for reos.db migrations, `play_schema_version` for play.db's integer-only version).

---

## Approach A (Recommended): Single-Phase Consolidation with New DB File

Create `~/.talkingrock/talkingrock.db` as the unified database. Copy data from all three sources. Switch all connection points to the new path. Keep old databases as backups.

**Why this wins:**
- Clean break; no legacy path fragments survive in code
- The directory rename (`~/.reos-data` → `~/.talkingrock`) aligns with the project's public name
- All table conflicts resolved once, in one place
- Rollback is simple: point the env var back
- Aligns with the project's local-first philosophy (one file, one truth)

**Why it is risky:** It touches the most files of any option. Missing one path reference means a silent data loss or a crash on first write after migration.

## Approach B: Incremental Merge (reos.db → play.db first)

Merge `reos.db` into `play.db` as a first step, then merge `cairn.db` into `play.db` in a second step, keeping `~/.reos-data/` directory name throughout, and only renaming the directory last.

**Trade-offs:**
- Lower blast radius per step; easier to test in isolation
- Requires two complete test cycles instead of one
- The directory rename still has to happen and still touches all path references
- Does not reduce total code changes materially

**Verdict:** Approach A is preferred because the directory rename must happen regardless. The incremental approach adds two test cycles without reducing the total change surface.

## Approach C: Symlink Bridge (zero-downtime transition)

Create `~/.talkingrock/` as a directory containing `talkingrock.db`, and add symlinks `~/.reos-data → ~/.talkingrock/` so old code paths continue to work while new paths are introduced.

**Trade-offs:**
- Allows a staged rollout with zero code changes required immediately
- But: defeats the purpose of the consolidation (three DB files still exist)
- Symlinks are fragile across user sessions, `chroot`, and some backup tools
- Leaves the `play/` subdirectory structure intact, perpetuating the three-DB architecture

**Verdict:** Rejected. This is a workaround, not a consolidation.

---

## Implementation Steps (Approach A)

### Phase 0: Pre-conditions (no code changes yet)

**Step 0.1** — Audit live data in `reos.db` `conversations` and `messages` tables.

Run against the live database:
```sql
SELECT COUNT(*) FROM conversations;
SELECT COUNT(*) FROM messages;
```

If both are 0 or their data is a subset of what's already in `play.db`, those tables can be dropped from `reos.db` before migration. If they contain live data not in `play.db`, they must be renamed to `legacy_conversations` / `legacy_messages` in the unified schema.

**Step 0.2** — Inventory `cairn.db` health tables.

`CairnStore._init_schema()` delegates health table creation to:
- `src/cairn/cairn/health/anti_nag.py`: `init_health_tables()`, `init_health_check_defaults()`
- `src/cairn/cairn/health/snapshot.py`: `init_snapshot_tables()`

These create: `health_check_configs`, `health_surfacing_log`, `health_acknowledgments`, `health_snapshots`, `pattern_drift_events`. None of these conflict with other databases.

---

### Phase 1: New schema module

**File to create:** `src/cairn/talkingrock_db.py`

This becomes the single database class for the unified store. It:
1. Accepts `db_path` with default `~/.talkingrock/talkingrock.db`
2. Reads the data dir from a new env var `TALKINGROCK_DATA_DIR` (with fallback to `REOS_DATA_DIR` for backward compat during transition)
3. On `migrate()`, creates all tables from all three current schemas, with conflict resolution applied (see above)
4. Replaces the role currently played by `db.py`'s `Database` class for `reos.db` tables

The `play_db.py` module-level functions (`_play_db_path`, `_get_connection`) are updated to derive their path from the unified `settings.data_dir` pointing at `~/.talkingrock/`.

The `CairnStore` class receives its path from the same source instead of being constructed with `Path(play_path) / ".cairn" / "cairn.db"`.

---

### Phase 2: Settings update

**File:** `src/cairn/settings.py`

Change:
```python
# line 29 (current)
data_dir: Path = Path(os.environ.get("REOS_DATA_DIR", Path.home() / ".reos-data"))
```
To:
```python
data_dir: Path = Path(
    os.environ.get("TALKINGROCK_DATA_DIR")
    or os.environ.get("REOS_DATA_DIR")
    or Path.home() / ".talkingrock"
)
```

All other `settings.*` derived paths (`events_path`, `audit_path`, `log_path`) follow automatically because they are defined as `data_dir / "..."`.

The env var `REOS_DATA_DIR` continues to work during transition; tests that set it do not need to change immediately.

---

### Phase 3: Update `db.py`

**File:** `src/cairn/db.py`

Line 25: Change `settings.data_dir / "reos.db"` to `settings.data_dir / "talkingrock.db"`.

The `Database` class is otherwise unchanged. Its migration runner (`migrations/runner.py`) tracks its own `schema_version` table and is unaffected.

---

### Phase 4: Update `play_db.py`

**File:** `src/cairn/play_db.py`

Line 65: Change `return base / "play" / "play.db"` to `return base / "talkingrock.db"`.

Lines 1849, 1937: Same base path used in migration helper functions — update to match.

The `schema_version` table conflict between `reos.db` (which uses the migration runner format with `applied_at`, `description`, `checksum` columns) and `play.db` (which uses `version INTEGER PRIMARY KEY` only) must be resolved. Recommended resolution: rename play.db's version table to `play_schema_version` in the v18 migration of `play_db.py`. The migration runner's `schema_version` table is kept as-is.

---

### Phase 5: Update `CairnStore` path construction

**Files containing `Path(play_path) / ".cairn" / "cairn.db"`:**

| File | Lines |
|------|-------|
| `src/cairn/rpc_handlers/system.py` | 64, 120, 141, 155, 186, 384, 438 |
| `src/cairn/rpc_handlers/health.py` | 38 |
| `src/cairn/rpc_handlers/play.py` | 360 |
| `src/cairn/mcp_tools.py` | 386 |
| `src/cairn/agent.py` | 972–973 |

All of these compute a path from `play_path` and then construct a `CairnStore`. After consolidation, `CairnStore` must be pointed at the unified database. Two sub-approaches:

**Option A (simpler):** Add a module-level `get_cairn_store()` function in `src/cairn/cairn/store.py` that constructs from `settings.data_dir / "talkingrock.db"`, analogous to `db.py`'s `get_db()`. All call sites replace `CairnStore(Path(play_path) / ".cairn" / "cairn.db")` with `get_cairn_store()`.

**Option B (more explicit):** Pass the unified `Database` connection to `CairnStore`, eliminating the second connection entirely by having `CairnStore` share the same SQLite file.

Option A is lower risk because it preserves `CairnStore`'s existing connection management and limits the blast radius to path construction only.

---

### Phase 6: Update hardcoded `~/.reos-data` paths

These files contain hardcoded paths that bypass `settings.data_dir`:

| File | Line | Content |
|------|------|---------|
| `src/cairn/documents/storage.py` | 47 | `~/.reos-data/play/documents` |
| `src/cairn/documents/storage.py` | 55 | `~/.reos-data/play/acts/{act_id}/documents` |
| `src/cairn/auth.py` | 63 | `Path.home() / ".reos-data" / self.username` |
| `src/cairn/recovery.py` | 371 | `Path.home() / ".reos-data" / username` |
| `src/cairn/reasoning/safety.py` | 211 | `Path.home() / ".reos-data" / "backups"` |
| `src/cairn/app.py` | 85 | Error message string (non-functional, update for accuracy) |
| `src/cairn/agent.py` | 972 | `Path(self._db.db_path).parent / ".reos-data"` — **wrong**: derives `.reos-data` as a subdirectory of the db file's parent directory. This is a bug regardless of the migration. |

For `documents/storage.py`: replace with `settings.data_dir / "play" / "documents"` and `settings.data_dir / "play" / "acts" / act_id / "documents"`.

For `auth.py` line 63: `Session.get_user_data_root()` is used by `CryptoStorage` and controls per-user isolation. Change to `Path.home() / ".talkingrock" / self.username`. This also affects the `REOS_DATA_DIR`-based play root in `play_fs.py` for authenticated sessions.

For `recovery.py` line 371: Same pattern as `auth.py` — change to `Path.home() / ".talkingrock" / username`.

For `agent.py` line 972: The current code computes `data_dir = Path(self._db.db_path).parent / ".reos-data"` and then `cairn_db_path = data_dir / "cairn.db"`. After consolidation, replace entirely with `get_cairn_store()` (see Phase 5, Option A).

---

### Phase 7: Update `db_crypto.py` encrypted marker

**File:** `src/cairn/db_crypto.py`

The `_ENCRYPTED_MARKER` file (`.encrypted`) is written to the parent directory of each database file. After consolidation, there is only one database and one marker file. No code change needed — the marker path is computed dynamically from the db path. However, when creating the migration script, the migration must copy or re-create the `.encrypted` marker at `~/.talkingrock/.encrypted` if one existed at `~/.reos-data/`.

---

### Phase 8: Update the keyring service name

**File:** `src/cairn/providers/secrets.py`

Line 17: `SERVICE_NAME = "com.reos.providers"` — this is a GNOME Keyring / SecretService entry name. Changing it will cause existing stored API keys to become inaccessible on next login. **This must not be changed silently.**

Recommended: Change the constant to `"com.talkingrock.providers"` AND add a one-time migration function that reads from the old service name and writes to the new one on first run. Without this migration step, users will be prompted to re-enter API keys.

**File:** `src/cairn/auth.py`

Line 39: `KEYRING_ENCRYPTION_SERVICE = "com.cairn.encryption"` — already uses `cairn`, not `reos`. No change needed here.

---

### Phase 9: Write the data migration script

**File to create:** `scripts/migrate_to_talkingrock.py`

This is a one-time, run-once script that:

1. Verifies old databases exist at `~/.reos-data/reos.db`, `~/.reos-data/play/play.db`, `~/.reos-data/play/.cairn/cairn.db`
2. Creates `~/.talkingrock/` directory with mode `0700`
3. Uses `sqlite3` directly (no app imports) to avoid circular dependencies
4. Opens each source database (using plaintext connection since encryption key is not available in script context — **this is a limitation: see Risks**)
5. Creates schema in `talkingrock.db` by attaching it and running `CREATE TABLE IF NOT EXISTS` for all tables
6. Copies data with `INSERT OR IGNORE INTO talkingrock.db.<table> SELECT * FROM <table>` for each non-conflicting table
7. Handles the `conversations`/`messages` conflict explicitly based on Step 0.1 findings
8. Renames `schema_version` from play.db to `play_schema_version` during copy
9. Copies `.encrypted` marker file if present
10. Migrates GNOME Keyring entry from `com.reos.providers` to `com.talkingrock.providers` using the `keyring` library
11. Backs up old databases to `~/.reos-data/backups/YYYYMMDD/` (does not delete originals)
12. Prints a summary: tables copied, rows per table, conflicts resolved

---

### Phase 10: Update `.gitignore`

**File:** `/home/kellogg/dev/Cairn/.gitignore`

Line 26: Change `.reos-data/` to `.talkingrock/` (and optionally add `.reos-data/` as a comment-tagged legacy entry for users who haven't migrated).

---

### Phase 11: Update tests

The `REOS_DATA_DIR` env var is set in 44+ test fixtures across the test suite. The var must continue to work (settings.py keeps the fallback). No immediate test changes are required, **but** any test that asserts the path contains `.reos-data` must be updated:

| File | Line | Issue |
|------|------|-------|
| `tests/test_auth.py` | 133 | `assert ".reos-data" in str(data_root)` — will fail after migration |

All other test uses of `REOS_DATA_DIR` set it to a `tmp_path` value and do not assert on the string itself; those are unaffected.

---

### Phase 12: Update documentation

| File | Change needed |
|------|--------------|
| `CLAUDE.md` | Line 199: Update backward compat note; line 405: update DB path |
| `docs/the-play.md` | Line 325: Still says `reos.db` |
| `docs/ui-migration-typescript.md` | Lines 170–172: `.reos-data/` and `reos.db` references |
| `src/cairn/documents/storage.py` | Module docstring line 4: `~/.reos-data/play/documents` |
| `src/cairn/logging_setup.py` | Module docstring line 17: `.reos-data/` reference |
| `src/cairn/db.py` | Class docstring line 17: "ReOS events" |
| `.github/copilot-instructions.md` | Line 77: `.reos-data/` |

---

## Files Affected

### Create
- `scripts/migrate_to_talkingrock.py` — one-time migration script

### Modify (source)
| File | Change summary |
|------|---------------|
| `src/cairn/settings.py` | Change default `data_dir` to `~/.talkingrock`; add `TALKINGROCK_DATA_DIR` env var |
| `src/cairn/db.py` | Change db filename `reos.db` → `talkingrock.db` (line 25) |
| `src/cairn/play_db.py` | Change db path (line 65); rename `schema_version` → `play_schema_version` in fresh schema + v18 migration; update helper lines 1849, 1937 |
| `src/cairn/cairn/store.py` | Add `get_cairn_store()` factory function; update path default |
| `src/cairn/rpc_handlers/system.py` | Replace 7 `CairnStore(Path(play_path) / ".cairn" / "cairn.db")` calls |
| `src/cairn/rpc_handlers/health.py` | Replace 1 call (line 38) |
| `src/cairn/rpc_handlers/play.py` | Replace 1 call (line 360) |
| `src/cairn/mcp_tools.py` | Replace 1 call (line 386) |
| `src/cairn/agent.py` | Fix lines 972–973 (was already computing wrong path) |
| `src/cairn/documents/storage.py` | Lines 47, 55: use `settings.data_dir` |
| `src/cairn/auth.py` | Line 63: `.reos-data` → `.talkingrock` |
| `src/cairn/recovery.py` | Line 371: `.reos-data` → `.talkingrock` |
| `src/cairn/reasoning/safety.py` | Line 211: `.reos-data` → `.talkingrock` |
| `src/cairn/providers/secrets.py` | Line 17: update `SERVICE_NAME`; add keyring migration |
| `src/cairn/app.py` | Line 85: update error message string |
| `.gitignore` | Line 26: `.reos-data/` → `.talkingrock/` |

### Modify (tests)
| File | Change summary |
|------|---------------|
| `tests/test_auth.py` | Line 133: update path assertion |

### Modify (documentation)
| File | Change summary |
|------|---------------|
| `CLAUDE.md` | Lines 199, 405 |
| `docs/the-play.md` | Line 325 |
| `docs/ui-migration-typescript.md` | Lines 170–172 |
| `src/cairn/documents/storage.py` | Module docstring |
| `src/cairn/logging_setup.py` | Module docstring |
| `src/cairn/db.py` | Class docstring |
| `.github/copilot-instructions.md` | Line 77 |

---

## Risks and Mitigations

### Risk 1: SQLCipher encryption makes data migration impossible from script context

**Severity: High**

`db_crypto.py` encrypts databases when `pysqlcipher3` is installed and a key is active. The migration script runs outside an authenticated session, so it cannot decrypt the databases to copy data.

**Mitigations:**
- Option A (preferred): The migration script operates at the file level — it copies the raw `.db` files to the new paths rather than reading row data. Then code changes point to the new paths. SQLCipher will still work because the same key material (from the keyring) opens the file regardless of path. The `.encrypted` marker file must also be copied.
- Option B (fallback): Run the migration as part of the application's authenticated startup sequence, where the key is already loaded into `db_crypto._active_key`. This requires a startup-time migration check in `app.py` or `ui_rpc_server.py`.

**Recommendation:** Use Option A for the file-level migration script. SQLite ATTACH DATABASE only works when keys match; since all databases use the same DEK (from the same keyring entry), a SQLCipher-aware migration using `ATTACH DATABASE ... KEY "x'...'"` is feasible if the script retrieves the DEK from the keyring at runtime.

### Risk 2: `schema_version` table conflict

**Severity: Medium**

`reos.db` uses `schema_version(version, applied_at, description, checksum)` (migration runner format). `play.db` uses `schema_version(version INTEGER PRIMARY KEY)` (integer-only). Both tables exist in the target unified database.

**Mitigation:** In `play_db.py`, add a v18 migration that renames the play schema version table to `play_schema_version`. The migration runner's `schema_version` is kept. The unified database has `play_schema_version` (integer) and `schema_version` (migration runner format). No conflict.

### Risk 3: `conversations` and `messages` table conflict

**Severity: Medium**

Both `reos.db` and `play.db` define `conversations` and `messages` with incompatible schemas. The `reos.db` versions appear unused (all live conversation code targets `play.db`), but this must be confirmed empirically (Step 0.1).

**Mitigation:** If confirmed empty, drop the `reos.db` versions entirely from the unified schema. If they contain live data, rename to `legacy_conversations` and `legacy_messages` and update the handful of callers (primarily in `src/cairn/http_rpc.py` and any code referencing `reos.db` conversations directly — search for usages before coding).

### Risk 4: Per-user authenticated play root (`~/.reos-data/{username}/play`)

**Severity: Medium**

`Session.get_user_data_root()` in `auth.py` line 63 returns `Path.home() / ".reos-data" / self.username`. This per-user path is used by `CryptoStorage` and `play_fs.play_root()` when an authenticated session is active. Changing to `.talkingrock` in code without migrating existing per-user data at `~/.reos-data/{username}/` would silently start a fresh data directory for any user who has previously authenticated.

**Mitigation:** The migration script must enumerate `~/.reos-data/*/` and, for each `username/` subdirectory, create `~/.talkingrock/username/` with the same contents (file-level copy, preserving encryption).

### Risk 5: Keyring service name change breaks stored API keys

**Severity: Medium**

Changing `SERVICE_NAME` in `secrets.py` from `"com.reos.providers"` to `"com.talkingrock.providers"` will cause the application to not find previously stored API keys on the next run.

**Mitigation:** The migration script and/or the `check_keyring_available()` call at startup should detect the presence of entries under the old service name and copy them to the new name. The old entries should then be deleted (after confirmation). The `keyring` library supports `get_password(old_service, provider)` / `set_password(new_service, provider, value)` / `delete_password(old_service, provider)` — this is straightforward.

### Risk 6: Archive/documentation references in `docs/archive/`

**Severity: Low**

Several files under `docs/archive/` reference `~/.reos-data/` and `reos.db`. These are historical documents and do not need code changes, but they may confuse future readers.

**Mitigation:** Add a note at the top of the affected archive documents: "NOTE: This document predates the consolidation to ~/.talkingrock/ (2026-03). Path references are historical." This is a low-priority documentation task.

### Risk 7: `agent.py` cairn_db_path construction is already wrong

**Severity: Low (pre-existing bug)**

`agent.py` lines 972–973 compute:
```python
data_dir = Path(self._db.db_path).parent / ".reos-data"
cairn_db_path = data_dir / "cairn.db"
```
When `self._db.db_path` is `~/.reos-data/reos.db`, `parent` is `~/.reos-data/`, and `data_dir` becomes `~/.reos-data/.reos-data/` — which does not exist. This is a pre-existing bug that the migration will surface and fix (replace with `get_cairn_store()`).

---

## Migration Script Design

```
scripts/migrate_to_talkingrock.py
```

**Inputs:** No arguments required. Auto-detects `~/.reos-data/`.

**Algorithm:**
1. Check `~/.reos-data/` exists and contains the expected files. Abort loudly if not.
2. Check `~/.talkingrock/` does not already exist (idempotency guard). If it does, and `talkingrock.db` is present, print "Already migrated" and exit 0.
3. Create `~/.talkingrock/` with mode `0700`.
4. **File-level copy strategy** (recommended given encryption):
   - Copy `~/.reos-data/reos.db` → `~/.talkingrock/reos.db.bak` (backup only)
   - Copy `~/.reos-data/play/play.db` → `~/.talkingrock/talkingrock.db` (becomes the base)
   - Attach `~/.reos-data/reos.db` to `talkingrock.db` via `ATTACH DATABASE` and copy non-conflicting tables
   - Attach `~/.reos-data/play/.cairn/cairn.db` and copy all tables
   - Copy `.encrypted` markers as needed
5. Copy per-user subdirectories: `~/.reos-data/*/` → `~/.talkingrock/*/`
6. Copy non-database files: `events.jsonl`, `audit.log`, `cairn.log`, `backups/`
7. Migrate keyring entries: `com.reos.providers` → `com.talkingrock.providers`
8. Print verification summary: list of tables in new DB with row counts
9. Print next step: "Run the updated application to complete migration. Old data remains at ~/.reos-data/."

**What the script does NOT do:**
- Delete `~/.reos-data/` (kept as rollback)
- Start or stop the application
- Touch code files

---

## Testing Strategy

### Unit tests (no live databases)

All existing tests use `monkeypatch.setenv("REOS_DATA_DIR", str(tmp_path))` or `os.environ["REOS_DATA_DIR"]`. Because `settings.py` still accepts `REOS_DATA_DIR` as a fallback, all existing tests continue to pass without changes (except `test_auth.py:133`).

New tests to write:

1. **`tests/test_settings.py`**: Add a test verifying that `TALKINGROCK_DATA_DIR` takes precedence over `REOS_DATA_DIR`, which takes precedence over `~/.talkingrock`.
2. **`tests/test_migration_script.py`**: Test the `migrate_to_talkingrock.py` script against fixture databases:
   - Creates expected directory structure
   - All tables present in output DB
   - Row counts match source
   - Idempotency: running twice does not error
3. **`tests/test_store_path.py`**: Verify `get_cairn_store()` returns a path under `settings.data_dir`.
4. **`tests/test_schema_conflict_resolution.py`**: Verify that after `play_db.py` init, `play_schema_version` exists and `schema_version` is the migration-runner format.

### Integration tests

After code changes, run the full test suite with the existing command:
```bash
PYTHONPATH="/home/kellogg/dev/Cairn/src" "/home/kellogg/dev/Cairn/.venv/bin/python3" \
    -m pytest tests/test_*.py -x --tb=short -q --no-cov
```
Target: all 2033 tests pass.

### Manual verification (before discarding old databases)

1. Start the application with `./talkingrock`
2. Verify it opens `~/.talkingrock/talkingrock.db` (check `settings.data_dir` via a `get_diagnostics` RPC call)
3. Verify all Acts and Scenes visible in the Play overlay
4. Verify all memories accessible
5. Verify health pulse runs without errors
6. Verify email intelligence tables accessible
7. Verify keyring API keys work (if applicable)

---

## Order of Operations

The steps must be executed in this order to avoid leaving the application in a broken state:

1. Step 0.1–0.2 (audit): Confirm `conversations`/`messages` live-data status
2. Write migration script (Phase 9) and test it against fixture data
3. Run migration script on real data (`~/.reos-data/` → `~/.talkingrock/`)
4. `settings.py` change (Phase 2) — affects all downstream paths
5. `play_db.py` schema change: rename `schema_version` → `play_schema_version` (Phase 4), add v18 migration
6. `db.py` filename change (Phase 3)
7. `cairn/store.py` factory function + path update (Phase 5, Option A)
8. All RPC handler call sites (Phase 5 — system.py, health.py, play.py, mcp_tools.py)
9. `agent.py` fix (Phase 6)
10. Hardcoded `~/.reos-data` paths (Phase 6 — documents/storage.py, auth.py, recovery.py, reasoning/safety.py)
11. Keyring service name change + migration (Phase 8)
12. `app.py` error message (Phase 6)
13. `.gitignore` update (Phase 10)
14. Test suite (Phase 11)
15. Documentation (Phase 12)

---

## Rollback Strategy

Because the migration script does not delete `~/.reos-data/`, rollback is:

```bash
export REOS_DATA_DIR=~/.reos-data
# OR: revert settings.py to the old default
```

The application will then read the original database files unchanged. No data loss in either direction until `~/.reos-data/` is explicitly deleted (which should only happen after the new installation has been stable for at least one week).

---

## Definition of Done

- [ ] Step 0.1 audit completed; `conversations`/`messages` conflict resolution documented
- [ ] Migration script written and tested against fixture databases (idempotent, row-count verified)
- [ ] `settings.py` updated with `TALKINGROCK_DATA_DIR` fallback chain
- [ ] `db.py` default path uses `talkingrock.db`
- [ ] `play_db.py` uses new path; `play_schema_version` table avoids conflict with migration runner
- [ ] `cairn/store.py` has `get_cairn_store()` factory; all 9 call sites use it
- [ ] All hardcoded `~/.reos-data` strings updated to use `settings.data_dir` or `.talkingrock`
- [ ] `agent.py` lines 972–973 bug fixed (was constructing an invalid path)
- [ ] `providers/secrets.py` keyring service name updated with backward-compat migration
- [ ] All 2033 tests pass (plus new tests for migration, settings priority, schema conflict)
- [ ] `tests/test_auth.py:133` path assertion updated
- [ ] Manual verification checklist completed (app starts, Play visible, health pulse green)
- [ ] `.gitignore` updated
- [ ] Documentation updated (CLAUDE.md, the-play.md, ui-migration-typescript.md, inline docstrings)
- [ ] Old databases confirmed safe at `~/.reos-data/` (not deleted until 1-week stability confirmation)

---

## Confidence Assessment

**High confidence (well-evidenced):**
- Table inventory across all three databases is complete
- All 9 `cairn.db` call sites identified
- The `conversations`/`messages` conflict is real and the resolution path is clear
- `agent.py` lines 972–973 is a pre-existing bug unrelated to this migration
- The keyring migration requirement is real and the approach is straightforward
- The file-level copy strategy is the only viable approach under SQLCipher encryption

**Medium confidence (requires verification):**
- Whether `conversations`/`messages` in `reos.db` are truly empty (Step 0.1 must confirm)
- Whether `play_schema_version` rename will break any existing code that queries the play.db version table by name (a grep for `schema_version` in `play_db.py` shows it queries by table name at line 114, 120; the rename must be paired with a code change)
- The exact health tables created by `anti_nag.py` (the `init_health_tables()` call was not fully read; the table names listed are from partial code review)

**Assumptions requiring validation before coding:**
1. The `play_db.py` `schema_version` query at line 114 (`SELECT name FROM sqlite_master WHERE type='table' AND name='schema_version'`) checks for the play.db version table. After renaming to `play_schema_version`, this check must also be updated to `'play_schema_version'`. Verify this is the only place the version table name is hardcoded in `play_db.py`.
2. The `CryptoStorage` user data root (per-user `~/.reos-data/{username}/`) is only created when PAM authentication is active. Confirm that tests do not exercise the per-user path, and that `documents/storage.py`'s hardcoded path at lines 47/55 is consistent with the per-user path (it is not — those hardcoded paths bypass the per-user isolation entirely and are bugs regardless of migration).
