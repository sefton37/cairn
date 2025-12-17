## Copilot Instructions for ReOS

### Current Architecture (M0 → M1 Phase)

**Tech Stack**: Python 3.12, PySide6 (desktop GUI), FastAPI (optional service), Ollama (local LLM), SQLite (local persistence)

**Project Structure**:
- `src/reos/gui/` → PySide6 desktop app (primary interface): 3-pane layout (nav | chat | inspection)
- `src/reos/commands.py` → Command registry for LLM introspection
- `src/reos/db.py` → SQLite schema (events, sessions, classifications, audit_log)
- `src/reos/app.py` → FastAPI service (optional, feeds events into SQLite)
- `src/reos/ollama.py` → Local Ollama client (no content capture)
- `.reos-data/` → Local data directory (git-ignored, user-owned)

**What's Implemented**:
- ✓ M0: FastAPI scaffold, JSONL event storage, Ollama health checks, tool registry
- ✓ M1a: SQLite migration (4-table schema), storage layer, comprehensive tests (5/5 passing)
- ✓ Desktop app scaffold: 1080p window, resizable 3-pane layout, placeholder chat
- ✓ Command registry: 4 commands (reflect_recent, inspect_session, list_events, note), JSON schema generator
- ✓ Code quality: ruff lint (0 violations), mypy checks, pytest suite

### Design Principles (from charter)

- **Local-first, Always**: Ollama runs locally. No cloud calls except explicit, user-consented integration.
- **Transparent AI Reasoning**: Every LLM output includes inspection trail (system prompt, input, tool calls, results). User clicks AI message → see full reasoning.
- **Command Interpreter**: LLM receives serialized command registry. AI reasons about tools instead of guessing blindly.
- **Metadata-Only Capture**: No keystroke logging. Events store: timestamp, app, window title, session metadata. Content never captured by default.
- **Explainable, Not Prescriptive**: Classifications are descriptive, not directive. No shame language, no productivity scores.
- **Attention as Labor**: Reflect patterns with neutral, compassionate tone.

### When Working on ReOS Code

**Before Writing Code**:
1. Check [ReOS_charter.md](../ReOS_charter.md) — is this aligned with "protect, reflect, return attention"?
2. For UI/chat/LLM: ensure it's in the chain (event → classification → reasoning → inspection)
3. For storage/network/ML: get explicit user approval on scope and data boundaries

**Code Style & Validation**:
- `ruff check` (100-char lines, sorted imports, PEP8)
- `mypy src/ --ignore-missing-imports` (PySide6 stubs are sparse)
- `pytest` before commit (5 tests must pass)
- Use `collections.abc.Callable`, not `typing.Callable`
- Add docstrings and type hints to all public functions

**Local Data & Git Safety**:
- All data → `.reos-data/` (git-ignored)
- `.gitignore` includes: `*.sqlite*`, `*.db`, `.venv/`, `__pycache__/`, `.reos-data/`
- Never commit DB files, only schemas in code
- Update `.gitignore` when adding new local data types

**Database Work**:
- Schema in `src/reos/db.py` (events, sessions, classifications, audit_log)
- All tables have `created_at`, `ingested_at` for audit trail
- Use `Database.get_db()` singleton for safe access
- Fresh DB per test (avoid threading issues)

**Ollama Integration**:
- Ollama URL via env `REOS_OLLAMA_URL` (default: http://127.0.0.1:11434)
- Check `check_ollama()` before assuming models available
- System prompt includes `registry_as_json_schema()` from `src/reos/commands.py`
- Parse LLM responses for tool calls; execute and store results to audit_log
- No content streaming; only metadata and reflection prompts

**GUI Development (PySide6)**:
- 3-pane layout using QSplitter (resizable)
- Chat input → Ollama + command executor
- Inspection pane: click AI message → reasoning trace (summary → drill-down JSON)
- Store all chat + reasoning to SQLite for audit
- No gamified prompts, streaks, or "focus modes"

**Attention Classification (Future)**:
- Track context switching, time between switches
- Detect "frayed mind" (rapid switches + shallow engagement + extended no-break periods)
- Classify as revolution (disruptive) vs evolution (gradual) vs stagnation
- Classify as fragmented vs coherent
- Use parameterized heuristics, not opaque ML
- Reflect without judgment: "High switching" not "You were distracted"

**Non-Goals** (flag if requested):
- ❌ Task managers / todo lists
- ❌ Gamified streaks, quotas, productivity scores
- ❌ Engagement loops or dopamine-driven UX
- ❌ Cloud storage without explicit consent
- ❌ Content capture (keystroke logging, message parsing)
- ❌ "Good/bad day" moral framing
- ❌ Corporate surveillance

### Typical Workflow

1. User types message → MainWindow._on_send_message()
2. Message → chat display + SQLite history
3. Message → Ollama with system prompt (includes command registry)
4. LLM responds with reasoning + tool calls (JSON)
5. Command executor parses, runs handlers, captures results
6. Results + reasoning trail → audit_log
7. AI response in chat; inspection pane populated
8. Click AI message → inspection pane shows summary + full trace link

### Running & Testing

```bash
python -m reos.gui          # Launch app
reos-gui                     # (same, via script entry)
python -m reos.app          # Optional FastAPI service
pytest                       # Tests
ruff check src/ tests/       # Lint
mypy src/ --ignore-missing-imports  # Types
```

### Key Files

| File | Purpose |
|------|---------|
| `src/reos/gui/main_window.py` | 3-pane Qt layout |
| `src/reos/commands.py` | Command registry, schema |
| `src/reos/db.py` | SQLite schema & CRUD |
| `src/reos/ollama.py` | Ollama client |
| `src/reos/models.py` | Pydantic schemas |
| `tests/test_db.py` | DB tests |
| `docs/tech-roadmap.md` | Architecture |
| `ReOS_charter.md` | Principles |

When in doubt, check [ReOS_charter.md](../ReOS_charter.md) first.
