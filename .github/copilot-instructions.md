## Copilot Instructions for ReOS

### Vision: Bifocal Interface (Build in VSCode, Reflect in ReOS)

ReOS is a **companion attention system** for developers. You work in VSCode (primary workspace), and ReOS observes your patterns + offers wisdom:

```
VSCode (Primary: Build)          ReOS (Companion: Reflect)
─────────────────────────────    ──────────────────────────
User coding, switching files  →  Observes file focus, git
                                 commits, time patterns
                                 ↓
                                 Real-time metrics: "8 context
                                 switches in 5 min"
                                 ↓
                                 Compassionate prompt: "Settle
                                 into one file? Or is this
                                 exploration?"
                                 ↓
User clicks ReOS insight  ←  ──  Reflection panel opens with
                                 full reasoning, session data,
                                 asking "What was your intention?"
```

**Not**: A chat app you alt-tab to. **But**: A companion that notices your work patterns and reflects back.

### Current Architecture (M0 → M1 Phase)

**Tech Stack**: Python 3.12, PySide6 (ReOS companion GUI), FastAPI (event service), Ollama (local LLM), SQLite (local persistence), JavaScript (VSCode extension)

**Key Components**:
1. **VSCode Extension** (Primary Observer)
   - Tracks: active file, time in file, git commits, project context
   - Publishes to SQLite → ReOS consumes
   - Silent by default; minimal status bar UI
   - File: `vscode-extension/extension.js`

2. **ReOS Desktop App** (Companion + Reflection)
   - 3-pane layout: nav (VSCode projects) | dashboard/chat | inspection (reasoning)
   - Shows real-time attention metrics
   - Proactive prompts: "You're fragmented. Settle or explore?"
   - Files: `src/reos/gui/main_window.py`, `src/reos/gui/__init__.py`

3. **SQLite Core** (Single Source of Truth)
   - Events from VSCode → stored here
   - Sessions, classifications, audit_log all derived from events
   - File: `src/reos/db.py`

4. **Command Registry** (Reasoning About Attention)
   - Commands: reflect_recent, inspect_session, list_events, note
   - NOT generic tools; these introspect VSCode-derived attention data
   - File: `src/reos/commands.py`

5. **Ollama Layer** (Local LLM)
   - All reasoning local; no cloud calls
   - System prompt includes attention patterns derived from VSCode events
   - File: `src/reos/ollama.py`

### Design Principles

- **Bifocal Workflow**: VSCode is primary (user's flow stays unbroken); ReOS is always-on companion.
- **Observation Over Prescription**: ReOS notices what you're doing, doesn't tell you what to do.
- **Attention as Sacred**: Reflections honor labor—never shame, guilt, or moral judgment.
- **Checks & Balances**: Proactive nudges ("You've been deep for 2 hrs—water break?"), not punishments.
- **Local-First**: All data SQLite; no sync to cloud without explicit consent.
- **Transparent Reasoning**: Every ReOS insight shows its full reasoning trail; user can inspect.

### When Working on ReOS Code

**Before Writing Code**:
1. Check the charter ([ReOS_charter.md](../ReOS_charter.md)) — does this serve "protect, reflect, return attention"?
2. Ask: "Does this strengthen the VSCode+ReOS bifocal system, or create distraction?"
3. If adding data collection: "Is this metadata-only? Does user consent?"
4. If adding UI/language: "Is this compassionate, non-prescriptive, non-judgmental?"

**Architecture Principles**:
- VSCode extension is the **observer** (collect data).
- ReOS app is the **companion** (reflect, offer wisdom).
- Bifocal means: VSCode should not be disrupted; ReOS prompts should be wise, not noisy.
- All attention patterns derived from VSCode events (don't make up data).

**Code Style & Validation**:
- `ruff check` (100-char lines, sorted imports, PEP8)
- `mypy src/ --ignore-missing-imports` (PySide6 stubs are sparse)
- `pytest` before commit (5 tests must pass)
- Use `collections.abc.Callable`, not `typing.Callable`
- Add docstrings and type hints to all public functions

**Language & Tone**:
- Avoid: "productivity", "focus mode", "streaks", "good/bad day", "distracted"
- Use: "fragmented/coherent", "revolution/evolution", "your attention was", "what's your intention?"
- Examples:
  - ✗ "You were distracted."
  - ✓ "7 file switches in 5 minutes. Was this creative exploration or fragmentation?"
  - ✗ "Great productivity streak!"
  - ✓ "You've been in this codebase for 3 hours. Deep work or dwelling?"

**Local Data & Git Safety**:
- All data → `.reos-data/` (git-ignored)
- `.gitignore` includes: `*.sqlite*`, `*.db`, `.venv/`, `__pycache__/`, `.reos-data/`
- Never commit DB files, only schemas in code
- Update `.gitignore` when adding new local data types

**Database Work**:
- Schema in `src/reos/db.py` (events, sessions, classifications, audit_log)
- All tables have `created_at`, `ingested_at` for audit trail
- Use `Database.get_db()` singleton for safe access
- Events table: populated by VSCode extension; cleaned/normalized in SQLite
- Fresh DB per test (avoid threading issues)

**VSCode Extension Work**:
- JavaScript; connects to ReOS FastAPI service
- Observes: file focus (`onDidChangeActiveTextEditor`), git (shell command), time
- Publishes to SQLite via `/events` endpoint → no user interruption
- Status bar: optional "ReOS listening" indicator + toggle mirroring on/off
- NO keystroke logging; NO content capture; metadata only

**ReOS Desktop App (PySide6)**:
- Left nav pane: VSCode projects/sessions (clickable, load context)
- Center: real-time attention dashboard + reflection chat
- Right inspection pane: click on insight → show reasoning (system prompt + LLM output + tools called)
- Proactive prompts: "8 switches in 5 min—settle on one file?" (compassionate, not demanding)
- No gamified UI; no streaks, scores, or "levels"

**Attention Classification** (Coming):
- Track context switching from VSCode file events
- Detect "frayed mind" (rapid switches + shallow engagement + no-break periods)
- Classify periods as: coherent (deep focus) vs fragmented (scattered attention)
- Classify as: revolution (disruptive change) vs evolution (gradual integration)
- Use parameterized heuristics (explainable), not opaque ML
- Reflect without judgment: "This period shows high switching" not "You were distracted"

**Checks & Balances System** (Coming):
- Real-time detection: "8 context switches in 5 minutes"
- Proactive prompts: "Settle into one file? Or is this creative exploration?"
- Intention checks: "You've been on this file for 30 min—understanding emerging?"
- Rest prompts: "Deep focus for 2 hours—good. Water break?"
- All prompts are compassionate, never shaming

**Non-Goals** (flag if requested):
- ❌ Task managers or todo lists
- ❌ Gamified streaks, quotas, productivity scores
- ❌ Engagement loops or dopamine-driven UX
- ❌ Cloud storage without explicit consent
- ❌ Keystroke logging or message-body parsing
- ❌ "Good/bad day" moral framing
- ❌ Corporate surveillance

### Typical Workflow (Vision)

```
1. User opens VSCode + ReOS side-by-side
2. VSCode extension silently observes:
   - file-focus events (via onDidChangeActiveTextEditor)
   - git commits/branch changes (via shell command)
   - time spent in each file
   → all published to SQLite

3. ReOS dashboard shows real-time:
   - Current project + session
   - Files open + time in each
   - Context switch count
   - Fragmentation score (derived from switching pattern)

4. ReOS detects pattern (e.g., "8 switches in 5 min"):
   - Proactive prompt appears: "8 context switches in 5 minutes.
     Settle into one file? Or is this creative exploration?"

5. User sees prompt, reflects:
   - Clicks "This is exploration" → stored as user reflection
   - Or ignores it → ReOS learns this pattern

6. User wants deeper reflection:
   - Clicks ReOS prompt/insight
   - Reflection panel opens: "Here's your last 2 hours..."
   - Shows reasoning trace (system prompt + LLM output + tools)
   - Asks: "What was your intention with that switching?"

7. User answers reflection question:
   - Stored in SQLite (audit_log)
   - ReOS learns: "Ah, that switching WAS exploration, not fragmentation"
   - Next similar pattern: "Remember last time? You were exploring."

Result: VSCode stays primary; ReOS is wise companion offering patterns,
        not interruption. User feels seen and supported, not judged.
```

### Running & Testing

```bash
# VSCode Extension
cd vscode-extension/
npm install
npm run watch  # Watches for changes; ready to debug in VSCode

# ReOS Desktop App
python -m reos.gui          # Launch app
reos-gui                     # (same, via script entry)

# FastAPI Service (feeds events into SQLite)
python -m reos.app          # Runs on http://127.0.0.1:8010

# Tests
pytest                       # Run test suite

# Lint + Type Check
ruff check src/ tests/       # Linting
mypy src/ --ignore-missing-imports  # Type checking
```

### Key Files to Know

| File | Purpose | Team |
|------|---------|------|
| `vscode-extension/extension.js` | VSCode observer (file focus, git) | Extension |
| `src/reos/gui/main_window.py` | ReOS 3-pane layout | GUI |
| `src/reos/commands.py` | Attention introspection commands | Core |
| `src/reos/db.py` | SQLite schema (events, sessions, classifications) | Core |
| `src/reos/ollama.py` | Local LLM client | Core |
| `src/reos/app.py` | FastAPI service (event ingestion) | Core |
| `tests/test_db.py` | SQLite tests | Tests |
| `docs/tech-roadmap.md` | Architecture & milestones | Planning |
| `ReOS_charter.md` | Core values & principles | Vision |

### Before You Ask for Help

- Is your question about a principle → check the charter first
- Is it about bifocal architecture → ask: "Does this keep VSCode unbroken while ReOS is wise?"
- Is it about language → ask: "Is this compassionate and non-prescriptive?"
- Is it about data → ask: "Is this metadata-only? Does user consent?"
- Is it about code style → run ruff, mypy, pytest

**Guiding Question**: "Does this help the user choose how to spend their attention, or does it try to control their attention?"

If the latter, you're off-vision. Attention is labor and sacred. We protect it, reflect it; we don't optimize it.

When in doubt, re-read [ReOS_charter.md](../ReOS_charter.md) and ask for clarification before proceeding.
