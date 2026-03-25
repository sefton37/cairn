# Plan: Copper Agent View in Cairn Tauri Desktop

## Context

Copper is a standalone FastAPI proxy on port 11400 that routes Ollama requests across LAN
nodes. It lives at `/home/kellogg/dev/Copper/`. It has a node registry (SQLite at
`~/.copper/copper.db`), periodic health monitoring via `/api/tags`, load-balanced proxying,
a model pull endpoint, and a request log table. It has no tests. Two known bugs exist:
active request tracking is never wired (`Router.track_request()` exists but `proxy.py`
never calls it), and the health loop swallows all exceptions silently (`except Exception:
pass`).

The Cairn Tauri desktop already has four agent views: `play`, `cairn`, `reos`, `riva`. The
view router lives in `main.ts`, `AgentId` is typed in `agentBar.ts`, and each view follows
the pattern established by `reosView.ts`: a factory function returning
`{ container, startPolling, stopPolling }`.

The RIVA integration (`rpc_handlers/riva.py`) is the established proxy pattern: Cairn's
Python kernel forwards `riva/*` calls to a separate process. Copper is HTTP rather than
Unix socket, so the implementation is simpler — plain `httpx.Client` calls rather than
length-prefixed framing.

### Modularity Requirement

The overarching design directive is: **no agent should be able to block another.** Copper
is a fully independent service with its own event loop, database, and health monitoring.
The Cairn RPC handler must be a thin, fast HTTP proxy — it must never do anything
computationally expensive or blocking. Every RPC call completes in under 5 seconds.
Long-running operations (pull) use the task pattern: start → return task ID → poll for
progress. The frontend drives all management; nothing requires the CLI except
`copper serve`.

---

## Desired End State

User clicks "Copper" in the agent bar and sees a dashboard with:
1. Node grid — health status, latency, alive/dead indicator per device
2. Per-node resource data — available models, active request count
3. Models table — which models are available and which nodes carry each
4. Model pull — button to start a pull, progress card with live polling, completion
   notification
5. Node management — Add Node dialog, Remove button with confirmation, Enable/Disable
   toggle, Priority adjustment
6. Routing config — per-node enable/disable and priority (Phase 2 scope, fully supported
   by the PATCH endpoint)

---

## Approach (Recommended): Option A — Cairn RPC Proxy to Copper HTTP

The frontend calls `kernelRequest('copper/status', {})`. Cairn's Python kernel makes an
`httpx.Client` call to `localhost:11400` and returns the result. This is the same pattern
used by RIVA (socket proxy) and is consistent with all existing agent views — the frontend
never speaks directly to a backend service other than the Cairn kernel.

### Why this wins over Option B (direct fetch from TypeScript)

- **Consistency**: Every existing agent view is kernel-mediated. Diverging creates two data
  flow architectures in one app.
- **Auth propagation**: The RPC layer validates `__session` before forwarding. A direct
  `fetch()` call would bypass this entirely.
- **CORS**: Copper's FastAPI app has no CORS middleware. Option B would require adding it,
  touching Copper's production config for a UI concern.
- **Error normalisation**: The kernel translates errors into structured JSON-RPC error
  objects. Direct fetch would require duplicating that in TypeScript.

### Trade-off

There is one extra network hop (frontend → kernel stdio → httpx → Copper HTTP). In
practice this is negligible: the kernel and Copper both run locally. The round-trip cost
is dominated by Copper's own health cache, not the proxy hop.

---

## Alternatives Considered

### Option B: Frontend calls Copper HTTP directly

`copperView.ts` uses `fetch('http://localhost:11400/api/status')`. Simpler TypeScript,
removes the proxy hop. Set aside because: (1) violates the kernel-mediated pattern,
(2) requires CORS changes in Copper, (3) bypasses session validation, (4) duplicates
error handling logic in the frontend.

### Option C: Embed Copper into Cairn's process

Import `copper` as a library and run it inside the Cairn Python process. Eliminated
immediately: Copper is a FastAPI app with its own lifespan and background tasks. Embedding
it would require async-in-sync gymnastics or a thread, and would permanently couple two
codebases that have independent deployment lifecycles.

---

## Bugs to Fix in Copper First

These should be resolved before the view is wired up, because they affect correctness of
what the dashboard will display.

### Bug 1: Active request tracking never wired

**Location:** `proxy.py`, `proxy_request()` function
**Problem:** `Router.track_request()` is an async context manager that adds/removes
`ActiveRequest` entries from `router._active`. It is never called. The `active_requests`
count shown in `/api/status` is always zero. The load-balancing sort key
`(self._active_count(n.name), n.priority)` therefore degenerates to priority-only.
**Fix:** Two parts:
1. Add `@asynccontextmanager` decorator to `Router.track_request()` in `router.py`
   (the `yield` is present but the decorator is missing).
2. Wrap the proxy body in `proxy_request()` with
   `async with router.track_request(node, model):`. The streaming path requires special
   care — see Risk 2 below.

### Bug 2: Silent health loop failures

**Location:** `proxy.py`, `_health_loop()`
**Problem:** `except Exception: pass` swallows all errors silently. If `load_nodes` or
`check_all_nodes` fails, the router's health map goes stale with no indication.
**Fix:** Replace with `except Exception as exc: logger.warning("Health loop error: %s", exc)`.

---

## New Copper Endpoints Needed

The existing `/api/status` endpoint returns node health and active request counts — this
covers the node grid. The following are additionally needed:

### `GET /api/nodes` — Node registry (not just health)

Returns the full node list from the SQLite registry (all nodes, including disabled ones),
not just the in-memory health cache. Needed so the user can see and manage nodes that are
currently offline.

Response shape:
```json
{
  "nodes": [
    { "name": "tatooine", "host": "...", "port": 11434, "enabled": true, "priority": 0 }
  ]
}
```

### `POST /api/nodes` — Add a node

Body: `{ "name": str, "host": str, "port": int, "priority": int }`

### `DELETE /api/nodes/{name}` — Remove a node

### `PATCH /api/nodes/{name}` — Update enabled/priority

Body: `{ "enabled": bool, "priority": int }`

**Note:** Full routing rules (model-to-node affinity, preference weights) are Phase 2
scope. The PATCH endpoint covering `enabled` and `priority` handles the most common
configuration need without schema changes.

### `DELETE /api/models/{name}` — Delete a model from a node (optional)

Query param: `?node=<node_name>` to target a specific node. If omitted, delete from all
nodes that carry it. This is a Phase 2 capability; include it if it does not add
complexity to Phase 1 node endpoints, otherwise defer.

### `POST /api/pull` — Start a background pull task (returns immediately)

**This endpoint no longer blocks.** The pull is enqueued as a background task.

Request body: `{ "model": str, "node": str | null }`

Response: `{ "task_id": "<uuid>" }` — returned immediately, typically within milliseconds.

### `GET /api/tasks/{task_id}` — Poll a task for progress

Response shape:
```json
{
  "task_id": "abc123",
  "status": "running | completed | failed",
  "progress": {
    "node": "tatooine",
    "model": "llama3.2",
    "bytes_pulled": 1234567,
    "total_bytes": 4000000000
  },
  "result": {
    "tatooine": { "status": "ok" }
  },
  "error": null
}
```

`progress` is populated while `status = "running"`. `result` is populated when
`status = "completed"`. `error` is populated when `status = "failed"`.

### `GET /api/tasks` — List active and recently completed tasks

Response: `{ "tasks": [ { "task_id": ..., "status": ..., "created_at": ... }, ... ] }`

Useful for the frontend to resume displaying progress if the user navigates away and
returns while a pull is in flight.

---

## Implementation Steps

### Phase 1 — Copper Bug Fixes

**Files:** `Copper/src/copper/router.py`, `Copper/src/copper/proxy.py`

1.1. Add `from contextlib import asynccontextmanager` to `router.py`. Decorate
`Router.track_request()` with `@asynccontextmanager`.

1.2. In `proxy_request()`, wrap the proxy logic with
`async with router.track_request(node, model):`. The streaming path needs the context
manager to exit only after the generator is exhausted — use a `try/finally` inside the
`stream_response()` generator to call the context manager's `__aexit__`. See Risk 2 for
details.

1.3. In `_health_loop()`, replace `except Exception: pass` with
`except Exception as exc: logger.warning("Health loop error: %s", exc)`.

1.4. Manual verification: confirm `/api/status` returns non-zero `active_requests` during
a live inference call.

### Phase 2 — New Copper Management Endpoints

**File:** `Copper/src/copper/proxy.py`

2.1. Add `GET /api/nodes` — call `load_nodes(_db)`, return serialised list.

2.2. Add `POST /api/nodes` — parse body with Pydantic, call `add_node(_db, node)`,
trigger immediate health check for the new node, call `router.update_health()`.

2.3. Add `DELETE /api/nodes/{name}` — call `remove_node(_db, name)`, remove from
`router._health`.

2.4. Add `PATCH /api/nodes/{name}` — update `enabled` and/or `priority` columns, trigger
re-check if newly enabled.

2.5. **Rewrite `POST /api/pull` as a background task dispatcher:**
- Generate a UUID task ID.
- Store an in-memory `TaskRecord` in a module-level `dict[str, TaskRecord]` with
  `status="running"` and `progress={}`.
- Enqueue `asyncio.create_task(_run_pull(task_id, model, target_node))` — the actual
  pull logic (iterating alive nodes, calling Ollama `/api/pull`) runs in the background.
- Return `{ "task_id": task_id }` immediately.

2.6. Add `GET /api/tasks/{task_id}` — look up `TaskRecord` by ID, return serialised
status/progress/result/error. Return HTTP 404 if ID not found.

2.7. Add `GET /api/tasks` — return all entries in the task dict, ordered by `created_at`
descending. Limit to the most recent 50 entries to bound memory usage.

2.8. (Phase 2 / optional) Add `DELETE /api/models/{name}` with `?node=` query param.

### Phase 3 — Cairn RPC Handler

**New file:** `Cairn/src/cairn/rpc_handlers/copper.py`

3.1. The module makes synchronous `httpx.Client` calls to Copper's HTTP API.
Use `httpx.Client` (not `AsyncClient`) — the RPC server stdio loop is synchronous.
Document this constraint in a module-level comment.

3.2. Read `COPPER_URL` from the environment. Fall back to `http://localhost:11400` only
if the variable is unset. Do not hardcode the URL anywhere else in the module.

```python
import os
_COPPER_BASE_URL = os.environ.get("COPPER_URL", "http://localhost:11400")
```

3.3. Implement a single dispatcher function `handle_copper_proxy(method, params)` that
maps `copper/*` method names to Copper endpoints. **All calls have a maximum 5-second
timeout.** The `copper/pull` method now starts a background task and returns immediately,
so 5 seconds is ample.

| RPC method | Copper endpoint | HTTP verb | Timeout |
|---|---|---|---|
| `copper/status` | `/api/status` | GET | 5s |
| `copper/nodes` | `/api/nodes` | GET | 5s |
| `copper/models` | `/api/tags` | GET | 5s |
| `copper/nodes/add` | `/api/nodes` | POST | 5s |
| `copper/nodes/remove` | `/api/nodes/{name}` | DELETE | 5s |
| `copper/nodes/update` | `/api/nodes/{name}` | PATCH | 5s |
| `copper/pull` | `/api/pull` | POST | 5s |
| `copper/tasks` | `/api/tasks` | GET | 5s |
| `copper/tasks/{task_id}` | `/api/tasks/{task_id}` | GET | 5s |

3.4. On `ConnectionRefusedError`, `httpx.ConnectError`, or `httpx.TimeoutException`:
return `{ "copper_available": False, "error": "<message>" }` rather than raising. The
frontend uses `copper_available` to decide whether to show the "not running" state.

3.5. On an unknown `copper/` sub-method: return a structured error dict rather than
raising an uncaught exception.

### Phase 4 — Wire into ui_rpc_server.py

**File:** `Cairn/src/cairn/ui_rpc_server.py`

4.1. Add import near the RIVA import (line 556):
```python
from .rpc_handlers.copper import handle_copper_proxy as _handle_copper_proxy
```

4.2. Add dispatch block after the RIVA block (after line 2996):
```python
# --- Copper LAN Ollama coordinator ---
if method is not None and method.startswith("copper/"):
    copper_params = {k: v for k, v in (params or {}).items() if k != "__session"}
    return _jsonrpc_result(
        req_id=req_id,
        result=_handle_copper_proxy(method=method, params=copper_params),
    )
```

This mirrors the RIVA dispatch exactly. The handler needs no `db` argument because it
never touches Cairn's database.

### Phase 5 — Frontend: copperView.ts

**New file:** `Cairn/apps/cairn-tauri/src/copperView.ts`

5.1. Factory signature:
```typescript
export function createCopperView(callbacks: CopperViewCallbacks): {
  container: HTMLElement;
  startPolling: () => void;
  stopPolling: () => void;
}
```
where `CopperViewCallbacks = { kernelRequest: (method: string, params: unknown) => Promise<unknown> }`.

5.2. **Helper functions:** Copy `makePanel`, `makeStatRow`, and `makeBar` from
`reosView.ts` verbatim into `copperView.ts`. Do not extract them to a shared module and
do not modify `reosView.ts`. The duplication is intentional — these views evolve
independently and a shared module would couple them.

5.3. Layout: single scrollable column (no split-screen — no terminal pane needed).
Sections, each using the duplicated helper functions:

- **Header bar**: "Copper" title, connection status badge (green = running, red = not
  running), last-updated timestamp
- **Nodes panel**: one card per node — name, host:port, alive dot (green/red), latency,
  model count, active request count, enable/disable toggle, remove button with
  confirmation, priority input
- **Add Node button**: opens an inline dialog (name, host, port, priority fields) with
  Submit/Cancel
- **Models panel**: table of models vs nodes (checkmark matrix — which nodes have each
  model), with a "Pull to..." dropdown action per row
- **Active pulls panel** (conditional): shown only while one or more pull tasks are
  in flight; one progress card per task, polling every 2-3 seconds, dismissed on
  completion or failure with a notification

5.4. Status polling: call `copper/status` every 10 seconds. Call `copper/models` on
initial load and after each pull task completes. When `copper_available` is false, reduce
poll interval to 30 seconds and show the "not running" state.

5.5. Pull action flow:
1. User selects a model and optionally a target node, clicks "Pull Model".
2. Frontend calls `copper/pull` with `{ model, node }`.
3. Response: `{ "task_id": "..." }`.
4. Frontend adds a progress card for that task ID and begins polling
   `copper/tasks/{task_id}` every 2-3 seconds.
5. On `status = "completed"`: dismiss progress card, show success notification,
   re-fetch model list.
6. On `status = "failed"`: dismiss progress card, show error notification.
7. Multiple simultaneous pulls are supported — each has its own progress card.

5.6. Node enable/disable toggle: call `copper/nodes/update` with the current node's
name and the flipped `enabled` value. Re-fetch status on completion.

5.7. Node removal: clicking Remove shows an inline confirmation ("Remove tatooine?
This cannot be undone."). On confirm, call `copper/nodes/remove`. Re-fetch nodes on
completion.

5.8. Add node: on Submit, call `copper/nodes/add`. Re-fetch status on completion (which
will trigger a health check of the new node in Copper).

### Phase 6 — Agent Bar and View Router

**File:** `Cairn/apps/cairn-tauri/src/agentBar.ts`

6.1. Change the `AgentId` type:
```typescript
export type AgentId = 'play' | 'cairn' | 'reos' | 'riva' | 'copper';
```

6.2. Add to `CORE_AGENTS` array after `riva`:
```typescript
{ id: 'copper', label: 'Copper', icon: '\u{1F310}', description: 'LAN Ollama coordinator' }
```

**File:** `Cairn/apps/cairn-tauri/src/main.ts`

6.3. Add import:
```typescript
import { createCopperView } from './copperView';
```

6.4. Instantiate after the other views:
```typescript
const copperView = createCopperView({ kernelRequest });
```

6.5. Append `copperView.container` to the view container div (hidden by default, consistent
with how `reosView.container` and `rivaView.container` are appended).

6.6. In `switchView()`:
- Add `'copper'` case: hide all other views, show `copperView.container`, call
  `copperView.startPolling()`
- In all non-copper cases, add `copperView.stopPolling()` alongside the existing
  stop calls

### Phase 7 — Tests

**New files in `Copper/tests/`:**

7.1. `test_router.py` (pytest-asyncio):
- `track_request` increments active count, decrements on clean exit, decrements on
  exception inside the context
- `select_node` returns the node with fewest active requests; ties broken by priority;
  returns `None` when no healthy node has the requested model

7.2. `test_health.py` (pytest-asyncio + pytest-httpx):
- Alive node: correct `latency_ms`, `models` list populated, `alive=True`
- Timeout: `alive=False`, `error` string set
- HTTP 500: `alive=False`, `error` string set

7.3. `test_proxy.py` (pytest-asyncio + pytest-httpx):
- `GET /api/status` returns router health snapshot
- `GET /api/nodes` returns SQLite registry contents
- `POST /api/nodes` inserts node and triggers health check
- `DELETE /api/nodes/{name}` removes node
- `PATCH /api/nodes/{name}` updates enabled/priority
- `POST /api/pull` returns a task ID immediately (does not block)
- `GET /api/tasks/{task_id}` reflects `running` while pull in progress, `completed`
  after finish
- `GET /api/tasks` lists the task
- Active request count is nonzero during an in-flight proxied streaming call

**New file in `Cairn/tests/`:**

7.4. `test_rpc_copper.py` (pytest, monkeypatching httpx.Client):
- Each `copper/*` method maps to the correct HTTP verb and endpoint path
- All calls use a 5-second timeout (including `copper/pull`)
- `copper/pull` passes `{ model, node }` body and returns the task ID dict
- `copper/tasks/{task_id}` maps to `GET /api/tasks/{task_id}`
- `ConnectionRefusedError` returns `{ "copper_available": False }` without raising
- Unknown `copper/` method returns a structured error, not an exception

---

## Files Affected

### New files

| File | Purpose |
|------|---------|
| `Cairn/src/cairn/rpc_handlers/copper.py` | Cairn RPC proxy to Copper HTTP |
| `Cairn/apps/cairn-tauri/src/copperView.ts` | Frontend dashboard view |
| `Cairn/tests/test_rpc_copper.py` | RPC handler tests |
| `Copper/tests/test_router.py` | Router unit tests |
| `Copper/tests/test_health.py` | Health check unit tests |
| `Copper/tests/test_proxy.py` | FastAPI endpoint tests |

### Modified files

| File | Change |
|------|--------|
| `Copper/src/copper/router.py` | Add `@asynccontextmanager` to `track_request()` |
| `Copper/src/copper/proxy.py` | Wire `track_request`; fix health loop logging; add `/api/nodes` CRUD; rewrite `/api/pull` as background task; add `/api/tasks` and `/api/tasks/{task_id}` |
| `Cairn/src/cairn/ui_rpc_server.py` | Import copper handler, add `copper/*` dispatch block |
| `Cairn/apps/cairn-tauri/src/agentBar.ts` | Add `'copper'` to `AgentId`, add entry to `CORE_AGENTS` |
| `Cairn/apps/cairn-tauri/src/main.ts` | Import `createCopperView`, instantiate, wire into `switchView()` |

---

## Risks & Mitigations

### Risk 1: Copper not running when user navigates to the view

The most common scenario during development and first-use.

**Mitigation:** The RPC handler returns `{ "copper_available": False }` on
`ConnectionRefusedError` or timeout. `copperView.ts` renders a "Copper is not running"
state with a command hint (`copper serve`). `startPolling()` continues at a reduced
interval (30s) so the view recovers automatically when Copper starts.

### Risk 2: Active-request context manager and streaming

The streaming path in `proxy_request()` returns a `StreamingResponse` whose body is
consumed asynchronously after the function returns. A naive wrapping of the function body
with `async with router.track_request(...)` will decrement the active count before
streaming completes — the context manager exits when the function returns, not when the
stream is exhausted.

**Mitigation:** The context manager must be exited inside the `stream_response()` async
generator, after `aiter_bytes()` is exhausted. The correct pattern:

```python
async def stream_response():
    req_ctx = router.track_request(node, model)
    await req_ctx.__aenter__()
    try:
        async with _client.stream("POST", target_url, json=body) as resp:
            async for chunk in resp.aiter_bytes():
                yield chunk
    finally:
        await req_ctx.__aexit__(None, None, None)
    duration = int((time.monotonic() - start) * 1000)
    _log_request(model, node.name, duration, "ok")
```

A test asserting `_active_count()` is nonzero during an in-flight stream is required
before shipping.

### Risk 3: ui_rpc_server.py is synchronous

`ui_rpc_server.py` is a synchronous stdio loop. The Copper proxy must use
`httpx.Client` (synchronous), not `httpx.AsyncClient`. This is the same constraint that
governs the RIVA proxy (which uses blocking sockets). The `copper.py` handler must not
use `asyncio.run()` or any async primitives.

**Mitigation:** Document the constraint in `copper.py`. Use `httpx.Client` exclusively.
All calls have a 5-second timeout. The pull endpoint now returns a task ID immediately,
so there is no long-blocking RPC call anywhere in the path.

### Risk 4: Stale tasks accumulating in memory

The background task dict in Copper's process grows unboundedly if tasks are never
cleaned up. A Copper service that runs for weeks and accumulates thousands of pull
attempts (including failed ones) will grow its in-memory task dict without bound.

**Mitigation:** The `GET /api/tasks` response is limited to the 50 most recent tasks
(by `created_at` desc). A background cleanup can trim entries older than 1 hour.
Alternatively, store completed tasks in the `request_log` SQLite table and expire
them from memory on completion — this also preserves history across restarts. The
implementer should choose one strategy and apply it consistently.

### Risk 5: Node registry vs health cache drift

`/api/nodes` reads SQLite; `/api/status` reads in-memory `router._health`. A node can be
registered but not yet health-checked. The dashboard could show a node as "unknown."

**Mitigation:** After `POST /api/nodes`, trigger an immediate targeted health check and
update `router._health`. The frontend should tolerate `health = null` for unchecked nodes
and display "checking..." rather than a stale or missing state.

### Risk 6: main.ts size and complexity

`main.ts` is already 55KB. Adding a fifth view adds more code to an already large file.

**Mitigation:** The additions are mechanical and localised to the view instantiation block
and `switchView()`. No refactor of the file's structure is needed for this work. If the
file grows further, a view registry refactor is a separate future task.

---

## Testing Strategy

### Copper tests

Dev dependencies in `pyproject.toml` already include `pytest-asyncio` and `pytest-httpx`.

Key scenarios per module:

**`test_router.py`** — unit tests, no I/O:
- `track_request` increments and decrements active list correctly
- `track_request` decrements even when the body raises an exception
- `select_node` picks least-busy among eligible nodes
- `select_node` breaks ties by priority
- `select_node` returns `None` when no healthy node has the model

**`test_health.py`** — uses `pytest-httpx` to mock Ollama's `/api/tags`:
- Successful response: `alive=True`, latency set, models list populated
- Timeout: `alive=False`, error string set
- HTTP 5xx: `alive=False`, error string captured

**`test_proxy.py`** — uses FastAPI `TestClient` + `pytest-httpx`:
- `/api/status` returns router's health snapshot
- `/api/nodes` returns SQLite registry
- `POST /api/nodes` round-trips through the database
- `DELETE /api/nodes/{name}` removes correctly
- `PATCH /api/nodes/{name}` updates enabled and priority
- `POST /api/pull` returns a task ID immediately (response time < 100ms regardless of
  model size)
- `GET /api/tasks/{task_id}` shows `running` while the background task is active;
  transitions to `completed` after the mock pull finishes
- Active request count is nonzero during a streaming proxy call (async test with delayed
  generator)

### Cairn RPC handler tests

**`test_rpc_copper.py`** — monkeypatches `httpx.Client`:
- Each of the 9 `copper/*` methods invokes the correct HTTP verb and endpoint path
- All calls use a 5-second timeout (including `copper/pull`)
- `copper/pull` body contains `{ model, node }` and response contains `task_id`
- `copper/tasks/{task_id}` maps to `GET /api/tasks/{task_id}` with the ID in the path
- `ConnectionRefusedError` → `{ "copper_available": False }` without raising
- `COPPER_URL` env var is respected: calls go to the overridden URL, not
  `http://localhost:11400`
- Unknown `copper/` subpath returns a structured error dict, not an uncaught exception

### Manual integration test

Start Copper (`copper serve`), register a local node, open the Tauri app, navigate to the
Copper view. Verify:
1. Node appears in the node grid with correct health state
2. Model list populates
3. Health indicator updates within 10 seconds
4. Enable/disable toggle updates the node state
5. "Pull Model" button returns immediately, progress card appears, card resolves when
   pull completes
6. Multiple simultaneous pulls each have independent progress cards
7. Adding a node via the Add Node dialog causes it to appear in the grid within one poll
   cycle
8. Removing a node removes it from the grid
9. Shutting down Copper causes the view to show "Copper is not running" within one poll
   cycle (10-30 seconds)

---

## Definition of Done

- [ ] `Router.track_request()` has `@asynccontextmanager` and is called in `proxy_request()`
- [ ] Active request count in `/api/status` is nonzero during in-flight proxied requests
- [ ] Streaming path decrements active count only after stream is fully consumed
- [ ] Health loop logs warnings instead of silently swallowing errors
- [ ] `/api/nodes` GET, POST, DELETE, PATCH endpoints exist and tested
- [ ] `POST /api/pull` returns a task ID immediately; pull runs in the background
- [ ] `GET /api/tasks/{task_id}` returns task status/progress/result
- [ ] `GET /api/tasks` returns list of recent tasks (bounded to 50)
- [ ] Task memory is bounded (cleanup strategy implemented)
- [ ] `copper.py` RPC handler proxies all 9 `copper/*` methods to Copper HTTP
- [ ] All RPC calls use a 5-second timeout — no call can block the stdio loop for more than 5 seconds
- [ ] `COPPER_URL` env var is respected; no hardcoded URL in `copper.py`
- [ ] Connection-refused path returns `{ "copper_available": False }` without raising
- [ ] `httpx.Client` (synchronous) used throughout `copper.py` — no `AsyncClient`
- [ ] `ui_rpc_server.py` dispatches `copper/*` to the handler
- [ ] `agentBar.ts` `AgentId` includes `'copper'`, entry appears in the sidebar
- [ ] `copperView.ts` duplicates `makePanel`/`makeStatRow`/`makeBar` inline (not imported from shared module)
- [ ] `copperView.ts` renders nodes, models, pull controls, node management (add/remove/toggle/priority)
- [ ] Pull UI: button starts pull, progress card polls every 2-3 seconds, resolves on completion
- [ ] "Copper is not running" state renders gracefully (no blank or crashed view)
- [ ] `switchView()` calls `startPolling`/`stopPolling` on enter/leave of the copper view
- [ ] Copper test suite passes: `test_router.py`, `test_health.py`, `test_proxy.py`
- [ ] Cairn `test_rpc_copper.py` passes
- [ ] Manual integration test passes (nodes, models, pull, health update, node management, graceful degradation)

---

## Confidence Assessment

**High confidence:**
- Option A proxy pattern — direct application of the RIVA proxy with `httpx.Client`
  substituted for the Unix socket. The pattern is proven in production.
- Agent bar and view router wiring — mechanical additions with exact parallels in reos/riva.
- Bug fixes — the missing `@asynccontextmanager` and bare-except are clear and localised.
- Background task pattern for pull — standard FastAPI `asyncio.create_task` idiom; the
  existing `/api/pull` already has all the pull logic, it just needs wrapping.
- 5-second timeout enforcement — straightforward `httpx.Client(timeout=5.0)`.

**Medium confidence:**
- The streaming active-request tracking fix (Risk 2) — the async generator teardown is
  non-trivial. A test is essential before shipping.
- `copperView.ts` layout — the node-grid, model-matrix, and progress card layout is more
  complex than `reosView.ts`'s stat rows. Prototype in-browser before polishing CSS.
- Task cleanup strategy (Risk 4) — the right approach (in-memory expiry vs SQLite
  persistence) depends on how frequently pulls are expected and whether history across
  restarts matters. The implementer should confirm with the user before choosing.
