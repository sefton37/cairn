## ReOS Technical Roadmap (Python, Local-First, Desktop App)

### Scope and Intent
- Build a **local, standalone desktop application** (PySide6/Qt) as the primary ReOS interface—the "face" of the attention kernel.
- Desktop UI: **transparent AI reasoning**. Every chat turn shows the LLM's reasoning, MCP tool calls, and inspection trails so nothing is hidden.
- Backend: local SQLite for persistence, local Ollama for LLM inference, command interpreter so the LLM can reason about available MCP tools instead of guessing.
- MVP focus: chat-based interface where the user talks to ReOS about their attention/project, and ReOS reasons through decisions using a visible command system.
- Avoid task scoring, streaks, or engagement loops; all reflections are descriptive and explainable.
- Keep the FastAPI service optional (for VS Code bridge, headless mode, future integrations).

### Guardrails from the Charter
- No hidden data capture; require explicit consent for any data leaving the machine.
- Language: reflective, non-moral. Report fragmentation/coherence, not productivity scores.
- Data boundaries: default to local storage (SQLite). No message-body capture by default; only metadata needed for attention modeling. All AI reasoning is auditable/inspectable.
- Transparency: every AI-generated output includes its "inspection trail" (prompt sent, model used, tool calls made, confidence, alternatives considered).

### Assumptions
- OS: Linux; primary interface is now a desktop app (1080p Qt window).
- Language: Python 3.12.3; PySide6 for the UI.
- Ollama runs locally; model can be user-selected.
- MCP tool system is central: the LLM reasons about available tools and calls them declaratively (not guessing).

### Architecture Direction (explainable, inspectable)
- **Desktop App (PySide6/Qt)**: 1080p window with left nav pane, center chat, right inspection pane. Every AI output has a "summary" + drill-down.
- **Command Interpreter**: Registry of available commands/MCP tools that the LLM can introspect. LLM reasons about which tools to use, then we execute them.
- **Storage**: local SQLite (events, sessions, classifications, audit_log).
- **LLM layer**: local Ollama + thin client. LLM gets a "system prompt" that includes the command registry.
- **Event collectors (background)**: VS Code extension (optional), optional Git/focus watchers.
- **Interfaces**: Desktop chat app (primary); FastAPI service (optional); CLI (future).
- **Privacy switches**: explicit user toggles; all data local by default.

### MVP Thin Slice (Desktop-First)
1) Desktop app scaffold (PySide6): 1080p window, left nav pane (empty for now), center chat input/output, right inspection pane.
2) Command registry: define available commands/tools in a structured format; LLM can introspect and reason.
3) Ollama integration: send a chat message + command registry as context; parse LLM response for tool calls; execute and show results.
4) Chat history: store messages + tool calls + results in SQLite for replay/audit.
5) Inspection pane: click on any AI message to see the full reasoning trail (system prompt, LLM reasoning, tools called, results).

### Incremental Milestones
- **M1 (Desktop Scaffold + Chat)**: PySide6 window, basic chat I/O, Ollama integration wired.
- **M2 (Command Interpreter)**: Define command registry, LLM tool calling, inspection pane working.
- **M3 (Persistence)**: Chat history → SQLite, replay/audit features.
- **M4 (Attention Classifiers)**: Integrate sessionization + fragmentation scoring into chat context.
- **M5 (VS Code Bridge Sync)**: Optional: VS Code extension events → SQLite → available in chat context.

### Development Workflow
- Tooling: ruff, mypy, pytest (already set up).
- Commands: `python -m reos.gui` (desktop app), `python -m reos` (service, optional), `python -m pytest` (tests).
- New dependency: `PySide6>=6.7.0`.

### Open Questions
- Model selection UI in settings, or hardcoded initially?
- Chat persistence: unlimited history, or rolling window?
- Inspection pane: JSON view, pretty-printed, or custom formatter?
