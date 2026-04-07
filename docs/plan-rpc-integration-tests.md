# Plan: RPC Round-Trip Integration Tests

## Context

Cairn has two parallel dispatch paths for JSON-RPC 2.0:

1. **`ui_rpc_server._handle_jsonrpc_request(db, req)`** — the stdio/Tauri path. A large
   hand-written if-chain (≈2,600 lines). Uses four pre-registered lookup tables
   (`_SIMPLE_HANDLERS`, `_STRING_PARAM_HANDLERS`, `_NO_DB_STRING_HANDLERS`,
   `_INT_PARAM_HANDLERS`) for common patterns, then falls through to individual `if method ==
   ...` blocks. Enforces `__session` presence on all non-exempt calls.

2. **`http_rpc._dispatch(db, body)`** — the HTTP/PWA path. A flat `_METHODS` dict of
   `(handler, needs_db)` pairs; ≈115 methods. Strips `__` keys before dispatch. Supports async
   handlers natively via `asyncio.to_thread`.

The two paths do **not** share the same dispatch table; they are maintained independently.
This is a known maintenance hazard: a method added to one path can be silently missing from
the other.

**Existing coverage** is strong but narrow:

- `test_play_rpc.py` — 11 tests exercising `ui._handle_jsonrpc_request` via an `_rpc()` helper.
  Covers Play/Acts/Scenes/KB. This is the gold-standard pattern.
- `test_blocks_rpc.py` — 553 lines calling handler functions directly (no dispatcher, no DB
  singleton). Bypasses the dispatch layer.
- `test_memory_rpc.py` — 780 lines calling handler functions directly via `play_db.init_db()`.
  Same bypass pattern.
- `test_ui_rpc_server.py` — 508 lines testing error formatting, auth structures, and
  `_SIMPLE_HANDLERS` lookup via mocks. Very little real-DB round-trip coverage.
- `test_chat_rpc.py`, `test_consciousness_rpc.py`, `test_cc_rpc.py`, etc. — also bypass the
  dispatcher, calling handler functions directly.

**The gap:** No test currently:
- Drives `_handle_jsonrpc_request` for conversation lifecycle, blocks, memory graph, or
  documents methods with a real DB.
- Validates that every method in the dispatch table resolves to a callable (registration audit).
- Confirms that the `http_rpc._METHODS` table and the `ui_rpc_server` if-chain cover the same
  method set.
- Proves the dispatcher's `__session` enforcement and error envelope logic holds end-to-end.

## Approach (Recommended)

Introduce a `_rpc()` helper into `conftest.py` (or a shared `tests/helpers.py`) that is
identical to the one in `test_play_rpc.py`. This helper becomes the single canonical tool for
round-trip tests through `ui_rpc_server._handle_jsonrpc_request`.

Write **four new test files**, one per domain cluster, plus one registry-audit file:

| File | Domain | Target dispatcher |
|------|--------|-------------------|
| `test_rpc_roundtrip_dispatch.py` | Registration audit + protocol envelope | both dispatchers |
| `test_rpc_roundtrip_conversations.py` | Conversation lifecycle + briefing | `ui_rpc_server` |
| `test_rpc_roundtrip_blocks.py` | Blocks CRUD + tree + rich text | `ui_rpc_server` |
| `test_rpc_roundtrip_memory_graph.py` | Memory relationships + search + index | `ui_rpc_server` |

The existing `test_play_rpc.py` already covers Play/Acts/Scenes/KB adequately and does not need
a parallel file.

## Alternatives Considered

### Alternative A: Extend existing per-handler files

Add round-trip tests to `test_blocks_rpc.py`, `test_memory_rpc.py`, etc. by importing
`_handle_jsonrpc_request` directly.

**Rejected** because: Those files use `play_db.init_db()` (the old connection pool), not
`isolated_db_singleton` (the new `cairn.db.Database` singleton). Mixing them in the same file
creates fixture interference. Also, the existing files test handler contracts, not the dispatch
layer — a clear separation of concern is preferable.

### Alternative B: HTTP dispatch path (`http_rpc._dispatch`) as the sole test target

`http_rpc._dispatch` is already designed for testability (the docstring says "separated so it
can be tested without a full HTTP request cycle"), is `async`, and is the path the PWA uses.

**Trade-off:** Requires `pytest-asyncio` (or `anyio`) and introduces async fixtures throughout.
The Tauri/stdio path (`_handle_jsonrpc_request`) would remain untested at the dispatcher level.
Both paths are in production, so both deserve coverage.

**Decision:** Test `ui_rpc_server` (sync) as the primary round-trip target; add a thin
`_dispatch` smoke suite in `test_rpc_roundtrip_dispatch.py` to catch divergence between the two
tables.

## Implementation Steps

### Step 1 — Extract the `_rpc()` helper into `conftest.py`

In `/home/kellogg/dev/Cairn/tests/conftest.py`, add a module-level helper function (not a
fixture — it should be importable as a plain function):

```python
def rpc(db: object, *, req_id: int = 1, method: str, params: dict | None = None) -> dict:
    """Drive _handle_jsonrpc_request with a real DB.

    Injects __session automatically.  Returns the full JSON-RPC envelope.
    """
    import cairn.ui_rpc_server as ui
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    resp = ui._handle_jsonrpc_request(db, {"jsonrpc": "2.0", "id": req_id, "method": method, "params": p})
    assert resp is not None, f"Dispatcher returned None for method={method!r}"
    return resp
```

Also add an `rpc_db` fixture that composes `isolated_db_singleton` with `tmp_path` env setup:

```python
@pytest.fixture
def rpc_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    """Isolated DB + env for RPC round-trip tests."""
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(tmp_path / "data"))
    # isolated_db_singleton already sets _db_instance; just compose with it.
    ...
```

**Note:** `test_play_rpc.py` already duplicates `_rpc()` locally. After this step, update
`test_play_rpc.py` to import from `conftest` to avoid drift. That is a one-line change.

### Step 2 — Create `test_rpc_roundtrip_dispatch.py`

**Purpose:** Registration audit and protocol envelope verification. No real I/O.

**Tests (~20):**

1. `test_all_methods_in_ui_server_resolve_to_callable` — Build a dynamic list of method names
   from `_SIMPLE_HANDLERS`, `_STRING_PARAM_HANDLERS`, `_NO_DB_STRING_HANDLERS`,
   `_INT_PARAM_HANDLERS`, plus all `if method == ...` strings by parsing the `if method ==`
   pattern in the module source (or maintaining an explicit `_ALL_METHODS` set to import).
   Assert `callable(handler_fn)` for each.

2. `test_http_rpc_methods_dict_values_are_callables` — Iterate `http_rpc._METHODS`; assert each
   value is `(callable, bool)`.

3. `test_method_sets_parity` — Compare the method set known to `ui_rpc_server` against
   `http_rpc._METHODS`. Fail if a method exists in one but not the other, **unless** it is on an
   explicit allowed-divergence list (e.g. `lifecycle/*` methods exist only in `ui_rpc_server`;
   `files/*` exists in both). Document the divergence list as a constant in the test file so
   additions are visible in diffs.

4. `test_missing_session_yields_error_32003` — Call any non-exempt method without `__session`.
   Assert `error.code == -32003`.

5. `test_exempt_methods_pass_without_session` — `ping`, `initialize`, `debug/log`.

6. `test_unknown_method_yields_error_32601`.

7. `test_notification_no_id_returns_none` — Pass `req` without `id` key; assert return is `None`.

8. `test_http_dispatch_method_not_found_yields_32601` — Call `_dispatch` with unknown method via
   `asyncio.run`.

9. `test_http_dispatch_blacklisted_method_yields_32601` — Call `auth/login` via `_dispatch`.

10. `test_tools_call_unknown_tool_yields_rpc_error` — `tools/call` with nonexistent `name`.

11–20: Parametrized missing-required-param tests for a representative sample of the four lookup
tables (e.g. `ollama/set_url` without `url`, `safety/set_sudo_limit` without
`max_escalations`).

### Step 3 — Create `test_rpc_roundtrip_conversations.py`

**Purpose:** Full round-trip through `lifecycle/conversations/*` and `lifecycle/briefing/*`
methods with real DB.

**Mocks needed:** None for basic lifecycle operations (start/messages/list are pure DB).
`lifecycle/conversations/close` triggers `CompressionManager.submit()` — mock that to avoid
background threads.

**Tests (~18):**

1. `test_get_active_returns_null_on_fresh_db`
2. `test_start_returns_conversation_with_id`
3. `test_start_twice_returns_error_with_active_conversation`
4. `test_list_returns_active_conversation`
5. `test_add_message_user_role`
6. `test_add_message_assistant_role`
7. `test_messages_returns_in_order`
8. `test_messages_limit_respected`
9. `test_pause_transitions_state`
10. `test_unpause_transitions_state`
11. `test_close_triggers_compression_submit` (mock `CompressionManager.submit`)
12. `test_compression_status_returns_dict`
13. `test_list_enhanced_empty_db_returns_empty_list`
14. `test_search_fts_empty_db_returns_empty_results`
15. `test_briefing_get_on_fresh_db_returns_none_or_stale`
16. `test_briefing_generate_manual_trigger_does_not_crash`
17. `test_close_nonexistent_conversation_returns_error`
18. `test_conversation_detail_not_found_returns_error_or_null`

### Step 4 — Create `test_rpc_roundtrip_blocks.py`

**Purpose:** Full round-trip for blocks CRUD + tree operations through the dispatcher. This
replaces the handler-direct tests in `test_blocks_rpc.py` for the subset of operations the
dispatcher exposes.

**Mocks needed:** None. Blocks are fully SQLite-backed with no external I/O.

**Tests (~22):**

Setup fixture: create an Act via `play/acts/create` (using `rpc()`), extract `act_id`.
Create a Page via `play/pages/create`, extract `page_id`.

1. `test_blocks_create_paragraph_returns_block`
2. `test_blocks_get_roundtrip` (create then get)
3. `test_blocks_get_not_found_returns_error`
4. `test_blocks_list_by_page_id`
5. `test_blocks_list_by_act_id`
6. `test_blocks_update_rich_text`
7. `test_blocks_delete_removes_block`
8. `test_blocks_delete_missing_param_returns_error`
9. `test_blocks_move_to_new_parent`
10. `test_blocks_reorder_changes_positions`
11. `test_blocks_ancestors_returns_chain`
12. `test_blocks_descendants_returns_children`
13. `test_blocks_page_tree_returns_tree`
14. `test_blocks_page_markdown_returns_string`
15. `test_blocks_import_markdown_creates_blocks`
16. `test_blocks_rich_text_get_and_set_roundtrip`
17. `test_blocks_property_get_and_set_roundtrip`
18. `test_blocks_property_delete_removes_key`
19. `test_blocks_search_returns_matches`
20. `test_blocks_unchecked_todos_returns_list`
21. `test_blocks_scene_create_and_validate`
22. `test_blocks_create_missing_type_returns_error`

### Step 5 — Create `test_rpc_roundtrip_memory_graph.py`

**Purpose:** Round-trip for `memory/*` (the hybrid vector-graph system), not to be confused with
`lifecycle/memories/*` (the conversation memory lifecycle).

**Mocks needed:**
- `MemoryRetriever` / `MemoryGraphStore` — the graph store is backed by `play_db` (SQLite), so
  no mock is needed for relationship CRUD.
- `memory/search` and `memory/index/*` invoke embedding computation. Mock the embedding
  service (return a zero vector) to keep tests fast. The `RelationshipExtractor` may call an
  LLM; mock it.
- After each test reset the module-level singletons in `cairn.rpc_handlers.memory`:
  `_graph_store = _retriever = _extractor = None`.

**Tests (~18):**

Setup fixture: Create two blocks via `blocks/create` to get real `block_id` values.

1. `test_relationships_create_returns_relationship_id`
2. `test_relationships_list_returns_created_relationship`
3. `test_relationships_list_direction_outbound`
4. `test_relationships_update_confidence`
5. `test_relationships_delete_removes_relationship`
6. `test_relationships_create_missing_source_id_returns_error`
7. `test_memory_stats_returns_counts`
8. `test_memory_related_empty_graph_returns_empty`
9. `test_memory_path_no_path_returns_empty`
10. `test_memory_index_block_with_mocked_embedder`
11. `test_memory_index_remove_after_index`
12. `test_memory_index_batch_empty_list`
13. `test_memory_search_with_mocked_retriever`
14. `test_memory_auto_link_with_mocked_extractor`
15. `test_memory_extract_relationships_with_mocked_extractor`
16. `test_memory_learn_from_feedback_does_not_crash`
17. `test_memory_related_missing_block_id_returns_error`
18. `test_memory_path_missing_start_id_returns_error`

## Files Affected

### New files to create

| Path | Purpose |
|------|---------|
| `/home/kellogg/dev/Cairn/tests/test_rpc_roundtrip_dispatch.py` | Registration audit + envelope |
| `/home/kellogg/dev/Cairn/tests/test_rpc_roundtrip_conversations.py` | Conversation lifecycle |
| `/home/kellogg/dev/Cairn/tests/test_rpc_roundtrip_blocks.py` | Blocks CRUD via dispatcher |
| `/home/kellogg/dev/Cairn/tests/test_rpc_roundtrip_memory_graph.py` | Memory graph via dispatcher |

### Files to modify

| Path | Change |
|------|--------|
| `/home/kellogg/dev/Cairn/tests/conftest.py` | Add `rpc()` helper function + `rpc_db` fixture |
| `/home/kellogg/dev/Cairn/tests/test_play_rpc.py` | Replace local `_rpc()` with import from conftest (optional, low risk) |

### Files read-only during this work

- `/home/kellogg/dev/Cairn/src/cairn/ui_rpc_server.py`
- `/home/kellogg/dev/Cairn/src/cairn/http_rpc.py`
- `/home/kellogg/dev/Cairn/src/cairn/rpc_handlers/*.py`

## Risks & Mitigations

### Risk 1: `conftest.py` helper diverges from `test_play_rpc.py` local `_rpc()`

**Description:** Two copies of nearly identical helper logic will diverge over time. If
`_handle_jsonrpc_request`'s calling convention changes, one copy gets updated and the other
doesn't.

**Mitigation:** Migrate `test_play_rpc.py` to import the shared helper as part of this work.
Add a comment in `test_play_rpc.py` pointing to `conftest.rpc`.

### Risk 2: `lifecycle/conversations/close` spawns a background compression thread

**Description:** `handle_conversations_close` calls `CompressionManager.submit(conversation_id)`,
which starts a background thread. If the thread outlives the test, it may touch the now-closed
temp DB and produce spurious errors or flakiness.

**Mitigation:** In `test_rpc_roundtrip_conversations.py`, mock `get_compression_manager()` to
return a `MagicMock`. This is the same approach used in `test_conversation_lifecycle.py`.

### Risk 3: Memory graph singletons leak between tests

**Description:** `rpc_handlers/memory.py` uses module-level `_graph_store`, `_retriever`,
`_extractor` singletons. If one test initialises them pointing at a temp DB, the next test's
`isolated_db_singleton` creates a new DB, but the singletons still point at the old one.

**Mitigation:** Add a fixture in `test_rpc_roundtrip_memory_graph.py` that resets all three
singletons to `None` in its teardown (same pattern used in `test_memory_rpc.py` lines 44–57).

### Risk 4: `play_db.close_connection()` vs `cairn.db.Database` singleton confusion

**Description:** `blocks_db` and `memory graph` read/write through `play_db` (the old SQLite
connection pool), while conversation lifecycle reads through `cairn.db.Database` (the new
singleton). Tests using `isolated_db_singleton` only replace the `cairn.db.Database` singleton,
not `play_db`. Block and memory graph tests must additionally set `TALKINGROCK_DATA_DIR` and call
`play_db.close_connection()` in teardown — exactly like `test_blocks_rpc.py` does today.

**Mitigation:** The `rpc_db` fixture in conftest must: (1) set `TALKINGROCK_DATA_DIR`, (2) call
`play_db.close_connection()` before and after, (3) yield the `cairn.db.Database` instance from
`isolated_db_singleton`. Compose the two rather than duplicate.

### Risk 5: Method-set parity test is brittle if methods are added to one path only

**Description:** `test_method_sets_parity` will fail every time a developer adds a method to
`ui_rpc_server` but forgets `http_rpc` (which is actually the desired behaviour), but it will
also require an allowed-divergence list to be maintained.

**Mitigation:** Keep the divergence list as a named constant `_KNOWN_DIVERGENCE: frozenset[str]`
at the top of `test_rpc_roundtrip_dispatch.py`. Add a comment explaining why each entry
diverges. This makes the delta visible in every PR diff.

### Risk 6: Async `_dispatch` tests require event loop management

**Description:** `http_rpc._dispatch` is an `async` function. Calling it requires
`asyncio.run()` or `pytest-asyncio`.

**Mitigation:** Use `asyncio.run()` inline (no additional dependency) for the small number of
HTTP-path smoke tests in `test_rpc_roundtrip_dispatch.py`. If the project adopts
`pytest-asyncio` in the future, those calls can be converted.

## Testing Strategy

### What these tests must verify

1. **Dispatcher routes correctly** — every registered method reaches its handler without a
   `TypeError` (missing required param caught by dispatcher) or `KeyError` (wrong dispatch
   table key).

2. **No 500s on valid minimal params** — the smoke tests pass `{"__session": "test-session"}`
   plus the minimum required params for each method. If a method returns `{"error": {...}}` with
   code `-32603`, that is a bug.

3. **State mutations are durable** — read-after-write tests (create → list, write → read)
   confirm the DB commit path is exercised, not just the in-memory handler.

4. **Error contracts are correct** — missing-param tests confirm the dispatcher returns
   `-32602`, not a Python exception.

5. **Registration completeness** — the audit test catches a method added to one dispatcher but
   not the other before it reaches production.

### What these tests explicitly do NOT test

- LLM inference quality (`chat/respond`, `cairn/chat_async`, etc.)
- Thunderbird subprocess integration
- Filesystem encryption (crypto module mocked via env isolation)
- ReOS handlers (optional import; skip if not installed)
- PAM authentication

### Test markers

Use `pytest.mark` to tag these tests. The existing `pyproject.toml` configuration excludes
`slow` tests by default; these tests are fast and should run in the default suite (no marker
needed). If any test touches the filesystem heavily, it can be marked `@pytest.mark.integration`
for optional exclusion.

### How to run after implementation

```bash
PYTHONPATH="/home/kellogg/dev/Cairn/src" \
  "/home/kellogg/dev/Cairn/.venv/bin/python3" -m pytest \
  tests/test_rpc_roundtrip_dispatch.py \
  tests/test_rpc_roundtrip_conversations.py \
  tests/test_rpc_roundtrip_blocks.py \
  tests/test_rpc_roundtrip_memory_graph.py \
  -x --tb=short -q --no-cov
```

## Estimated Test Counts

| File | Tests |
|------|-------|
| `test_rpc_roundtrip_dispatch.py` | ~20 |
| `test_rpc_roundtrip_conversations.py` | ~18 |
| `test_rpc_roundtrip_blocks.py` | ~22 |
| `test_rpc_roundtrip_memory_graph.py` | ~18 |
| **Total** | **~78** |

## Definition of Done

- [ ] `conftest.py` has `rpc()` helper and `rpc_db` fixture; no duplication with
  `test_play_rpc.py`
- [ ] `test_rpc_roundtrip_dispatch.py` exists and passes; method-parity test is green;
  divergence list is documented
- [ ] `test_rpc_roundtrip_conversations.py` exists and passes; conversation start/messages/list
  is covered with real DB
- [ ] `test_rpc_roundtrip_blocks.py` exists and passes; create/get/update/delete/search covered
- [ ] `test_rpc_roundtrip_memory_graph.py` exists and passes; relationship CRUD covered; embedding
  calls mocked
- [ ] All four files pass in the default `pytest` run (no `--slow`, no Ollama dependency)
- [ ] No test touches the real user DB (`~/.talkingrock/talkingrock.db`)
- [ ] `ruff check` and `ruff format` pass on all new files (100-char line length)

## Unknowns and Assumptions Requiring Validation

1. **`play_db` vs `cairn.db` split for blocks** — Blocks handlers take a `Database` argument but
   internally call `play_db` directly. Confirm by reading `blocks_db.create_block()` to see
   whether it uses the `db` argument or the module-level `play_db` connection. If it ignores
   `db`, then `isolated_db_singleton` is not sufficient isolation for block data — only
   `TALKINGROCK_DATA_DIR` isolation matters.

2. **`CompressionManager` singleton** — Confirm whether `get_compression_manager()` returns a
   module-level singleton that persists across tests in the same process. If yes, the mock must
   be applied with `monkeypatch.setattr` rather than a context manager, to prevent it from
   bleeding into other test files.

3. **`MemoryGraphStore` DB path** — Confirm `MemoryGraphStore()` opens `play_db` (same
   `TALKINGROCK_DATA_DIR`) or opens the `cairn.db` singleton. This determines which isolation
   mechanism is sufficient.

4. **Method set for `ui_rpc_server` audit** — The if-chain in `_handle_jsonrpc_request` does not
   have a programmatic method registry (unlike `http_rpc._METHODS`). The audit test must either
   maintain an explicit list or grep the source. Recommended: define
   `_ALL_UI_SERVER_METHODS: frozenset[str]` as a constant in `ui_rpc_server.py` (one-line change
   that also benefits documentation), or use the `http_rpc._METHODS` as the authoritative set
   and diff against a curated list of `ui_rpc_server`-only methods.
