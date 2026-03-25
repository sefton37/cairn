# Plan: ReOS Terminal Telemetry & Observability System

## Context

The ReOS terminal pipeline in the Cairn Tauri app has no observability. The full
pipeline — PTY output arrives → regex scan → error detected → `reos/propose` RPC
→ `propose_command()` → Ollama call → response → `extract_command()` → proposal
card shown → user action — produces no durable record of what happened, what
model was used, how long inference took, or whether a proposal was good. This
makes debugging detection failures and comparing model quality entirely
guesswork.

Key facts surfaced during research:

- `shell_propose.propose_command()` (ReOS: `src/reos/shell_propose.py`)
  currently returns `(command, explanation)` and discards all Ollama response
  metadata. The Ollama HTTP response body contains `model`, `eval_count`, and
  `total_duration` at the top level, but `_post_chat()` in
  `trcore/providers/ollama.py` strips the response down to `content.strip()`
  before returning.

- `handle_reos_propose()` (ReOS: `src/reos/rpc_handlers/propose.py`)
  wraps the call and returns `{command, explanation, success}` with no model or
  latency metadata.

- The frontend (`reosView.ts` lines 776-797) calls `reos/propose`, shows the
  proposal card, and handles three user actions: Run, Edit, Dismiss. None of
  these actions are recorded anywhere.

- The RPC dispatch pattern in `ui_rpc_server.py` lines 620-680 is table-driven
  with a clear convention: simple handlers go into `_SIMPLE_HANDLERS`, single
  string param handlers go into `_STRING_PARAM_HANDLERS`, full payload handlers
  use explicit `if method ==` blocks further down in
  `_handle_jsonrpc_request()`.

- Data dir is `~/.talkingrock/` (from `trcore/settings.py`). The convention is
  to put a separate SQLite file there for isolated concerns; this telemetry DB
  should live at `~/.talkingrock/reos_telemetry.db` to stay separate from the
  main `talkingrock.db`.

- `OllamaProvider` exposes `self._model` and `_get_default_model()`, so the
  model name is always knowable. However, `chat_text()` does not return it; a
  new internal method `_post_chat_with_meta()` is needed to surface it.

---

## Approach (Recommended): Thin Instrumentation Layer with Event Table

Write minimal, non-blocking telemetry that instruments the exact points where
information exists rather than adding cross-cutting middleware. The design
has three interlocking parts:

1. A SQLite schema in a dedicated file (`reos_telemetry.db`) with one central
   table and supporting indices.
2. A Python handler module (`reos/rpc_handlers/telemetry.py`) that writes events
   and answers analysis queries over RPC.
3. Targeted enrichments in `shell_propose.py` and `propose.py` to surface model
   name and latency without changing the public interface.
4. Frontend instrumentation at four well-defined points in `reosView.ts`.

The telemetry DB is append-only from the hot path. All writes are fire-and-forget
within a try/except so telemetry failures never affect proposal flow.

---

## Alternatives Considered

### Alternative A: In-process structured logging (JSONL)

Write events to `~/.talkingrock/reos_events.jsonl` instead of SQLite. Simpler
to write, requires no schema. Analysis requires external tooling (jq, pandas).

Rejected because: the ecosystem standard is SQLite for persistence; JSONL has
no ad-hoc query support; replay and analysis queries (p50/p95 latency, false
negative rate) would require parsing the file each time; no indices.

### Alternative B: Augment the main `talkingrock.db`

Add telemetry tables to the shared DB. Simpler dependency (no second DB
connection). But: the main DB is Cairn-owned and migrated by Cairn's migration
system; adding ReOS-specific diagnostic tables there creates coupling that
contradicts the spirit of the ReOS/Cairn separation. A separate file keeps
telemetry isolated and trivially deletable.

### Alternative C: Structured logging via Python `logging` + log aggregator

Emit structured JSON to the existing log file. Zero schema design. But: no
aggregate queries, no replay, no unique session tracking across the pipeline,
and the existing log file is a rotating text file not suitable for p95 analysis.

---

## Implementation Steps

### Step 1: Create `reos/telemetry.py` — DB init and write primitives

**File:** `ReOS/src/reos/telemetry.py`

This module owns the telemetry DB connection and the schema. It provides three
public functions: `init_db()`, `record_event()`, and `get_db_path()`.

Schema (see section below). The module must be safe to import with no side
effects; `init_db()` is called lazily on first write.

### Step 2: Enrich `OllamaProvider._post_chat()` to return metadata

**File:** `talkingrock-core/src/trcore/providers/ollama.py`

Add a private method `_post_chat_with_meta(payload, timeout)` that returns
`(content: str, model: str, latency_ms: int)`. Measure wall-clock time around
the `httpx.Client.post()` call using `time.monotonic()`. The model name comes
from `payload["model"]`. The existing `_post_chat()` stays unchanged (delegates
to the new method and discards meta) to avoid breaking all other callers.

Do NOT modify `chat_text()` signature in the `LLMProvider` protocol. The
enriched data flows only through a new internal call path in `shell_propose.py`.

### Step 3: Add `propose_command_with_meta()` to `shell_propose.py`

**File:** `ReOS/src/reos/shell_propose.py`

Add a new function `propose_command_with_meta(natural_language)` that returns
`(command, explanation, model_name, latency_ms, attempt_count)`. This function
is identical to `propose_command()` but calls `_post_chat_with_meta()` and
collects the timing and model data. The existing `propose_command()` stays as a
thin wrapper over the new one (drops the extra return values) to avoid breaking
CLI usage and the `main()` entry point.

`attempt_count` is 1 (first prompt succeeded) or 2 (retry was needed). This is
diagnostic signal for model comparison: a model that requires retry on 40% of
requests is worse than one that never does.

### Step 4: Enrich `handle_reos_propose()` to record telemetry

**File:** `ReOS/src/reos/rpc_handlers/propose.py`

Replace the call to `propose_command()` with `propose_command_with_meta()`. On
return, fire `telemetry.record_event()` with event type `proposal_generated`.
The RPC response gains two new optional fields: `model_name` and `latency_ms`.
These are passed back to the frontend so it can include them in user action
events.

This is the only place where blocking telemetry write is acceptable because we
are already in the RPC handler thread after the Ollama call has completed.

### Step 5: Create `reos/rpc_handlers/telemetry.py` — RPC handler

**File:** `ReOS/src/reos/rpc_handlers/telemetry.py`

Implement two RPC handler functions. Each is registered in `ui_rpc_server.py`.
See handler design section below.

### Step 6: Register telemetry handlers in `ui_rpc_server.py`

**File:** `Cairn/src/cairn/ui_rpc_server.py`

Add to the `_REOS_AVAILABLE` import block:

```python
from reos.rpc_handlers.telemetry import (
    handle_reos_telemetry_event as _handle_reos_telemetry_event,
    handle_reos_telemetry_query as _handle_reos_telemetry_query,
)
```

Both methods need a full dict payload (not a single string), so they go into
the explicit `if method ==` block in `_handle_jsonrpc_request()`, placed after
the existing ReOS `reos/propose` handler. The implementer should read the
dispatch function past line 760 to confirm whether a `_FULL_PAYLOAD_HANDLERS`
table already exists before adding new `if method ==` blocks.

### Step 7: Frontend instrumentation in `reosView.ts`

**File:** `Cairn/apps/cairn-tauri/src/reosView.ts`

Add a `recordEvent(eventType, payload)` helper that calls
`callbacks.kernelRequest('reos/telemetry/event', {...})` and silently eats
errors. Fire-and-forget (no `await`, just `.catch(() => {})`).

Instrument four points (see instrumentation section below).

---

## SQLite Schema

**File:** `~/.talkingrock/reos_telemetry.db`

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One row per discrete pipeline event. The event_type column is the
-- taxonomy discriminator; payload_json holds the type-specific fields.
CREATE TABLE IF NOT EXISTS reos_events (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT    NOT NULL,  -- UUID generated per terminal open
    trace_id      TEXT    NOT NULL,  -- UUID per proposal pipeline invocation
    ts            INTEGER NOT NULL,  -- Unix milliseconds (epoch)
    event_type    TEXT    NOT NULL,  -- See taxonomy below
    payload_json  TEXT    NOT NULL   -- JSON object, type-specific fields
);

CREATE INDEX IF NOT EXISTS idx_events_session  ON reos_events (session_id);
CREATE INDEX IF NOT EXISTS idx_events_trace    ON reos_events (trace_id);
CREATE INDEX IF NOT EXISTS idx_events_type_ts  ON reos_events (event_type, ts);
CREATE INDEX IF NOT EXISTS idx_events_ts       ON reos_events (ts);
```

No foreign keys between tables (all events are self-describing via `trace_id`
correlation). This keeps the write path trivial and the schema evolvable.

The session/trace IDs are the join key for E2E analysis. A single user action
(e.g., typing "open firefox") generates multiple events sharing one `trace_id`:
`error_detected` -> `proposal_requested` -> `proposal_generated` -> `user_action`.

---

## Event Type Taxonomy with Payload Schemas

All timestamps are Unix epoch milliseconds. All payloads are JSON objects.

### `session_start`
Fired when the terminal is opened. Establishes the session boundary.
```json
{
  "session_id": "uuid-v4"
}
```

### `session_end`
Fired when the terminal is closed or the view is torn down.
```json
{
  "session_id": "uuid-v4",
  "duration_ms": 12345
}
```

### `error_detected`
Fired when `scanForCommandNotFound()` matches a pattern. This is the entry
point of every proposal pipeline.
```json
{
  "raw_line": "bash: fi: command not found",
  "matched_shell": "bash",
  "failed_cmd": "fi",
  "extracted_input": "fi les in current dir",
  "input_source": "echoed_line | fallback_cmd"
}
```
`input_source` distinguishes cases where the full user input was recovered from
the echoed shell line vs. where only the bare failed command was available. This
is diagnostic for understanding false negatives caused by input extraction
failure.

### `proposal_requested`
Fired immediately before the `reos/propose` RPC call.
```json
{
  "natural_language": "fi les in current dir"
}
```

### `proposal_generated`
Fired when `handle_reos_propose()` returns (success or failure).
```json
{
  "natural_language": "fi les in current dir",
  "success": true,
  "command": "ls",
  "explanation": "Lists files in the current directory",
  "model_name": "llama3.2:3b",
  "latency_ms": 843,
  "attempt_count": 1,
  "failure_reason": null
}
```
`failure_reason` is non-null when `success` is false. Values: `"safety_block"`,
`"no_command_extracted"`, `"llm_error"`, `"extract_command_failed"`.

### `user_action`
Fired when the user acts on the proposal card.
```json
{
  "action": "run | edit | dismiss",
  "proposed_command": "ls",
  "model_name": "llama3.2:3b",
  "latency_ms": 843,
  "card_display_duration_ms": 2100
}
```
`card_display_duration_ms` is the wall clock between `showProposal()` being
called and the button click. Short dismissal times may indicate annoyance (the
proposal was obviously wrong). Long durations before "run" may indicate
hesitation (the proposal needed review).

### `false_negative_marker`
Fired by the analysis harness, not the live system. Used in E2E test replay to
mark events where a known-bad error pattern was not detected.
```json
{
  "raw_output_snippet": "...",
  "expected_event": "error_detected",
  "reason": "regex miss on fish shell variant"
}
```

---

## Python Handler Design

**File:** `ReOS/src/reos/rpc_handlers/telemetry.py`

Two handler functions:

```
handle_reos_telemetry_event(db, *, payload: dict) -> dict
```

Writes a single telemetry event. Fire-and-forget semantics: always returns
`{"success": True}` even if the write fails, to preserve the principle that
telemetry never affects application flow.

Expected params (all from frontend):
- `session_id: str`
- `trace_id: str`
- `event_type: str` (see taxonomy)
- `ts: int` (epoch ms, set by frontend for accurate timing)
- `payload: dict` (type-specific fields)

```
handle_reos_telemetry_query(db, *, query: str, params: dict) -> dict
```

Runs a named analysis query. The `query` param is a key into a registry of
pre-approved SELECT statements — never raw SQL from the frontend. Returns
`{"rows": [...], "columns": [...]}`.

Named queries:
- `"model_comparison"` — success rate and retry rate per model
- `"latency_percentiles"` — p50/p95 per model
- `"false_negative_rate"` — detections without proposals
- `"user_action_distribution"` — run/edit/dismiss breakdown
- `"recent_sessions"` — last N sessions
- `"trace_replay"` — full event sequence for one `trace_id`

The named query registry prevents SQL injection and limits the attack surface
to a known set of read-only SELECTs. The `params` dict provides safe binding
values (e.g., `{"days": 7}`).

The `db` param is the Cairn `Database` object passed by the dispatch framework.
Telemetry uses its own separate SQLite connection via `reos.telemetry.get_db()`,
so `db` is unused but must be accepted for dispatch compatibility — identical
pattern to `handle_reos_vitals`.

---

## Enriched `propose.py` Return Shape

After Step 4, the `reos/propose` RPC response becomes:

```json
{
  "command": "ls",
  "explanation": "Lists files",
  "success": true,
  "model_name": "llama3.2:3b",
  "latency_ms": 843
}
```

`model_name` and `latency_ms` are `null` when `success` is false. The frontend
stores these on the proposal card state and includes them in the subsequent
`user_action` event. No schema change to the existing fields.

If a TypeScript interface for the `reos/propose` response exists in
`Cairn/apps/cairn-tauri/src/types.ts`, add `model_name: string | null` and
`latency_ms: number | null` to it.

---

## Frontend Instrumentation Points (`reosView.ts`)

Add two module-level variables inside `createReosView()`:
- `sessionId: string` — UUID v4, generated once when `startTerminal()` is
  first called.
- `sessionStartedAt: number` — `Date.now()` value from `startTerminal()`.

Add per-proposal state:
- `currentTraceId: string` — UUID v4, generated in `scanForCommandNotFound()`
  when a match fires.
- `proposalShownAt: number | null` — `Date.now()` value set in `showProposal()`.
- `currentProposalMeta: { model_name: string|null, latency_ms: number|null }` —
  stored from the enriched `reos/propose` response.

**Point 1: `startTerminal()` — after `pty_start` resolves successfully**

```typescript
recordEvent('session_start', { session_id: sessionId });
```

**Point 2: `scanForCommandNotFound()` — after `extractUserInput()` returns,
before `requestProposal()`**

```typescript
currentTraceId = crypto.randomUUID();
recordEvent('error_detected', {
  raw_line: errorLine,
  matched_shell: detectedShell,  // 'bash' | 'sh' | 'zsh' | 'fish'
  failed_cmd: failedCmd,
  extracted_input: fullInput,
  input_source: fullInput !== failedCmd ? 'echoed_line' : 'fallback_cmd',
});
// immediately after:
recordEvent('proposal_requested', { natural_language: fullInput });
```

**Point 3: `requestProposal()` — inside the `.then()` callback, after result
is classified as success or failure**

```typescript
const failureReason = !result.success
  ? deriveFailureReason(result.explanation ?? '')
  : null;
recordEvent('proposal_generated', {
  natural_language: failedInput,
  success: result.success ?? false,
  command: result.command ?? '',
  explanation: result.explanation ?? '',
  model_name: result.model_name ?? null,
  latency_ms: result.latency_ms ?? null,
  attempt_count: 1,   // not yet tracked per-attempt from frontend
  failure_reason: failureReason,
});
```

**Point 4: Button click handlers**

In each of `btnApprove`, `btnEdit`, `btnDismiss` click handlers, before
`hideProposal()`:

```typescript
recordEvent('user_action', {
  action: 'run' | 'edit' | 'dismiss',
  proposed_command: currentProposedCommand,
  model_name: currentProposalMeta.model_name,
  latency_ms: currentProposalMeta.latency_ms,
  card_display_duration_ms: proposalShownAt
    ? Date.now() - proposalShownAt
    : null,
});
```

**`teardownTerminalResources()` — before `hideProposal()` call**

```typescript
recordEvent('session_end', {
  session_id: sessionId,
  duration_ms: sessionStartedAt ? Date.now() - sessionStartedAt : null,
});
```

The `recordEvent` helper:

```typescript
function recordEvent(eventType: string, payload: Record<string, unknown>): void {
  if (!sessionId || !currentTraceId) return;
  void callbacks.kernelRequest('reos/telemetry/event', {
    session_id: sessionId,
    trace_id: currentTraceId,
    ts: Date.now(),
    event_type: eventType,
    payload,
  }).catch(() => {
    // Telemetry failures are silent — never let them surface to user.
  });
}
```

Note: `session_start` and `session_end` events fire with `trace_id` equal to a
sentinel value (e.g., `"session"`) since they are not part of a proposal trace.
This is intentional and the query layer filters on `event_type` not `trace_id`
for session-level queries.

---

## Query Examples for Common Analysis Tasks

### Model comparison: proposal quality by model

```sql
SELECT
    json_extract(payload_json, '$.model_name')     AS model,
    COUNT(*)                                        AS total_proposals,
    SUM(json_extract(payload_json, '$.success'))   AS successes,
    ROUND(
        100.0 * SUM(json_extract(payload_json, '$.success')) / COUNT(*), 1
    )                                               AS success_pct,
    SUM(
        CASE WHEN json_extract(payload_json, '$.attempt_count') = 2
             THEN 1 ELSE 0 END
    )                                               AS retries,
    ROUND(AVG(json_extract(payload_json, '$.latency_ms')), 0) AS avg_latency_ms
FROM reos_events
WHERE event_type = 'proposal_generated'
  AND ts > (strftime('%s','now') - :days * 86400) * 1000
GROUP BY model
ORDER BY success_pct DESC, avg_latency_ms ASC;
```

### Latency p50 / p95 per model

```sql
WITH ranked AS (
    SELECT
        json_extract(payload_json, '$.model_name') AS model,
        json_extract(payload_json, '$.latency_ms') AS latency_ms,
        ROW_NUMBER() OVER (
            PARTITION BY json_extract(payload_json, '$.model_name')
            ORDER BY json_extract(payload_json, '$.latency_ms')
        ) AS rn,
        COUNT(*) OVER (
            PARTITION BY json_extract(payload_json, '$.model_name')
        ) AS total
    FROM reos_events
    WHERE event_type = 'proposal_generated'
      AND json_extract(payload_json, '$.success') = 1
      AND ts > (strftime('%s','now') - :days * 86400) * 1000
)
SELECT
    model,
    MAX(CASE WHEN rn <= total * 0.50 THEN latency_ms END) AS p50_ms,
    MAX(CASE WHEN rn <= total * 0.95 THEN latency_ms END) AS p95_ms,
    MAX(latency_ms)                                        AS max_ms
FROM ranked
GROUP BY model
ORDER BY p50_ms;
```

SQLite window functions are available from version 3.25 (2018); the system
SQLite on Linux 6.17 has this.

### False negative rate (detections without proposals)

```sql
-- Sessions where error_detected fired but no proposal_generated followed
-- within 10 seconds on the same trace_id.
WITH detections AS (
    SELECT session_id, trace_id, ts AS detected_at
    FROM reos_events WHERE event_type = 'error_detected'
),
proposals AS (
    SELECT session_id, trace_id, ts AS proposed_at
    FROM reos_events WHERE event_type = 'proposal_generated'
)
SELECT
    d.session_id,
    d.trace_id,
    d.detected_at,
    p.proposed_at,
    (p.proposed_at - d.detected_at) AS pipeline_ms
FROM detections d
LEFT JOIN proposals p
    ON d.session_id = p.session_id AND d.trace_id = p.trace_id
WHERE p.proposed_at IS NULL
   OR (p.proposed_at - d.detected_at) > 10000;
-- NULL proposed_at = detection fired but RPC was never called
-- pipeline_ms > 10s = extreme latency (timeout or model hang)
```

### User action distribution

```sql
SELECT
    json_extract(payload_json, '$.action')          AS action,
    COUNT(*)                                        AS count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct,
    ROUND(AVG(json_extract(payload_json, '$.card_display_duration_ms')), 0)
                                                    AS avg_display_ms
FROM reos_events
WHERE event_type = 'user_action'
  AND ts > (strftime('%s','now') - :days * 86400) * 1000
GROUP BY action;
```

### Trace replay (full pipeline for one invocation)

```sql
SELECT ts, event_type, payload_json
FROM reos_events
WHERE trace_id = :trace_id
ORDER BY ts ASC;
```

This is the primary debugging query. Given a `trace_id`, it reconstructs the
full pipeline history: what was detected, what was sent to the model, what the
model returned, what the user did, and how long each step took.

---

## Files Affected

### New files

| File | Purpose |
|------|---------|
| `ReOS/src/reos/telemetry.py` | DB init, schema, `record_event()`, `trim_old_events()` |
| `ReOS/src/reos/rpc_handlers/telemetry.py` | RPC handlers for event write and named queries |

### Modified files

| File | Change |
|------|--------|
| `talkingrock-core/src/trcore/providers/ollama.py` | Add private `_post_chat_with_meta()` |
| `ReOS/src/reos/shell_propose.py` | Add `propose_command_with_meta()` returning model/latency/attempts |
| `ReOS/src/reos/rpc_handlers/propose.py` | Call `*_with_meta`, record telemetry event, enrich RPC response |
| `Cairn/src/cairn/ui_rpc_server.py` | Import and register telemetry handlers |
| `Cairn/apps/cairn-tauri/src/reosView.ts` | Session/trace IDs, four event fires, `recordEvent()` helper |
| `Cairn/apps/cairn-tauri/src/types.ts` | Add `model_name` and `latency_ms` to `reos/propose` response type (if interface exists) |

### No new dependencies

All instrumentation uses Python stdlib (`sqlite3`, `time`, `uuid`, `json`) and
the existing `httpx` for Ollama timing. No new packages in either repo.

---

## Risks and Mitigations

### Risk 1: Telemetry write latency contaminates the proposal flow

The `record_event()` call in `handle_reos_propose()` happens after the Ollama
call completes (the slow part), on the RPC handler thread. A SQLite write to a
WAL-mode DB on local disk is typically under 1ms.

Mitigation: Wrap every `record_event()` call in `try/except Exception: pass`.
If the telemetry DB is locked or corrupt, the proposal still returns normally.
Log failures at DEBUG level only.

### Risk 2: Telemetry DB grows unbounded

At ~500 bytes average per event, 1 million events is ~500MB. A busy session
with many typos could accumulate this over months.

Mitigation: Add `trim_old_events(days: int)` to `telemetry.py`, called lazily
on `init_db()` after schema creation. Default retention is 90 days, overridable
via `TALKINGROCK_TELEMETRY_RETENTION_DAYS`. This bounds the DB with no user
action required.

### Risk 3: `_post_chat_with_meta()` and the retry decorator

The current `_post_chat()` is decorated with `@_retry_transient`. The timing
measurement must wrap the entire retry sequence, not just one attempt, so that
`latency_ms` reflects actual user-perceived wait time.

Mitigation: Measure with `time.monotonic()` in `propose_command_with_meta()`
at the call site, not inside `_post_chat_with_meta()`. The model name comes
from `payload["model"]` which is set before the retry loop. This cleanly
separates timing (call site's concern) from execution (provider's concern).

### Risk 4: Ollama `total_duration` field availability

The Ollama `/api/chat` response includes `total_duration` (nanoseconds) but
this is absent or zero on some model/version combinations.

Mitigation: Use wall-clock time exclusively. Capturing Ollama's `total_duration`
as a secondary field is optional and can be added later without schema changes
(it would appear inside `payload_json`).

### Risk 5: Orphaned `error_detected` events from suppressed proposals

The frontend suppresses `requestProposal()` when `proposalPending` is true or
the card is already showing (line 710 in `reosView.ts`). In these cases,
`error_detected` fires but no `proposal_generated` follows.

Mitigation: This is expected behavior. The analysis queries account for it
(the false negative rate query uses a LEFT JOIN). Document this behavior in
the telemetry module's docstring so future analysts do not miscount.

### Risk 6: `trcore` is a shared library used by Cairn

`OllamaProvider` is used by both Cairn and ReOS. The new method is private
(underscore-prefixed) and only called from `shell_propose.py`. Cairn's callers
all use `chat_text()` / `chat_json()` which remain unchanged.

Mitigation: Add a code comment on `_post_chat_with_meta()` marking it as
ReOS-only diagnostic infrastructure. If trcore ever formalizes a metrics
interface, this can be promoted then.

---

## E2E Test Harness Design

The telemetry schema enables a replay harness (separate test utility, not
production code).

**How it works:**

1. Collect a corpus of PTY output snippets from real terminal sessions.
   Store as text fixtures in `ReOS/tests/fixtures/pty_sessions/`.

2. The harness replays each snippet through `scanForCommandNotFound()` and
   records which snippets triggered `error_detected` events.

3. Annotate the corpus with ground truth (does this snippet contain a real
   "command not found" pattern?). Compute precision and recall of the regex.

4. For proposal quality: replay annotated snippets through `propose_command()`
   and judge output. Judgment is manual initially; a local LLM judge can be
   added later to compare proposed command to annotated expected command.

**Key metrics from the harness:**

- Regex scanner recall: fraction of real errors detected.
- Regex scanner precision: fraction of detections that were real errors.
- Proposal success rate: fraction of detected errors that got a valid command.
- Latency by model: measured under controlled replay conditions.

The harness stores its results as `false_negative_marker` events in the
telemetry DB, enabling the false negative rate query to surface them alongside
live data.

---

## Testing Strategy

### Unit tests for `telemetry.py`

- `test_init_db_creates_schema`: verify tables and indices exist after `init_db()`.
- `test_record_event_happy_path`: write an event, read it back, check all fields.
- `test_record_event_never_raises`: pass corrupt payload, verify no exception propagates.
- `test_trim_old_events`: insert events at varying ages, verify retention works.

### Unit tests for `propose_command_with_meta()`

- `test_returns_model_name_and_latency`: mock `_post_chat_with_meta`, verify
  the return tuple contains all five fields.
- `test_attempt_count_on_retry`: mock first attempt to fail `extract_command`,
  verify `attempt_count=2` on successful retry.
- `test_latency_is_non_negative`: verify `latency_ms` is always >= 0.

### Unit tests for `handle_reos_telemetry_query()`

- `test_named_query_model_comparison`: seed DB with known events, verify query
  returns expected aggregates.
- `test_rejects_unknown_query_name`: verify `ValueError` (not raw SQL execution)
  for unknown query names.

### Integration test

- `test_propose_records_telemetry`: call `handle_reos_propose()` with a mocked
  Ollama, verify a `proposal_generated` event appears in the telemetry DB with
  correct `model_name` and `latency_ms` fields.

### Frontend instrumentation (manual verification)

Open the Tauri app and type a nonexistent command in the terminal. Verify via
`reos/telemetry/query` with `query: "trace_replay"` and the most recent
`trace_id` that a complete 4-event sequence appears: `error_detected` ->
`proposal_requested` -> `proposal_generated` -> `user_action`.

---

## Definition of Done

- [ ] `ReOS/src/reos/telemetry.py` created: `init_db()`, `record_event()`,
      `get_db_path()`, `trim_old_events()` all implemented and unit tested.
- [ ] `_post_chat_with_meta()` added to `OllamaProvider` (private method).
- [ ] `propose_command_with_meta()` in `shell_propose.py` returns
      `(command, explanation, model_name, latency_ms, attempt_count)`.
- [ ] `propose_command()` delegates to `*_with_meta` and drops extra values;
      CLI behavior unchanged.
- [ ] `handle_reos_propose()` calls `*_with_meta`, records `proposal_generated`
      event, returns `model_name` and `latency_ms` in RPC response.
- [ ] `ReOS/src/reos/rpc_handlers/telemetry.py` created with both handlers and
      all six named queries implemented.
- [ ] Both telemetry handlers registered in `ui_rpc_server.py`.
- [ ] `reosView.ts` fires events at all four points with correct payloads.
- [ ] All unit tests pass. Integration test passes with mocked Ollama.
- [ ] Typing a nonexistent command in the live terminal produces a complete
      4-event trace queryable via `reos/telemetry/query`.
- [ ] Telemetry failures in the hot path produce a DEBUG log entry, not an
      exception or user-visible error.
- [ ] DB confirmed at `~/.talkingrock/reos_telemetry.db` after first run.
- [ ] `types.ts` updated with enriched `reos/propose` response type.

---

## Confidence Assessment

**High confidence:**

- The single-table polymorphic schema with `trace_id` correlation is the right
  fit for an append-only diagnostic store of this scale. SQLite WAL handles
  concurrent reads from analysis queries without blocking writes.
- All four frontend instrumentation points are well-defined in the existing
  code; the existing `proposalPending` / `proposalCard.style.display` state
  makes adding `proposalShownAt` trivial.
- The private `_post_chat_with_meta()` approach is the minimal-risk path through
  the shared `trcore` library; no protocol changes required.
- Fire-and-forget telemetry with `try/except` wrapping is correct and will not
  affect proposal latency.

**Medium confidence:**

- The dispatch registration for full-payload handlers. The reviewed dispatch
  table (lines 620-760 of `ui_rpc_server.py`) does not show a
  `_FULL_PAYLOAD_HANDLERS` table. The implementer should read the full
  `_handle_jsonrpc_request()` function before adding new `if method ==` blocks
  to confirm the correct insertion point.
- `attempt_count` from the frontend side: the current `requestProposal()`
  function has no visibility into whether `propose_command_with_meta()` retried.
  The `attempt_count` field will always be 1 as reported from the frontend event.
  The backend records the actual count in `proposal_generated` via the RPC
  response; the frontend event is a best-effort echo. This is acceptable for
  initial version.

**Unknowns requiring validation before implementation:**

1. Whether `ui_rpc_server.py` past line 760 contains a `_FULL_PAYLOAD_HANDLERS`
   dict or similar. The full dispatch function was not reviewed.
2. Whether `trcore` tests cover `OllamaProvider._post_chat()` in a way that
   would break if the internal method is replaced by a delegate. Adding a sibling
   method avoids this risk, but the test suite should be checked.
3. Whether `Cairn/apps/cairn-tauri/src/types.ts` has an interface for the
   `reos/propose` response that needs updating.
