# Plan: Tool Purge (20 tools) + Benchmark System

## Overview

This document covers two related tasks:

1. **Task 1** — Remove 20 orphaned MCP tools from Cairn's tool surface
2. **Task 2** — Build `Cairn/benchmarks/` mirroring ReOS's benchmark framework

These tasks are ordered: do the purge first, because the post-purge tool inventory defines the
benchmark corpus scope.

---

# Task 1: Tool Purge

## Context

Cairn currently exposes 56 tools across two files:
- `src/cairn/cairn/mcp_tools.py` — inner file: `list_tools()` (definitions) + `CairnToolHandler.call_tool()` (dispatcher) + handler methods
- `src/cairn/mcp_tools.py` — outer public wrapper: re-exposes `list_tools()`, `call_tool()`, plus an alias remapping block for `cairn_play_acts_list` and `cairn_play_scenes_list`

20 tools have no backing product feature. They were built speculatively and have never been
wired into an active user-facing capability.

**Tools to remove (20 total):**

| # | Tool | Orphan reason |
|---|------|---------------|
| 1 | `cairn_set_kanban_state` | No kanban board surface |
| 2 | `cairn_surface_waiting` | Depends on kanban waiting state |
| 3 | `cairn_surface_needs_priority` | Priority system unused |
| 4 | `cairn_set_priority` | Priority system unused |
| 5 | `cairn_defer_item` | Moves to kanban "someday" |
| 6 | `cairn_set_due_date` | Due dates without task management |
| 7 | `cairn_link_contact` | Contact linking unused |
| 8 | `cairn_unlink_contact` | Contact linking unused |
| 9 | `cairn_surface_contact` | Contact linking unused |
| 10 | `cairn_get_contact_links` | Contact linking unused |
| 11 | `cairn_check_coherence` | Coherence system dormant |
| 12 | `cairn_add_anti_pattern` | Coherence system dormant |
| 13 | `cairn_remove_anti_pattern` | Coherence system dormant |
| 14 | `cairn_list_anti_patterns` | Coherence system dormant |
| 15 | `cairn_get_identity_summary` | Coherence system dormant |
| 16 | `cairn_activity_summary` | Analytics unused |
| 17 | `cairn_set_autostart` | Autostart mechanism unclear |
| 18 | `cairn_get_autostart` | Autostart mechanism unclear |
| 19 | `cairn_play_acts_list` | Legacy alias for `cairn_list_acts` |
| 20 | `cairn_play_scenes_list` | Legacy alias for `cairn_list_scenes` |

The count is 20, not 21 — `cairn_set_due_date` was listed twice in the original task brief.

### Important: What NOT to remove

The backing store methods, database tables (kanban state, priority, due_date columns, contact
links tables, identity/coherence tables), and any code in `store.py`, `coherence.py`, or
`identity.py` should **not** be touched. The schema is shared and migrations are cumulative.
The purge is surface-only: tool definitions and dispatcher branches only.

### Undo reverse-dispatch complication

`CairnToolHandler._execute_reverse_tool()` at line 2869 of `src/cairn/cairn/mcp_tools.py`
contains a dispatch map that includes `cairn_set_priority` and `cairn_set_kanban_state` as
reverse tools for undo operations:

```python
tool_methods = {
    "cairn_update_act": self._update_act,
    "cairn_update_scene": self._update_scene,
    "cairn_set_priority": self._set_priority,        # removing the MCP tool
    "cairn_set_kanban_state": self._set_kanban_state, # removing the MCP tool
    "cairn_delete_act": self._delete_act,
    "cairn_delete_scene": self._delete_scene,
}
```

These entries reference `_set_priority` and `_set_kanban_state` as **internal handler methods**,
not as public tools. Since the requirement is to remove the MCP tool surface but keep the backing
methods, these lines in `_execute_reverse_tool()` must be **kept** — they call the private
`_set_priority` and `_set_kanban_state` methods which are not being deleted. Removing these
from the undo dispatcher would break undo for any historical undo contexts that reference these
operations.

### Test impact

The alias tools `cairn_play_acts_list` and `cairn_play_scenes_list` are referenced in three test files:

- `tests/test_agent_integration.py` — uses `cairn_play_acts_list` as mock tool name in FakeOllama
  setup (3 occurrences)
- `tests/test_agent_policy.py` — uses both alias names as representative tools in policy tests;
  the comment at line 46 explicitly notes these replaced git tools after that purge
- `tests/test_cairn.py` — references `cairn_set_priority` in an `UndoContext` test data fixture

**What to do with these tests:**
- In `test_agent_integration.py` and `test_agent_policy.py`: replace `cairn_play_acts_list`
  with `cairn_list_acts` and `cairn_play_scenes_list` with `cairn_list_scenes`. The tests
  test agent policy behavior, not the alias tools themselves. The behavior is identical after
  removal because the outer `call_tool()` currently remaps aliases to the canonical names anyway.
- In `test_cairn.py`: the `UndoContext` fixture at line 572 uses `cairn_set_priority` as a string
  literal in test data for serialization/deserialization testing. This test does not invoke the
  MCP tool — it tests the `UndoContext` dataclass. Leave it unchanged; string literals in test
  data are not a product dependency.
- In `test_e2e_cairn.py`: line 1306 lists `cairn_set_priority` in a list of tool names for an
  E2E test that calls `store.set_priority()` directly (line 1340), not via MCP. The comment at
  line 1339 says "cairn_set_priority uses this". This comment is documenting which tool previously
  used the store method. After the purge, update the comment; the test itself does not invoke the
  tool.

## Approach (Recommended)

Remove cleanly in a single pass. The two files are independent: the inner file owns definitions
and dispatch, the outer file owns the public wrapper and the alias map.

**Constraint:** Do not delete backing handler methods (`_set_priority`, `_set_kanban_state`,
`_set_due_date`, `_defer_item`, `_surface_waiting`, `_surface_needs_priority`, `_link_contact`,
`_unlink_contact`, `_surface_contact`, `_get_contact_links`, `_check_coherence`,
`_add_anti_pattern`, `_remove_anti_pattern`, `_list_anti_patterns`, `_get_identity_summary`,
`_activity_summary`, `_set_autostart`, `_get_autostart`). These remain as private internal
methods in case they are needed for undo dispatch or future reinstatement.

## Alternatives Considered

**Alternative A: Mark tools as deprecated rather than removing them**
Add a `deprecated: true` marker to each tool definition and have `list_tools()` filter them
out, but keep the dispatcher branches. Advantages: safer rollback. Disadvantages: increases
confusion for the benchmark corpus and for the LLM which still sees the tool count reflected
in its context window. The goal of the purge is a smaller, cleaner tool surface — half-removal
defeats this.

**Alternative B: Remove backing methods too**
Delete `_set_priority`, `_set_kanban_state`, etc. Cleaner code. Disadvantages: breaks the
`_execute_reverse_tool()` reverse dispatch map for historical undo contexts, risks breaking
any internal callers we may have missed, and violates the explicit instruction to preserve
the schema layer. Surface-only removal is safer.

**Recommendation: Approach in the plan body** — remove from `list_tools()` and from
`call_tool()` dispatch, keep backing methods.

## Implementation Steps

### Step 1: Edit `src/cairn/cairn/mcp_tools.py` — `list_tools()`

Remove the `Tool(...)` blocks for these 18 tools (the two alias tools live in the outer file):

1. `cairn_set_priority` (line 127)
2. `cairn_set_kanban_state` (line 155)
3. `cairn_set_due_date` (line 180)
4. `cairn_defer_item` (line 199)
5. `cairn_surface_needs_priority` (line 270)
6. `cairn_surface_waiting` (line 283)
7. `cairn_link_contact` (line 324)
8. `cairn_unlink_contact` (line 352)
9. `cairn_surface_contact` (line 363)
10. `cairn_get_contact_links` (line 375)
11. `cairn_activity_summary` (line 666)
12. `cairn_check_coherence` (line 681)
13. `cairn_add_anti_pattern` (line 708)
14. `cairn_remove_anti_pattern` (line 729)
15. `cairn_list_anti_patterns` (line 743)
16. `cairn_get_identity_summary` (line 748)
17. `cairn_set_autostart` (line 827)
18. `cairn_get_autostart` (line 845)

Also remove or update the section comment headers that become empty after removal (e.g.
`# =====================================================================` / `# Analytics`
/ `# =====================================================================` if no tools remain
in that section).

**`cairn_list_items` cleanup:** `cairn_list_items`'s input schema has `kanban_state` and
`has_priority` filter parameters. These parameters still work — they call `store.list_metadata()`
which remains. Do not remove these parameters from the schema; the LLM can still use them
for filtering, and removing them would be a separate decision about whether the store query
should be simplified.

### Step 2: Edit `src/cairn/cairn/mcp_tools.py` — `CairnToolHandler.call_tool()`

Remove the 18 dispatch branches corresponding to the tools removed in Step 1. The branches
are consecutive `if name == "cairn_X":` statements in the dispatcher. Remove each block.

**Specifically preserve:** The dispatch branches for `cairn_set_priority` and
`cairn_set_kanban_state` ARE being removed from `call_tool()`. But the private handler
methods `_set_priority()` and `_set_kanban_state()` are NOT deleted — they are still referenced
from `_execute_reverse_tool()`.

### Step 3: Edit `src/cairn/mcp_tools.py` — outer public wrapper

Remove the two alias tools from `list_tools()`:
- `cairn_play_acts_list` (line 389–415)
- `cairn_play_scenes_list` (line 394–415)

Remove the alias remapping block from `call_tool()`:
```python
# Lines 428-433 in src/cairn/mcp_tools.py
_play_aliases = {
    "cairn_play_acts_list": "cairn_list_acts",
    "cairn_play_scenes_list": "cairn_list_scenes",
}
if name in _play_aliases:
    name = _play_aliases[name]
```

Remove the `tools.extend([...])` block that adds the alias tools (lines 386–415).

### Step 4: Update tests

**`tests/test_agent_policy.py`:**
- Replace all occurrences of `cairn_play_acts_list` with `cairn_list_acts`
- Replace all occurrences of `cairn_play_scenes_list` with `cairn_list_scenes`
- Update the comment at line 46 to remove the mention of these as replacement tools

**`tests/test_agent_integration.py`:**
- Replace all occurrences of `cairn_play_acts_list` with `cairn_list_acts`

**`tests/test_e2e_cairn.py`:**
- Line 1339: update comment from `# Set priority (cairn_set_priority uses this)` to
  `# Set priority (store layer)` — the test still exercises the store method correctly

**`tests/test_cairn.py`:**
- No changes needed. The `UndoContext` test fixture at line 572 uses `"cairn_set_priority"`
  as a string literal in serialization test data. This is test data, not a product dependency.

### Step 5: Verify

Run the full test suite:
```
PYTHONPATH="src" pytest tests/ -x --tb=short -q --no-cov
```

Expected: All ~2033 tests pass. Zero failures introduced by the purge.

## Files Affected

| File | Change |
|------|--------|
| `src/cairn/cairn/mcp_tools.py` | Remove 18 `Tool(...)` definitions from `list_tools()`, remove 18 dispatch branches from `call_tool()` |
| `src/cairn/mcp_tools.py` | Remove 2 alias `Tool(...)` definitions, remove `_play_aliases` remap block |
| `tests/test_agent_policy.py` | Replace alias tool names with canonical names |
| `tests/test_agent_integration.py` | Replace alias tool names with canonical names |
| `tests/test_e2e_cairn.py` | Update comment at line 1339 |

**Do NOT modify:**
- `src/cairn/cairn/store.py` — keep all store methods
- `src/cairn/cairn/coherence.py` — keep dormant coherence code
- `src/cairn/cairn/identity.py` — keep identity code
- `src/cairn/cairn/mcp_tools.py` backing handler methods (`_set_priority`, etc.)
- `src/cairn/cairn/mcp_tools.py` `_execute_reverse_tool()` dispatch map

## Risks and Mitigations

**Risk: Undo breaks for historical undo contexts referencing removed tools**
Mitigation: The `_execute_reverse_tool()` map is not touched. The private `_set_priority`
and `_set_kanban_state` methods remain. Undo will work for any stored undo contexts that
reference these operations.

**Risk: LLM produces calls to removed tools**
Mitigation: After the purge, the removed tool names will no longer appear in `list_tools()`.
The LLM will not be offered these tools. If an old conversation history contains a removed
tool name, `call_tool()` will fall through to the `raise CairnToolError(unknown_tool)` at the
bottom of the dispatcher — which is the correct behavior.

**Risk: Intent engine still routes to removed tools**
The `src/cairn/cairn/intent_engine.py` was checked — it does not reference any of the 20
tools being removed by name in its pattern matching or `CATEGORY_TOOLS` map. No change needed.

**Risk: Tests reference alias tools as structural markers in policy tests**
Mitigation: The policy test behavior does not depend on which specific tool is called; the
tests verify argument-stripping policy. Substituting `cairn_list_acts` for `cairn_play_acts_list`
does not change what is being tested.

## Post-Purge Tool Inventory

After the purge, 36 tools remain (56 defined minus 20 removed). The surviving tools are:

**Knowledge Base (read/touch):** `cairn_list_items`, `cairn_get_item`, `cairn_touch_item`
**Surfacing:** `cairn_surface_next`, `cairn_surface_today`, `cairn_surface_stale`, `cairn_surface_attention`
**Thunderbird:** `cairn_thunderbird_status`, `cairn_search_contacts`, `cairn_get_calendar`, `cairn_get_upcoming_events`, `cairn_get_todos`
**Acts CRUD:** `cairn_list_acts`, `cairn_create_act`, `cairn_update_act`, `cairn_delete_act`, `cairn_set_active_act`
**Scenes CRUD:** `cairn_list_scenes`, `cairn_create_scene`, `cairn_update_scene`, `cairn_delete_scene`
**Undo/Confirm:** `cairn_undo_last`, `cairn_confirm_action`, `cairn_cancel_action`
**Block Editor:** `cairn_create_block`, `cairn_update_block`, `cairn_search_blocks`, `cairn_get_page_content`, `cairn_create_page`, `cairn_list_pages`, `cairn_update_page`, `cairn_add_scene_block`, `cairn_get_unchecked_todos`, `cairn_get_page_tree`, `cairn_export_page_markdown`
**Health:** `cairn_health_report`, `cairn_acknowledge_health`, `cairn_health_history`

## Definition of Done

- [ ] `list_tools()` in `src/cairn/cairn/mcp_tools.py` returns exactly 36 tools
- [ ] `list_tools()` in `src/cairn/mcp_tools.py` returns exactly 36 tools (no alias tools)
- [ ] All 20 removed tool names return `unknown_tool` error when called via `call_tool()`
- [ ] `_execute_reverse_tool()` still contains entries for `cairn_set_priority` and `cairn_set_kanban_state`
- [ ] All tests pass: `PYTHONPATH="src" pytest tests/ -x --tb=short -q --no-cov`
- [ ] No references to the 20 removed tool names remain in `list_tools()` or `call_tool()` dispatcher
- [ ] `test_agent_policy.py` and `test_agent_integration.py` no longer reference alias tool names

---

# Task 2: Benchmark System

## Context

Cairn has an existing E2E test harness at `tools/harness/` with 12 synthetic persona profiles
at `tools/test_profiles/`. The harness runs broad "what type of query is this" questions (8
categories × 12 personas) but does not test tool correctness: it cannot answer "did the model
select the right tool?" because it never specifies a correct tool for each question.

The benchmark system needs to answer different questions than the harness:
1. For a given tool, does the model correctly select it (tool match)?
2. For a given tool, does the model pass correct arguments (args match)?
3. Does the tool call succeed (execution success)?
4. How does this vary across 17 models (16 Ollama + Claude API)?
5. How does it vary across communication styles (12 personas)?

ReOS has a complete benchmark framework at `ReOS/benchmarks/` that solves a structurally similar
problem (NL → shell command selection). We mirror its architecture with Cairn-specific adaptations.

**Key structural difference from ReOS:**
ReOS tests: `NL → command string`
Cairn tests: `NL → tool selection → tool arguments → tool execution → response`
This means Cairn's `benchmark_results` table needs to capture the full tool call trace, not just
a final command string.

## Approach (Recommended)

Build `Cairn/benchmarks/` as a new top-level directory alongside `tools/`, mirroring ReOS's
module structure. The existing `tools/harness/` is **not replaced** — it continues to serve
its broader persona simulation purpose. The new `benchmarks/` system addresses a different
question (tool-specific correctness) and is the foundation for model comparison.

**Reuse from existing harness:**
- The 12 persona profiles in `tools/test_profiles/` (databases are the test fixtures)
- The `tools/harness/mock_thunderbird.py` mock injection mechanism
- The `ConsciousnessObserver` event extraction pattern from `tools/harness/runner.py`
- The `_load_profile_meta()` pattern for reading persona metadata
- The personality style functions from `tools/harness/question_generator.py`

**Build new:**
- The corpus (tool-specific questions, not category-based questions)
- The database schema (tool-call-oriented results, not classification-oriented)
- The runner (exercises tool calls, not just classification)
- The matching/scoring algorithms (tool match, args match, not command string matching)

## Alternative Considered

**Alternative: Extend the existing harness rather than creating a separate benchmarks/ directory**
Add tool-specific questions to `question_generator.py` and extend the recorder schema.
Rejected because: (a) the existing harness and the benchmark serve different purposes and
should be independently runnable; (b) the recorder schema change would require migrating
existing harness.db results; (c) coupling the two increases complexity for both; (d) the
ReOS mirror structure is the stated requirement.

## Directory Structure

```
Cairn/benchmarks/
├── __init__.py          # empty
├── __main__.py          # CLI: run / analyze / list-tools / export
├── corpus.py            # Corpus loader and TestCase dataclass
├── corpus.json          # Tool-specific test cases (authoritative source)
├── db.py                # SQLite schema + helper functions
├── runner.py            # BenchmarkRunner class
├── matching.py          # Scoring: tool_match, args_match, execution_success, response_quality
├── models.py            # Model matrix (copy from ReOS, Cairn-appropriate)
├── anthropic_provider.py # Copy from ReOS/benchmarks/, unchanged
└── README.md            # How to use
```

## Database Schema

**File:** `Cairn/benchmarks/db.py`
**Database path:** `~/.talkingrock/cairn_benchmark.db`

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- One row per invocation of the runner
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_uuid            TEXT    NOT NULL UNIQUE,      -- UUID4
    started_at          INTEGER NOT NULL,              -- epoch ms
    completed_at        INTEGER,                       -- epoch ms, NULL if interrupted
    model_name          TEXT    NOT NULL,              -- e.g. "qwen2.5:7b"
    model_family        TEXT,                          -- e.g. "qwen2.5"
    model_param_count   TEXT,                          -- e.g. "7b"
    ollama_url          TEXT    NOT NULL,
    temperature         REAL    NOT NULL DEFAULT 0.0,  -- Cairn uses 0.0 for determinism
    corpus_version      TEXT,                          -- git hash of corpus.json
    host_info           TEXT,                          -- JSON: {hostname, cpu, ram_gb, gpu}
    notes               TEXT
);

-- The corpus: one row per (tool, variant) combination
-- Populated from corpus.json on first run; stable across runs
CREATE TABLE IF NOT EXISTS test_cases (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id             TEXT    NOT NULL UNIQUE,  -- e.g. "cairn_list_acts_basic"
    tool_name           TEXT    NOT NULL,         -- target tool, e.g. "cairn_list_acts"
    question_template   TEXT    NOT NULL,         -- canonical phrasing before persona styling
    variant             TEXT    NOT NULL CHECK (  -- what aspect this tests
        variant IN ('basic', 'edge', 'regression', 'off_topic', 'ambiguous')
    ),
    expected_tool       TEXT    NOT NULL,         -- correct tool name (often = tool_name, but
                                                  -- 'off_topic' cases have 'none')
    expected_args_schema TEXT,                    -- JSON schema for acceptable args (nullable)
    notes               TEXT
);

-- One row per (run × case × persona)
CREATE TABLE IF NOT EXISTS benchmark_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id              INTEGER NOT NULL REFERENCES benchmark_runs(id),
    case_id             TEXT    NOT NULL REFERENCES test_cases(case_id),
    executed_at         INTEGER NOT NULL,          -- epoch ms

    -- Persona context
    persona_id          TEXT    NOT NULL,          -- profile directory name, e.g. "priya_chandrasekaran"
    persona_style       TEXT    NOT NULL,          -- personality: analytical/terse/verbose/anxious/creative/methodical
    prompt_used         TEXT    NOT NULL,          -- actual prompt after persona styling

    -- Pipeline outcome
    tool_selected       TEXT,                      -- tool name LLM chose, or NULL if no tool call
    tool_args           TEXT,                      -- JSON of actual args passed
    tool_execution_ok   INTEGER,                   -- 1 if tool call succeeded, 0 if raised, NULL if not called
    tool_error          TEXT,                      -- exception message if execution failed
    response_text       TEXT,                      -- final response to user

    -- Latency
    latency_ms          INTEGER,                   -- wall clock for full pipeline

    -- Token counts (Ollama native, NULL for Anthropic)
    tokens_prompt       INTEGER,
    tokens_completion   INTEGER,

    -- Pipeline error (exception outside tool call itself)
    pipeline_error      TEXT,

    -- Accuracy scoring (computed after the run)
    tool_match          INTEGER,   -- 1 if tool_selected == expected_tool
    args_match          INTEGER,   -- 1 if args satisfy expected_args_schema (partial OK)
    execution_success   INTEGER,   -- 1 if tool_execution_ok AND no tool_error
    response_quality    TEXT,      -- 'good' | 'partial' | 'wrong' | NULL (manual or heuristic)

    UNIQUE (run_id, case_id, persona_id)
);

CREATE INDEX IF NOT EXISTS idx_results_run       ON benchmark_results (run_id);
CREATE INDEX IF NOT EXISTS idx_results_case      ON benchmark_results (case_id);
CREATE INDEX IF NOT EXISTS idx_results_tool      ON benchmark_results (tool_selected);
CREATE INDEX IF NOT EXISTS idx_results_persona   ON benchmark_results (persona_id);
CREATE INDEX IF NOT EXISTS idx_cases_tool        ON test_cases (tool_name);
CREATE INDEX IF NOT EXISTS idx_runs_model        ON benchmark_runs (model_name);
```

**Views:**

```sql
-- Overall accuracy per model
CREATE VIEW IF NOT EXISTS v_model_accuracy AS
SELECT
    r.model_name,
    r.model_param_count,
    COUNT(br.id)                                                    AS total,
    ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)      AS tool_match_pct,
    ROUND(100.0 * SUM(br.args_match)      / COUNT(br.id), 1)      AS args_match_pct,
    ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1)    AS execution_pct,
    ROUND(AVG(br.latency_ms), 0)                                   AS avg_latency_ms
FROM benchmark_runs r
JOIN benchmark_results br ON br.run_id = r.id
GROUP BY r.model_name, r.model_param_count
ORDER BY tool_match_pct DESC;

-- Accuracy per tool per model
CREATE VIEW IF NOT EXISTS v_tool_accuracy AS
SELECT
    r.model_name,
    tc.tool_name,
    tc.variant,
    COUNT(br.id)                                                    AS total,
    ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)      AS tool_match_pct,
    ROUND(100.0 * SUM(br.args_match)      / COUNT(br.id), 1)      AS args_match_pct,
    ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1)    AS execution_pct
FROM benchmark_runs r
JOIN benchmark_results br ON br.run_id = r.id
JOIN test_cases tc         ON tc.case_id = br.case_id
GROUP BY r.model_name, tc.tool_name, tc.variant
ORDER BY r.model_name, tc.tool_name;

-- Accuracy by persona style
CREATE VIEW IF NOT EXISTS v_persona_accuracy AS
SELECT
    r.model_name,
    br.persona_style,
    COUNT(br.id)                                                    AS total,
    ROUND(100.0 * SUM(br.tool_match)      / COUNT(br.id), 1)      AS tool_match_pct,
    ROUND(100.0 * SUM(br.execution_success) / COUNT(br.id), 1)    AS execution_pct
FROM benchmark_runs r
JOIN benchmark_results br ON br.run_id = r.id
GROUP BY r.model_name, br.persona_style
ORDER BY r.model_name, br.persona_style;

-- Failure patterns: tool mismatches
CREATE VIEW IF NOT EXISTS v_mismatches AS
SELECT
    r.model_name,
    tc.tool_name         AS expected_tool,
    br.tool_selected     AS actual_tool,
    tc.variant,
    br.persona_style,
    br.prompt_used,
    br.tool_error,
    br.pipeline_error
FROM benchmark_runs r
JOIN benchmark_results br ON br.run_id = r.id
JOIN test_cases tc         ON tc.case_id = br.case_id
WHERE br.tool_match = 0
ORDER BY r.model_name, tc.tool_name;
```

## Corpus Structure

**File:** `Cairn/benchmarks/corpus.json`

The corpus is a JSON array of test case objects. Each tool in the post-purge inventory gets
at minimum:
- 1 `basic` variant: core functionality, unambiguous phrasing
- 1–2 `edge` variants: parameter variations, unusual inputs
- 1 `regression` variant: historically confused case or LLM-tricky phrasing

Off-topic and ambiguous variants cover cross-cutting concerns:
- `off_topic`: questions that should not invoke any tool
- `ambiguous`: questions where two tools are plausible (tests disambiguation)

**Corpus entry structure:**
```json
{
  "case_id": "cairn_list_acts_basic",
  "tool_name": "cairn_list_acts",
  "question_template": "What are my current Acts in The Play?",
  "variant": "basic",
  "expected_tool": "cairn_list_acts",
  "expected_args_schema": null,
  "notes": "Canonical question for list_acts"
}
```

For tools with required arguments, `expected_args_schema` contains a JSON Schema fragment
describing acceptable argument values:
```json
{
  "case_id": "cairn_create_act_basic",
  "tool_name": "cairn_create_act",
  "question_template": "Create a new Act called 'Health'",
  "variant": "basic",
  "expected_tool": "cairn_create_act",
  "expected_args_schema": {
    "required": ["title"],
    "properties": {
      "title": {"type": "string", "minLength": 1}
    }
  },
  "notes": "Basic create; title must be non-empty string"
}
```

**Persona variation** is not stored in corpus.json — it is generated at run time by
`corpus.py` using the same `STYLE` dictionary already in `tools/harness/question_generator.py`.
Each `question_template` becomes 12 persona-specific prompts (one per profile), multiplying
the corpus cases by 12. This keeps the corpus.json compact and maintainable.

**Estimated corpus size at launch:**
- 36 tools × ~3 variants/tool = ~108 base cases
- ×12 personas = ~1,296 total (run × case × persona) per model

## Corpus Loader

**File:** `Cairn/benchmarks/corpus.py`

```python
from dataclasses import dataclass
from pathlib import Path
import json

CORPUS_PATH = Path(__file__).parent / "corpus.json"

@dataclass
class TestCase:
    case_id: str
    tool_name: str
    question_template: str
    variant: str
    expected_tool: str
    expected_args_schema: dict | None
    notes: str | None

def load_corpus(
    tool_name: str | None = None,
    variant: str | None = None,
    corpus_file: Path | None = None,
) -> list[TestCase]:
    """Load and optionally filter test cases."""
    ...

def load_persona_profiles(profiles_dir: Path) -> list[dict]:
    """Load the 12 persona profiles from tools/test_profiles/."""
    ...

def expand_with_personas(
    cases: list[TestCase],
    profiles: list[dict],
) -> list[tuple[TestCase, dict, str]]:
    """Return (case, profile, styled_prompt) triples for every combination."""
    ...
```

The `expand_with_personas()` function applies the personality `STYLE` functions from
`question_generator.py` to each `question_template`, producing one prompt per persona.
This function should be imported from or reference the existing `STYLE` dict in
`tools/harness/question_generator.py` to avoid duplication.

## Runner Architecture

**File:** `Cairn/benchmarks/runner.py`

The runner must exercise the full Cairn MCP tool pipeline, not just the LLM. It uses the same
entry point as the existing harness (`ChatAgent.respond()`) with the same mock Thunderbird
injection pattern.

```python
class BenchmarkRunner:
    def __init__(
        self,
        model_name: str,
        tool_filter: str | None = None,   # restrict to one tool
        variant_filter: str | None = None, # restrict to one variant
        resume: bool = False,
        db_path: str | None = None,
        ollama_url: str | None = None,
        timeout: int = 120,
        anthropic_key: str | None = None,
    ) -> None: ...

    def run(self) -> str:
        """Run benchmark; return run_uuid."""
        ...
```

**Per-case execution sequence:**
1. Load the profile's `talkingrock.db` into a temp copy (isolation)
2. Set `TALKINGROCK_DATA_DIR` and `TALKINGROCK_OLLAMA_MODEL` env vars
3. Inject mock Thunderbird via `install_mock(tmp_db)`
4. Construct `ChatAgent(db=db)` and `ConsciousnessObserver`
5. Call `agent.respond(styled_prompt, agent_type="cairn")`
6. If `response.pending_approval_id`, re-call with `force_approve=True`
7. Extract from `ConsciousnessObserver` events:
   - `TOOL_CALL_START.metadata["tool"]` → `tool_selected`
   - `TOOL_CALL_START.metadata["args"]` → `tool_args`
   - `TOOL_CALL_COMPLETE` presence → `tool_execution_ok`
8. Compute scoring: `tool_match`, `args_match`, `execution_success`
9. Record to `benchmark_results`

**Token capture:** Wrap the Ollama provider with an instrumented variant that captures
`tokens_prompt` and `tokens_completion` from Ollama's native response metadata. Use the same
`InstrumentedOllamaProvider` pattern as in `ReOS/benchmarks/instrumented_provider.py` — check
if one already exists in Cairn providers, and if not, create `benchmarks/instrumented_provider.py`
as a thin wrapper.

## Matching and Scoring

**File:** `Cairn/benchmarks/matching.py`

Four scoring functions, each returns `int` (0 or 1):

```python
def tool_match(actual: str | None, expected: str) -> int:
    """1 if the tool selected matches the expected tool exactly."""
    return 1 if actual == expected else 0

def args_match(actual_args: dict | None, expected_schema: dict | None) -> int:
    """1 if actual args satisfy expected_args_schema.

    - If expected_schema is None, always returns 1 (no args constraint).
    - If actual_args is None but schema requires fields, returns 0.
    - Uses jsonschema.validate() for schema check; returns 0 on ValidationError.
    """
    ...

def execution_success(tool_execution_ok: int | None, tool_error: str | None) -> int:
    """1 if tool ran and produced no error."""
    return 1 if tool_execution_ok == 1 and not tool_error else 0

def response_quality_heuristic(response_text: str | None, expected_tool: str) -> str:
    """Heuristic quality label: 'good' | 'partial' | 'wrong'.

    Simple checks only:
    - 'wrong' if response_text is None or empty
    - 'wrong' if response contains known error patterns ('Error:', 'failed', 'unknown tool')
    - 'good' otherwise (conservative default — human review fills gaps)
    """
    ...
```

This is deliberately simpler than ReOS's 7-function matching suite. Cairn's correctness
criterion is binary: right tool or wrong tool. The args schema check adds a second dimension.
Semantic similarity matching (cosine, embeddings) is deferred until there is a reason to need it.

## Anthropic Provider

**File:** `Cairn/benchmarks/anthropic_provider.py`

Copy verbatim from `/home/kellogg/dev/ReOS/benchmarks/anthropic_provider.py`. The file has no
ReOS-specific dependencies — it uses the `anthropic` SDK directly and implements `chat_text()`.
The only adaptation needed: the Cairn runner does not call `chat_text()` directly (it exercises
the full `ChatAgent` stack), so the Anthropic provider is wired at the model-selection level
rather than the call level. The runner must detect `_is_anthropic_model(model_name)` and
configure the agent's provider factory to use `AnthropicProvider` instead of Ollama.

**Open question for implementer:** Cairn's `providers/factory.py` is documented as Ollama-only.
Verify whether the provider factory accepts an override, or whether the runner must monkey-patch
`get_provider()` for Anthropic runs.

## Models Matrix

**File:** `Cairn/benchmarks/models.py`

Copy from `ReOS/benchmarks/models.py` without modification. The 16 Ollama models + Claude Sonnet
API entry are identical. The `MODEL_MATRIX` list is the source of truth for `--all-models` CLI runs.

## CLI

**File:** `Cairn/benchmarks/__main__.py`

```
python -m benchmarks run --model qwen2.5:7b
python -m benchmarks run --model qwen2.5:7b --tool cairn_list_acts
python -m benchmarks run --all-models
python -m benchmarks run --model qwen2.5:7b --resume
python -m benchmarks analyze [--model MODEL]
python -m benchmarks list-tools
python -m benchmarks list-cases [--tool TOOL] [--variant VARIANT]
python -m benchmarks export --output FILE.csv
```

Key CLI additions versus ReOS:
- `--tool TOOL` — restrict run to cases for one tool (useful for iterative development)
- `--variant VARIANT` — restrict to one variant type
- `list-tools` — show the post-purge tool inventory with case counts
- No `--no-context` and `--no-rag` flags (Cairn doesn't have equivalent RAG toggle)

## What to Reuse vs Build New

| Component | Reuse | Build new |
|-----------|-------|-----------|
| Persona profiles (`tools/test_profiles/`) | Yes, unchanged | — |
| Mock Thunderbird injection (`tools/harness/mock_thunderbird.py`) | Yes, import directly | — |
| Personality style functions (`tools/harness/question_generator.py` `STYLE` dict) | Import directly | — |
| ConsciousnessObserver event extraction | Copy pattern from `tools/harness/runner.py` | — |
| `tools/harness/recorder.py` schema | No — different schema needed | New `benchmarks/db.py` |
| `tools/harness/analysis.py` | No — different query structure | New `benchmarks/analysis.py` |
| `tools/harness/question_generator.py` templates | No — need tool-specific questions | New `benchmarks/corpus.json` |
| ReOS `benchmarks/db.py` | Structural reference only | New schema for Cairn |
| ReOS `benchmarks/runner.py` | Structural reference only | New runner with MCP pipeline |
| ReOS `benchmarks/anthropic_provider.py` | Copy verbatim | — |
| ReOS `benchmarks/models.py` | Copy verbatim | — |
| ReOS `benchmarks/__main__.py` | Structural reference | New CLI |

## Migration Path from Existing Harness

The existing `tools/harness/` and `tools/harness_results/harness.db` are **not migrated**.
They remain operational and independent. The two systems serve different questions:

| Harness (`tools/harness/`) | Benchmark (`benchmarks/`) |
|---------------------------|--------------------------|
| "Does the model respond coherently?" | "Does the model select the correct tool?" |
| Category-based questions (8 types) | Tool-specific questions (36 tools × variants) |
| 12 personas × 8 questions = 96 per model | 36 tools × 3 variants × 12 personas = 1,296 per model |
| No expected tool specified | Expected tool + args schema per case |
| `harness.db` results | `cairn_benchmark.db` results |

The only shared infrastructure is the profiles directory and the mock Thunderbird bridge. Both
systems import these independently.

## Build Order

1. **`benchmarks/db.py`** — schema first; everything else depends on it
2. **`benchmarks/corpus.py`** — `TestCase` dataclass and loader
3. **`benchmarks/corpus.json`** — first 10 tools' cases (~30 entries) as bootstrap
4. **`benchmarks/matching.py`** — scoring functions
5. **`benchmarks/models.py`** — copy from ReOS
6. **`benchmarks/anthropic_provider.py`** — copy from ReOS
7. **`benchmarks/runner.py`** — wire together corpus + matching + agent invocation
8. **`benchmarks/__main__.py`** — CLI wiring
9. **Smoke test:** `python -m benchmarks run --model qwen2.5:3b --tool cairn_list_acts`
10. **Corpus expansion** — fill in remaining 26 tools' cases

Step 9 (smoke test on one tool × one model) is the critical integration checkpoint. It proves
the pipeline end-to-end before investing time in corpus expansion.

## Files to Create

| File | Source / Action |
|------|----------------|
| `Cairn/benchmarks/__init__.py` | Create empty |
| `Cairn/benchmarks/db.py` | Build new (schema above) |
| `Cairn/benchmarks/corpus.py` | Build new (dataclass + loader) |
| `Cairn/benchmarks/corpus.json` | Build new (bootstrap with ~30 cases) |
| `Cairn/benchmarks/matching.py` | Build new (4 scoring functions) |
| `Cairn/benchmarks/models.py` | Copy from `ReOS/benchmarks/models.py` |
| `Cairn/benchmarks/anthropic_provider.py` | Copy from `ReOS/benchmarks/anthropic_provider.py` |
| `Cairn/benchmarks/runner.py` | Build new (Cairn-specific) |
| `Cairn/benchmarks/__main__.py` | Build new (Cairn CLI) |

**No changes** to existing `tools/harness/` files.

## Risks and Mitigations

**Risk: Provider factory is Ollama-only; Anthropic provider cannot be injected**
Evidence: `CLAUDE.md` states "Cairn uses Ollama exclusively for local inference" and
`providers/factory.py` creates Ollama provider only.
Mitigation: The implementer must check whether `factory.py` accepts a provider override
before wiring Anthropic. If not, the runner may need to monkey-patch the factory for
Anthropic runs — same pattern used in ReOS's benchmark runner. Document this clearly in
runner.py with a TODO if deferring.

**Risk: ConsciousnessObserver does not fire TOOL_CALL_START for all tool invocations**
Evidence: The existing harness (`tools/harness/runner.py`) already uses this extraction
pattern successfully for `tool_called` and `tool_args`. If a tool call bypasses the observer,
the result will show `tool_selected = NULL` with `execution_success = 0`, which is correctly
recorded as a failure.

**Risk: Persona styling produces prompts that are too ambiguous for reliable tool selection**
Some personality styles (terse "Priorities?", vague "stuff") are deliberately adversarial.
These will produce lower `tool_match_pct` scores — which is informative, not an error.
The corpus design must clearly label variant="off_topic" or variant="ambiguous" for these
cases so analysis can filter them separately.

**Risk: 1,296 cases per model × 17 models = 22,032 total invocations**
At ~8 seconds each, full-matrix run is ~49 hours. This is a long-running operation.
Mitigation: The `--tool` and `--variant` flags allow targeted runs. The `--resume` flag
allows interrupted runs to be restarted. Production use will be targeted (one tool at a
time) until the corpus is validated, then `--all-models` for a periodic full run.

**Risk: Corpus.json drifts from the actual post-purge tool inventory**
If tools are added or renamed, `case_id` values remain in the database as orphan references.
Mitigation: The `list-tools` CLI command compares `corpus.json` against the live
`list_tools()` output and warns about mismatches. Document this in the corpus README.

## Testing Strategy

1. **Unit tests for `matching.py`:** Test each scoring function with known inputs. No LLM
   required. Create `tests/benchmarks/test_matching.py`.

2. **Unit tests for `corpus.py`:** Test `load_corpus()` with a minimal fixture corpus JSON.
   Test `expand_with_personas()` with 2 profiles and 2 cases. No LLM required.
   Create `tests/benchmarks/test_corpus.py`.

3. **Integration smoke test (manual):** Run one case on one tool for one model:
   `python -m benchmarks run --model qwen2.5:3b --tool cairn_list_acts`
   Verify a row appears in `cairn_benchmark.db` with expected columns populated.

The existing `tests/` tree should not be modified for benchmark tests. Create
`tests/benchmarks/` as a subdirectory (it already exists at `tests/integration/` for
the integration tests pattern).

## Definition of Done

- [ ] `Cairn/benchmarks/` directory exists with all 9 files
- [ ] `python -m benchmarks list-tools` prints the 36 post-purge tools with case counts
- [ ] `python -m benchmarks list-cases` shows all corpus entries with case_ids
- [ ] `python -m benchmarks run --model qwen2.5:3b --tool cairn_list_acts` completes
  without error and writes a row to `cairn_benchmark.db`
- [ ] `python -m benchmarks analyze --model qwen2.5:3b` prints a summary table
- [ ] `tests/benchmarks/test_matching.py` passes
- [ ] `tests/benchmarks/test_corpus.py` passes
- [ ] Corpus contains at least 3 variants for each of the 36 post-purge tools (108 base cases)
- [ ] `resume` flag correctly skips already-completed (run, case, persona) triples
- [ ] `anthropic_provider.py` is importable and raises a clear error if `anthropic` SDK
  is not installed

---

# Confidence Assessment

**Task 1 (Tool Purge):** High confidence. All affected lines were read directly. The undo
reverse-dispatch complication is the only non-obvious risk and it is well-understood. Test
impact is limited to four files with straightforward string substitutions.

**Task 2 (Benchmark System):** Medium-high confidence on architecture; medium confidence on
the Anthropic provider wiring. The existing harness provides a working template for the runner
pattern. The main unknown is whether Cairn's provider factory accepts an override injection
for Anthropic runs — this must be verified before implementing the Anthropic path in the runner.

# Assumptions Requiring Validation Before Implementation

1. **Anthropic provider injection:** Verify that `src/cairn/providers/factory.py`'s
   `get_provider()` function can be made to return an Anthropic provider for benchmark runs
   without modifying production code. If not, document the monkey-patch approach.

2. **ConsciousnessObserver singleton:** Confirm the singleton is reset correctly between
   profile runs. The existing harness calls `observer.start_session()` / `observer.end_session()`
   per question — verify this is sufficient to prevent events leaking between test cases when
   a new `ChatAgent` is constructed per profile.

3. **Post-purge tool count:** The plan states 36 surviving tools. Verify by running
   `PYTHONPATH="src" python -c "from cairn.mcp_tools import list_tools; print(len(list_tools()))"`
   before and after the purge — before should be 56, after should be 36.
