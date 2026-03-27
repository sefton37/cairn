# Plan: Consolidate filesystem knowledge_store into SQLite

## Context

Cairn maintains two parallel knowledge systems that serve overlapping purposes:

**System 1 — filesystem KnowledgeStore** (`src/cairn/knowledge_store.py`)

- Writes JSON files to `~/.talkingrock/play/acts/{act_id}/archives/{archive_id}.json`
- Writes learned facts to `~/.talkingrock/play/acts/{act_id}/learned.json`
- Optionally encrypts files via `CryptoStorage`
- Data types: `Archive` (conversation snapshot), `LearnedEntry` (learned fact with a category), `LearnedKnowledge` (ordered collection of `LearnedEntry` objects for one act)
- `LearnedEntry` categories: fact, lesson, decision, preference, observation

**System 2 — SQLite memory system** (`src/cairn/services/memory_service.py`)

- Writes to `memories`, `memory_entities`, `memory_state_deltas` tables in `talkingrock.db`
- Full deduplication pipeline: embedding similarity filter + LLM judgment arbiter
- Signal-count reinforcement, supersession chains
- FTS5 full-text search via `memories_fts`
- Embeddings for semantic search
- User review gate (status: pending_review, approved, rejected)
- `memory_type` column added in v19 schema (types: fact, preference, priority, commitment, relationship)

**The duplication problem:**

- `LearnedEntry` categories overlap directly with `memories.memory_type`
- `get_learned_markdown()` injects KB entries into every prompt via `agent.py._get_learned_context()`; approved `memories` rows serve the same purpose
- `Archive` stores full message snapshots on disk; SQLite already has `conversations` and `messages` tables plus `archive_metadata` linking to the filesystem archive by `archive_id`
- The filesystem knowledge store has a simpler dedup model (exact case-insensitive match) versus the richer embedding+LLM dedup in `MemoryService`

**Why eliminate the filesystem store:**

- Redundant write paths create confusion about which system is authoritative
- Filesystem archives bypass WAL-mode atomicity guarantees
- Encryption is done per-file instead of at the DB layer via `db_crypto`
- The `memories` table is already richer: embeddings, signal counts, user review, FTS5
- SQLite enables cross-Act queries and JOINs with scenes/acts/conversations that are impossible with scattered JSON files

---

## Concept Mapping: filesystem to SQLite

| Filesystem concept | SQLite equivalent | Notes |
|---|---|---|
| `Archive` (messages JSON file) | `conversations` + `messages` tables | Already exist; archival via `conversation/archive/confirm` RPC already writes here |
| `archive_metadata` DB table | Already exists | Created in migration `002_archive_memory_system.sql`; stores archive_id, conversation_id, act_id, topics, sentiment |
| `LearnedEntry` | `memories` row with `memory_type` | memory_type added in v19; the 5 KS categories map to memory types |
| `LearnedKnowledge.to_markdown()` | Query memories WHERE status='approved' grouped by memory_type | Reconstruct same markdown format from DB |
| `source_archive_id` on LearnedEntry | New `source_archive_id` column on memories | Archive ID is not the same as conversation ID; see Risk 1 |
| `KnowledgeStore.add_learned_entries()` dedup | `MemoryService.store()` dedup | KS uses exact-match; MemoryService uses embedding+LLM, which is strictly better |
| `KnowledgeStore.search_archives()` | FTS5 `memories_fts` + `messages_fts` | Richer; also enables semantic search via embeddings |
| Encryption via `CryptoStorage` | `db_crypto.connect()` already encrypts talkingrock.db | Whole-DB encryption already present; per-file encryption is redundant |

### Category mapping: LearnedEntry.category to memories.memory_type

```
"fact"        -> "fact"         (exact match, already in VALID_MEMORY_TYPES)
"preference"  -> "preference"   (exact match)
"lesson"      -> "fact"         (no "lesson" type in memories; closest is "fact")
"decision"    -> "commitment"   (a decision is a commitment to a course of action)
"observation" -> "fact"         (closest general type)
```

Note: `VALID_MEMORY_TYPES` in `memory_service.py` is `{"fact", "preference", "priority", "commitment", "relationship"}`. There is no "lesson" or "observation" type. The migration must map them; alternatively, `VALID_MEMORY_TYPES` can be extended first (low-risk since `memory_type` has no CHECK constraint — it is a nullable TEXT column added by a plain ALTER TABLE in v19).

---

## Approach A — Recommended: In-place redirect with migration script

Replace `KnowledgeStore` internals to write to SQLite (via `MemoryService` and `play_db`) while keeping the public interface stable. Migrate existing filesystem data in a one-shot script. Then, after a burn-in period, delete the filesystem write paths.

**Why recommended:**

- Preserves all public call sites (`agent.py`, `rpc_handlers/context.py`, `knowledge_service.py`, `archive_service.py`) without changing signatures
- Allows incremental rollout: old files stay until migration script runs, new writes go to DB
- Reversible during burn-in by re-enabling file writes with a flag
- The public `KnowledgeStore` API becomes a thin facade, not deleted immediately

## Approach B — Hard cutover: Delete KnowledgeStore, rewrite all consumers

Remove `knowledge_store.py` entirely. Rewrite all six consumers to call `MemoryService` and `play_db` directly. Update `archive_service.py` to stop writing JSON files.

**Why not recommended:**

- Six call sites must change atomically; high risk of regression
- `ArchiveService.assess_archive_quality()` currently calls `knowledge_store.get_archive()` and `knowledge_store.load_learned()` — full rewrites required
- `archive_service.py` currently has a dual write: filesystem JSON via `KnowledgeStore.save_archive()` AND DB metadata via `_store_archive_metadata()`. Eliminating the filesystem path requires verifying that `conversations` + `messages` tables contain identical data for historical archives
- Touching `agent.py` in the hot path during the same change window is higher risk
- Harder to roll back if an issue is found in production

## Approach C — Parallel writes with feature flag

Keep all filesystem writes, add duplicate DB writes behind a `KNOWLEDGE_STORE_BACKEND=sqlite` env flag. Flip the flag once validated.

**Why not recommended:**

- Adds permanent dual-write complexity for a transitional feature
- Doubles I/O during validation window
- Technical debt of the flag and parallel paths remains until cleanup; easy to forget

---

## Implementation Steps

### Phase 1 — Extend the memories schema (prerequisite)

**Step 1.1** — Add `source_archive_id` column to `memories` table.

The current `memories` table links to a `conversation_id` but not to a knowledge store archive ID. `LearnedEntry` objects carry a `source_archive_id` to trace which archive produced each learned fact. To preserve this lineage:

Add a v20 migration in `play_db.py`:
- Increment `SCHEMA_VERSION` to 20
- Add `_migrate_v19_to_v20()` that runs `ALTER TABLE memories ADD COLUMN source_archive_id TEXT`
- Add the column to the `CREATE TABLE memories` DDL in `_init_schema()` for fresh installs

File: `src/cairn/play_db.py`

**Step 1.2** — Extend `VALID_MEMORY_TYPES` to include "lesson" and "observation".

This avoids silently collapsing the semantic distinction. Since `memory_type` was added as a plain nullable TEXT column (no CHECK constraint, as confirmed by the v19 migration code), no table rebuild is required. Simply update the frozenset.

File: `src/cairn/services/memory_service.py` — update `VALID_MEMORY_TYPES`

### Phase 2 — Add SQLite-backed methods to MemoryService

**Step 2.1** — Add `store_learned_entry()` to `MemoryService`.

New method signature:
```python
def store_learned_entry(
    self,
    conversation_id: str,
    content: str,
    category: str,
    *,
    source_archive_id: str | None = None,
    destination_act_id: str | None = None,
    deduplicate: bool = True,
) -> Memory | None:
```

This wraps `store()` but accepts the KnowledgeStore input shape. Maps `category` to `memory_type`, sets `source="turn_assessment"` (avoids a CHECK constraint table rebuild), and populates `source_archive_id`.

File: `src/cairn/services/memory_service.py`

**Step 2.2** — Add `get_learned_markdown_from_db()` to `MemoryService`.

New method signature:
```python
def get_learned_markdown_from_db(
    self,
    act_id: str | None = None,
) -> str:
```

Queries `memories` WHERE `status='approved'` AND `destination_act_id = ?` (using `YOUR_STORY_ACT_ID` when `act_id` is None), groups by `memory_type`, renders the same markdown format as `LearnedKnowledge.to_markdown()`. This is a pure read with no schema changes required.

File: `src/cairn/services/memory_service.py`

**Step 2.3** — Verify archive reconstruction path in `ArchiveService`.

Confirm that `archive_service.get_archive()` can reconstruct the full archive from `archive_metadata JOIN messages`. The method currently calls `knowledge_store.get_archive()` which reads the filesystem JSON. After Phase 3, it must read from DB.

The critical check: does `archive_metadata` carry the `conversation_id`? Yes — confirmed at line 6 of `002_archive_memory_system.sql`. Messages are accessible via `db.get_messages(conversation_id=row["conversation_id"])`.

File: `src/cairn/services/archive_service.py` — read path only at this phase

### Phase 3 — Redirect KnowledgeStore writes to SQLite

**Step 3.1** — Refactor `KnowledgeStore.add_learned_entries()` to write to MemoryService.

Keep the method signature intact. Internally:
1. For each entry, call `MemoryService.store_learned_entry()` with content, category, source_archive_id, act_id
2. Remove the `load_learned()` / `save_learned()` file I/O
3. Map `act_id=None` to `YOUR_STORY_ACT_ID` for destination routing

File: `src/cairn/knowledge_store.py`

**Step 3.2** — Refactor `KnowledgeStore.get_learned_markdown()` to read from MemoryService.

Call `MemoryService.get_learned_markdown_from_db(act_id)`.

File: `src/cairn/knowledge_store.py`

**Step 3.3** — Refactor `KnowledgeStore.save_archive()` to stop writing filesystem JSON.

`save_archive()` should:
1. Assert that the conversation_id and messages are already in DB (they are, because `ArchiveService` calls `db.get_messages()` before calling this method)
2. Return an `Archive` dataclass populated from memory without writing to disk
3. Leave `archive_metadata` write in `ArchiveService._store_archive_metadata()` unchanged

This is a partial stop: do not write the JSON file, but return the `Archive` object as if you had.

File: `src/cairn/knowledge_store.py`

**Step 3.4** — Refactor `KnowledgeStore.get_archive()` and `list_archives()` to read from DB.

`get_archive(archive_id, act_id)`:
1. Query `archive_metadata WHERE archive_id = ?` to get `conversation_id`
2. Query `messages WHERE conversation_id = ?` to get message list
3. Reconstruct and return `Archive` dataclass

`list_archives(act_id)`:
1. Query `archive_metadata WHERE act_id = ?` ordered by `created_at DESC`
2. For each row, reconstruct a lightweight `Archive` (without loading messages)

`search_archives(query, act_id, limit)`:
1. Use `messages_fts` FTS5 table with `MATCH ?` query
2. JOIN back to `archive_metadata` to filter by `act_id`

File: `src/cairn/knowledge_store.py`

**Step 3.5** — Refactor `KnowledgeStore.load_learned()` to read from DB.

Reconstruct `LearnedKnowledge` from `memories` rows WHERE `destination_act_id = ?` AND `status = 'approved'`. Map `memory_type` back to `LearnedEntry.category`.

File: `src/cairn/knowledge_store.py`

**Step 3.6** — Refactor `KnowledgeStore.save_learned()` to a no-op.

Per-entry saves happen in `add_learned_entries()` via MemoryService. `save_learned(kb)` as a bulk-write operation is no longer needed. Make it a no-op with a deprecation log message.

File: `src/cairn/knowledge_store.py`

**Step 3.7** — Refactor `KnowledgeStore.clear_learned()` to use DB.

Execute `DELETE FROM memories WHERE destination_act_id = ? AND source = 'turn_assessment'`. (Or a wider delete if you want to clear all memories for an act — be conservative here.)

File: `src/cairn/knowledge_store.py`

### Phase 4 — Data migration script

**Step 4.1** — Write `src/cairn/migrations/migrate_knowledge_store.py`.

This one-shot script:
1. Reads all existing `learned.json` files (play-level and per-act) from `~/.talkingrock/play/`
2. For each `LearnedEntry`, calls `MemoryService.store_learned_entry()` to insert into `memories`
3. Uses `deduplicate=False` to skip LLM dedup during migration (avoid slow Ollama calls for bulk import)
4. Reads all `archives/*.json` files
5. For each `Archive`, checks if `archive_metadata` row already exists by `archive_id`; if not, inserts one pointing to a synthetic conversation record
6. Renames migrated `learned.json` files to `learned.json.migrated` (not deletion — keeps backup)
7. Reports: N learned entries migrated, M archives linked

The script must be idempotent (check before insert) and safe to run multiple times.

### Phase 5 — Update hot-path consumers to bypass KnowledgeStore

**Step 5.1** — Update `agent.py._get_learned_context()`.

Replace the `KnowledgeStore` import and `store.get_learned_markdown()` call with a direct `MemoryService.get_learned_markdown_from_db(active_act_id)` call. This removes the last import of `KnowledgeStore` from the hot path.

File: `src/cairn/agent.py` (lines 1198–1223)

**Step 5.2** — Update `rpc_handlers/context.py`.

Replace the `KnowledgeStore` import (line 15) and the `store.get_learned_markdown(active_act_id)` call (lines 49–51) with `MemoryService`.

File: `src/cairn/rpc_handlers/context.py`

**Step 5.3** — `services/knowledge_service.py` is deferred.

`KnowledgeService` is a thin wrapper over `KnowledgeStore`. After Phase 3, it continues to work unchanged because the `KnowledgeStore` interface is preserved as a facade. Collapsing `KnowledgeService` into direct `MemoryService` calls is a follow-up clean-up, not part of this plan.

### Phase 6 — Deprecate and archive filesystem paths (deferred, post burn-in)

Only after Phase 4 migration has run and a burn-in period of at least one week passes without regressions:

- Remove `_write_json`, `_read_json`, `_archives_dir`, `_learned_path`, `_ensure_dirs` private methods from `KnowledgeStore`
- Remove the `_get_crypto()` call (db_crypto already handles encryption)
- Delete `src/cairn/knowledge_store.py` once all consumers use MemoryService directly (separate PR)

---

## Files Affected

### New files

| File | Purpose |
|---|---|
| `src/cairn/migrations/migrate_knowledge_store.py` | One-shot migration script (Phase 4) |

### Modified files

| File | Change |
|---|---|
| `src/cairn/play_db.py` | v20 migration: add `source_archive_id` to memories; update DDL |
| `src/cairn/services/memory_service.py` | Add `store_learned_entry()`, `get_learned_markdown_from_db()`, extend `VALID_MEMORY_TYPES` |
| `src/cairn/knowledge_store.py` | Replace file I/O with MemoryService calls (facade pattern) |
| `src/cairn/services/archive_service.py` | Redirect `save_archive()` result construction to use DB; reconstruct Archive from archive_metadata and messages |
| `src/cairn/agent.py` | Replace `_get_learned_context()` to use MemoryService directly |
| `src/cairn/rpc_handlers/context.py` | Replace KnowledgeStore import with MemoryService |

### Files to delete (Phase 6 only, after burn-in)

| File | Condition |
|---|---|
| `src/cairn/knowledge_store.py` | After all consumers migrated to MemoryService directly |

### Files not affected

- `src/cairn/services/knowledge_service.py` — still works via KnowledgeStore facade in Phases 3–5
- `src/cairn/rpc_handlers/archive.py` — uses ArchiveService which is modified internally
- `src/cairn/ui_rpc_server.py` — no changes; RPC method names stay the same
- `tests/test_knowledge_store.py` — tests must be rewritten (see Testing Strategy)

---

## Risks and Mitigations

### Risk 1 — Archive message retrieval gap

**Problem:** `ArchiveService.assess_archive_quality()` calls `knowledge_store.get_archive(archive_id, act_id)` and reads `archive.messages`. After the redirect, `get_archive()` must reconstruct messages from the `messages` table. But `archive_metadata` stores `conversation_id`, and messages can be deleted if someone calls `delete_conversation(archive_first=False)`.

**Mitigation:** Keep the filesystem JSON write in `save_archive()` as a fallback for the `assess_archive_quality()` path until a `messages_snapshot` column is added to `archive_metadata`. This is a Phase 3 partial: stop writing `learned.json` immediately, but keep writing archive JSON files until the snapshot column is added. Document this as a known intermediate state.

### Risk 2 — source CHECK constraint on memories table

**Problem:** If a new `"learned_kb"` source value is desired for provenance tracking, it would require rebuilding the `memories` table to expand the CHECK constraint (same pattern as v14 and v16 migrations).

**Mitigation:** Map KS-imported entries to the existing `"turn_assessment"` source value, which is semantically close. The `memory_type` column already distinguishes the knowledge type, so a separate source value is not strictly necessary for query purposes. This avoids the table rebuild entirely.

### Risk 3 — Loss of act-scoped learned.json isolation

**Problem:** `LearnedKnowledge` is scoped by `act_id` (including `None` for play-level). The `memories` table uses `destination_act_id` for routing, which can be NULL for cross-cutting memories. Play-level learned entries (act_id=None) must map consistently.

**Mitigation:** In `store_learned_entry()`, map `act_id=None` to `destination_act_id=YOUR_STORY_ACT_ID` (the permanent cross-cutting act). Update `get_learned_markdown_from_db()` to use `YOUR_STORY_ACT_ID` when `act_id=None`. This is the same convention already used by `MemoryService._route_to_act()`.

### Risk 4 — Deduplication behavior change

**Problem:** The current KnowledgeStore deduplication is exact case-insensitive string match. MemoryService uses embedding similarity and LLM judgment. This is strictly better, but it produces different results. Existing tests that assert exact dedup behavior will fail.

**Mitigation:** The change in dedup behavior is intentional and desirable. Tests that assert specific dedup behavior must be rewritten. Document the behavior change clearly in the commit message and in this plan.

### Risk 5 — Encryption parity

**Problem:** `KnowledgeStore` uses `CryptoStorage` (AES-256-GCM per-file encryption). `talkingrock.db` uses `db_crypto`. If they are derived from different key sources, migrated data may not be protected equivalently.

**Mitigation:** Before implementing, verify that `db_crypto` is active whenever `CryptoStorage` would be active. Both should derive from the same auth session. This assumption must be confirmed by reading `db_crypto.py` and the auth boot sequence before Phase 3 begins.

### Risk 6 — Existing tests rely on filesystem behavior

**Problem:** `tests/test_knowledge_store.py` uses `tempfile.TemporaryDirectory` and tests file existence via `path.exists()`. After the redirect, these tests will fail.

**Mitigation:** Rewrite `test_knowledge_store.py` to test behavioral correctness (input/output contract) without asserting filesystem state. The new tests should use an in-memory SQLite database via the `TALKINGROCK_DATA_DIR` env var override that the existing test suite already uses.

---

## Testing Strategy

### Unit tests to rewrite

`tests/test_knowledge_store.py` — all 47 tests must be rewritten. Drop tests that assert filesystem paths. Keep all behavioral tests (add entry, retrieve, dedup, markdown output). Target the same public API, now backed by SQLite.

### Unit tests to add

`tests/test_memory_service.py` — add tests for `store_learned_entry()` and `get_learned_markdown_from_db()`.

`tests/test_archive_service.py` — add tests for `get_archive()` reconstructing from DB instead of filesystem.

### Integration tests to add

A round-trip test: call `KnowledgeStore.add_learned_entries()` then `KnowledgeStore.get_learned_markdown()` and assert the markdown contains the added entry. This proves the facade works end-to-end through SQLite without asserting file system state.

A migration test: write known `learned.json` files to a temp directory, run the migration script, assert entries appear in the `memories` table with correct `memory_type` values.

### Regression tests to preserve

`tests/test_services.py::TestKnowledgeService` — must pass unchanged (tests the public KnowledgeService interface, which remains stable because KnowledgeService delegates to KnowledgeStore facade).

`tests/test_archive_service.py` — most tests pass; only the `assess_archive_quality` path changes.

### Manual verification checklist

- After migration script runs: count entries in `memories` table vs entries in all `learned.json` files
- Run `archive/list` RPC and verify archives are returned
- Send a message to the agent and confirm learned knowledge appears in context (confirm `_get_learned_context()` returns non-empty for a user with existing learned entries)
- Check that `handle_context_stats` returns a non-zero `learned_kb` token count

---

## Definition of Done

- [ ] Schema v20 migration adds `source_archive_id` to `memories`; runs cleanly on existing DBs
- [ ] `VALID_MEMORY_TYPES` includes "lesson" and "observation" (or mapping to existing types is documented and tested)
- [ ] `MemoryService.store_learned_entry()` accepts category, content, and source_archive_id; stores to DB; deduplicates via embedding + LLM
- [ ] `MemoryService.get_learned_markdown_from_db(act_id)` produces output in the same markdown format as `LearnedKnowledge.to_markdown()`
- [ ] `KnowledgeStore.add_learned_entries()` routes to MemoryService; `learned.json` files are no longer written for new entries
- [ ] `KnowledgeStore.get_learned_markdown()` reads from MemoryService; returns correct results
- [ ] `KnowledgeStore.save_archive()` writes no filesystem JSON; messages are in the `messages` table and `archive_metadata` is populated (Risk 1 mitigation confirmed or deferred with documented plan)
- [ ] `agent.py._get_learned_context()` works correctly; learned knowledge appears in chat context
- [ ] `rpc_handlers/context.py.handle_context_stats()` includes correct learned KB token count
- [ ] Migration script (`migrate_knowledge_store.py`) runs successfully on production data; idempotent
- [ ] All 2232 existing tests pass (zero regressions)
- [ ] `tests/test_knowledge_store.py` fully rewritten and passing (no filesystem assertions)
- [ ] New tests for `MemoryService.store_learned_entry()` and `get_learned_markdown_from_db()` pass
- [ ] Burn-in period of at least 3 days before deleting filesystem code paths (Phase 6)

---

## Confidence Assessment

**High confidence (evidence-based):**

- The `memories` table can store everything `LearnedEntry` stores. The schema already has `memory_type` (v19), `destination_act_id`, `source`, and `narrative`.
- `archive_metadata` already partially replaces the filesystem archive; `conversation_id` links to messages in DB.
- The facade pattern (keep KnowledgeStore public API, redirect internals) isolates risk and allows incremental rollout.

**Medium confidence:**

- The message reconstruction path for `get_archive()` (Risk 1). Needs verification that no delete-conversation path drops messages that were the source of a filesystem archive. This requires confirming whether the frontend ever calls delete without archiving first.
- The encryption parity assumption (Risk 5). Needs confirmation that `db_crypto` is always active when `CryptoStorage` was active.

**Lower confidence:**

- The performance of `get_learned_markdown_from_db()` at query time versus reading a pre-built JSON file. For a user with many memories, the query should be fast due to the `idx_memories_destination` index, but this has not been benchmarked.

---

## Unknowns Requiring Validation Before Implementation

1. **Does the frontend ever delete a conversation without archiving first?** Check all callers of `conversation/delete` and the `ArchiveService.delete_conversation(archive_first=False)` path to confirm message loss is not a production risk.

2. **Is `db_crypto` always active when `CryptoStorage` is active?** Both systems are activated by the same auth session, but this should be confirmed by reading `db_crypto.py` and the auth boot sequence before Phase 3.

3. **What is the volume of existing `learned.json` entries on production?** If there are thousands of entries, the LLM-based dedup in `MemoryService.store()` will make the migration slow (each entry calls Ollama). The migration script should use `deduplicate=False` or direct INSERT to bypass LLM dedup during the one-shot migration.

4. **Are there any KnowledgeStore callers outside the six identified files?** The reconnaissance found exactly these files: `agent.py`, `services/context_service.py`, `rpc_handlers/context.py`, `knowledge_store.py`, `services/archive_service.py`, `services/knowledge_service.py`. This should be re-verified at implementation time by running a fresh grep across `src/` and `tests/`.
