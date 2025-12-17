## ReOS Technical Roadmap (Python, Local-First, VSCode Companion + Life Reflection)

### Scope and Intent

ReOS is a **bifocal intelligence system**:

- **VSCode Extension (Front-end)**: Silently observes your development work—file focus, git activity, context switching, time patterns. No interruption, just awareness.
- **ReOS Desktop App (Companion)**: Sits alongside VSCode as a reflection + reasoning tool. Shows real-time attention metrics, proactive checks/balances ("You've switched 8 times in 5 min—settle?"), and deep reflections on your work patterns.
- **Unified Workflow**: Build in VSCode (primary workspace), reflect in ReOS (companion). Data flows from VSCode → SQLite → ReOS reasoning + UI.
- **Evolution**: Starts as VSCode dev tool, expands into broader life/attention management system.

**Core Philosophy**: Attention is labor and sacred. ReOS protects it by observing with clarity, reflecting with compassion, and returning agency to the user.

### Guardrails from the Charter

- No hidden data capture; require explicit consent for any data leaving the machine.
- Language: reflective, non-moral. Report fragmentation/coherence, not productivity scores.
- Data boundaries: default to local storage (SQLite). No file content capture; only metadata (filename, time, git commit).
- Transparency: every AI-generated output includes its "inspection trail" (prompt sent, model used, tool calls made, confidence, alternatives considered).
- Checks & Balances: proactive, compassionate nudges. Not commands, not guilt—just "notice this" and "what's your intention?"

### Assumptions

- OS: Linux; dual-window workflow (VSCode + ReOS).
- Language: Python 3.12.3 (backend/reasoning); JavaScript (VSCode extension); PySide6 for ReOS UI.
- Ollama runs locally; model user-selected.
- VSCode extension is **primary data collector**; ReOS app is **companion + reflection layer**.
- All events flow through SQLite; no direct cloud calls.

### Architecture Direction (Bifocal, Observation-Driven)

**VSCode Extension** (Observer):
- Tracks active file, time spent, git commits, terminal commands (optional).
- Publishes events to SQLite → no user interruption.
- Minimal UI: optional status bar to show ReOS is listening + toggle mirroring.

**ReOS Desktop App** (Companion):
- Left nav: VSCode projects + sessions (clickable to load context).
- Center: real-time attention dashboard + reflection chat.
- Right inspection pane: click on any insight → see full reasoning trail.
- Proactive prompts: "8 context switches in 5 min—break or intention check?"

**SQLite Core**:
- Events table: file focus, git, time, project context (derived from VSCode data).
- Sessions table: project-aware work periods.
- Classifications table: fragmentation/coherence, revolution/evolution.
- Audit_log table: all AI reasoning + user reflections.

**LLM Layer**:
- Command registry: reflect_recent, inspect_session, list_events, note (tied to VSCode data, not generic).
- System prompt includes attention patterns derived from VSCode events.
- Reasoning is always transparent and auditable.

**Interfaces**:
- Primary: ReOS desktop app (reflection + checks/balances).
- Secondary: VSCode status bar (quick alerts, optional).
- Future: CLI reflect command; life graph visualization; broader attention tracking (email, browser, OS).

### MVP Thin Slice (Bifocal Workflow)

1. **VSCode Extension Enhancement**: Real-time file focus + git event tracking → SQLite.
2. **ReOS Dashboard**: Display real-time VSCode context (active project, file history, time).
3. **Attention Metrics**: Calculate fragmentation score from VSCode events; display in real-time.
4. **Proactive Nudges**: Detect frayed mind (8 switches in 5 min) → show compassionate prompt.
5. **Reflection Chat**: Click on prompt → ReOS opens reflection panel with full reasoning trail.

### Incremental Milestones

- **M0 (Completed)**: FastAPI scaffold, JSONL storage, Ollama health check, tool registry, VSCode extension basic event collection.
- **M1 (In Progress)**: SQLite migration, ReOS desktop app with 3-pane layout, command registry scaffolded.
- **M1b (Next)**: VSCode extension live event streaming → SQLite; ReOS nav pane populated from VSCode projects.
- **M2 (Real-time Attention)**: Fragmentation detection; attention dashboard; proactive "checks & balances" prompts.
- **M3 (Reflection & Reasoning)**: Ollama integration wired to VSCode-derived attention data; inspection pane working.
- **M4 (Classification)**: Revolution/evolution, coherence/fragmentation classification; reflections learned + remembered.
- **M5 (Life Expansion)**: Optional: Email (Thunderbird), browser, OS integration; broader life graph + attention management.

### Development Workflow

- Tooling: ruff, mypy, pytest (already set up).
- Extensions: `npm install` in `vscode-extension/`; `npm run watch` for dev.
- Backend: `python -m reos.gui` (desktop app), `python -m reos.app` (service), `python -m pytest` (tests).
- Dependencies: PySide6, Ollama (local), Node.js (for extension dev).

### Key Design Decisions

1. **VSCode Extension as Primary Observer**: Don't ask users to manually input their work; observe it passively.
2. **No Interruption UI**: VSCode extension is silent by default (status bar only); ReOS app shows insights on demand.
3. **Attention Metrics Come From VSCode**: Don't make up fragmentation/coherence; derive from real file-switching patterns.
4. **Compassion Over Guilt**: "You've been switching a lot—what's your intention?" not "You were distracted."
5. **Data Stays Local**: All SQLite, no cloud sync for core MVP.

### Open Questions

1. Should ReOS extend into VSCode UI (sidebar panel)? Or remain separate window?
2. How sensitive should fragmentation detection be? (8 switches/5min? 15/10min?)
3. Should user reflections ("This was creative exploration") be saved as training data for future classifications?
4. Email/browser integration: opt-in or opt-out by default?
