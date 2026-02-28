# Cairn (Talking Rock) Project Guide

> **See `~/.claude/CLAUDE.md` for the comprehensive workflow (Comprehension → Clarification → Planning → Execution).** This document provides Cairn-specific context only.

---

## What This Is

**Talking Rock** is a local-first personal attention minder with one agent:
- **CAIRN** — Attention minder and life organizer (1B models)

**Core philosophy:** Local inference is essentially free, enabling verification and analysis at scale that cloud services can't afford. Zero trust, local only, encrypted at rest, never phones home.

---

## Architecture Quick Reference

Read these first when working on the project:
- **[README.md](README.md)** - Mission statement, capabilities, development priorities
- **[CONVERSATION_LIFECYCLE_SPEC.md](docs/CONVERSATION_LIFECYCLE_SPEC.md)** - Conversation lifecycle, memory extraction, reasoning integration
- **[CAIRN_SIMPLIFICATION_PLAN.md](docs/archive/CAIRN_SIMPLIFICATION_PLAN.md)** - Optimization history (archived)

### Key Architectural Patterns

#### 1. Atomic Operations (3x2x3 Taxonomy)

Every user request is classified and recorded as an atomic operation:

```python
# Classification dimensions
destination_type: "stream" | "file" | "process"  # Where output goes
consumer_type: "human" | "machine"               # Who consumes result
execution_semantics: "read" | "interpret" | "execute"  # What action

# Examples
"what's next today?"    → (stream, human, interpret)
"save to notes.txt"     → (file, human, execute)
```

**Location:** `src/cairn/atomic_ops/` — processor, classifier, decomposer, executor, cairn_integration, verifiers/

#### 2. The Play (2-Tier Life Organization)

```python
Act        # Life narrative (Career, Health, Family) - months to years
  └─ Scene # Calendar event or task within the narrative

SceneStage = "planning" | "in_progress" | "awaiting_data" | "complete"
```

Philosophy: Two levels prevent obscuring responsibility in complexity. Acts answer "What narrative?" Scenes answer "When am I doing this?"

**Location:** `src/cairn/play_fs.py`, `src/cairn/play_db.py`, `src/cairn/play/` (blocks, markdown)

#### 3. CAIRN Intent Engine (4-Stage Pipeline)

```
Stage 1: Extract Intent    → Pattern matching → Category (CALENDAR, PLAY, etc.)
Stage 2: Verify Intent     → Check tool availability, build args
Stage 3: Execute Tool      → Call MCP tool with extracted args
Stage 4: Generate Response → Strictly from tool results (no hallucination)
```

**Location:** `src/cairn/cairn/intent_engine.py`

#### 4. MCP Tools System

Tools organized by category:
- `cairn_*` — The Play CRUD, calendar, contacts, knowledge (CairnToolHandler)

**Location:** `src/cairn/mcp_tools.py` (tool registry), `src/cairn/cairn/mcp_tools.py` (tool implementations)

#### 5. Conversation Lifecycle & Memory Architecture

```
Conversation States: active → ready-to-close → compressing → archived

Compression Pipeline (4-stage local inference):
  1. Entity Extraction    → People, tasks, decisions, waiting-ons
  2. Narrative Compression → Meaning synthesis (not transcript summary)
  3. State Delta           → Changes to knowledge graph
  4. Embedding Generation  → Semantic search via sentence transformers
```

- **Singleton constraint:** One active conversation at a time
- **Your Story:** Permanent Act, default memory destination, identity context
- **Memory as reasoning context:** Memories inform classification, decomposition, and verification at every pipeline stage

**Spec:** [CONVERSATION_LIFECYCLE_SPEC.md](docs/CONVERSATION_LIFECYCLE_SPEC.md)

**Key tables:**
- `conversations`, `messages` — Conversation lifecycle and message storage
- `memories`, `memory_entities`, `memory_state_deltas` — Compressed meaning with embeddings
- `conversation_summaries` — FTS5-searchable conversation summaries
- `state_briefings` — Situational awareness cache (24-hour TTL)
- `turn_assessments` — Per-turn memory extraction decisions
- `classification_memory_references` — Transparency: which memories influenced reasoning

#### 6. Continuous Conversation (Schema v13)

Built on top of the lifecycle system:
- **Per-Turn Delta Assessor** — Background thread evaluates each turn for memory-worthy content
- **State Briefing Service** — Generates situational awareness document, injected on first turn
- **Temporal Context** — Current time, session gap, calendar lookahead injected into every prompt
- **FTS5 Search** — Full-text search over messages and memories via `messages_fts`, `memories_fts`
- **Knowledge Base Browser** — RPC endpoints for memory search, supersession chains, influence logs

**Location:** `src/cairn/services/` (turn_delta_assessor, state_briefing_service, temporal_context, compression_pipeline, compression_manager, conversation_service, memory_service)

#### 7. Health Pulse

Monitors data freshness, calibration alignment, and system health across three axes. Surfaces findings through chat ("how are you doing?") and a passive UI indicator.

**Location:** `src/cairn/cairn/health/` — runner, snapshot, anti_nag, checks/ (9 check modules)

---

## Code Quality Standards

### Python Requirements

```bash
# Python version
python >= 3.12

# Formatting and linting
ruff check .           # Lint (E, F, I, UP, B rules)
ruff format .          # Format (100 char line length)

# Type checking
mypy src/              # Strict equality, warn return any

# Testing
pytest                 # Coverage report (slow tests excluded by default)
pytest -m slow         # Run slow tests (require Ollama)
```

### Configuration (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
addopts = "--cov=cairn --cov-report=term-missing -m 'not slow'"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_ignores = true
strict_equality = true
```

### Code Conventions

- **Type hints:** Use `|` for unions (e.g., `str | None`), not `Optional[]`
- **Error handling:** Fail loudly with context. Use structured error types in `src/cairn/errors.py`
- **Dataclasses:** Prefer dataclasses over dicts for structured data
- **Docstrings:** Required for public functions; explain WHY, not WHAT
- **File organization:** Follow existing structure (`cairn/`, `atomic_ops/`, `providers/`, `rpc_handlers/`, `services/`)

---

## Recent Design Decisions

### 1. CAIRN Simplification (2026-01)
**Context:** Simple conversational queries were going through 11 processing layers.

**Changes:**
- Intent-aware verification (FAST mode for READ/INTERPRET on STREAM destinations)
- Removed redundant decomposition calls
- Conditional intent enhancement (only when contextual references present)

**Result:** Personal questions now ~6 layers instead of 11, preserving full verification for mutations.

### 2. Ollama-Only Provider Strategy
**Decision:** Cairn uses Ollama exclusively for local inference. No cloud providers.

**Rationale:** Mission alignment (local-first), cost (free after download), privacy (no data leaves machine).

**Implementation:** `src/cairn/providers/factory.py` creates Ollama provider only.

### 3. Conversation Lifecycle & Memory Architecture (2026-02)
**Decision:** Conversations are units of meaning with a deliberate lifecycle. Memories are active reasoning context, not passive storage.

**Key choices:**
- Singleton constraint (one conversation at a time) — depth over breadth
- 4-stage local compression pipeline (entity extraction, narrative, state deltas, embeddings)
- Your Story as permanent, un-archivable Act for cross-cutting identity context
- Memories augment classification, decomposition, and verification at every pipeline stage

### 4. ReOS/RIVA Extraction (2026-02)
**Decision:** Extract ReOS (Linux system control) and RIVA (code verification) into separate archive directories. Cairn is now a single-agent system.

**Backward compat preserved:** `reos.db` filename, `~/.reos-data/` directory, `com.reos.providers` keyring service, crypto salts — all kept to avoid data loss.

**Archives:** `/home/kellogg/dev/ReOS/`, `/home/kellogg/dev/RIVA/`

---

## Key Files by Use Case

### Working on CAIRN (Attention Minder)
```
src/cairn/cairn/intent_engine.py       # 4-stage pipeline
src/cairn/cairn/surfacing.py           # Smart surfacing algorithms
src/cairn/cairn/mcp_tools.py           # CAIRN tool implementations
src/cairn/cairn/store.py               # Knowledge storage (SQLite)
src/cairn/cairn/thunderbird.py         # Calendar/contacts bridge
src/cairn/cairn/coherence.py           # Coherence kernel (distraction filtering)
src/cairn/cairn/extended_thinking.py   # Extended thinking traces
src/cairn/cairn/identity.py            # Identity context (Your Story)
src/cairn/atomic_ops/cairn_integration.py  # Bridge to atomic ops system
```

### Working on Conversation Lifecycle & Memory
```
docs/CONVERSATION_LIFECYCLE_SPEC.md          # Specification
src/cairn/services/conversation_service.py   # Conversation management
src/cairn/services/memory_service.py         # Memory storage, search, routing
src/cairn/services/compression_pipeline.py   # 4-stage compression
src/cairn/services/compression_manager.py    # Compression orchestration
src/cairn/services/turn_delta_assessor.py    # Per-turn memory extraction
src/cairn/services/state_briefing_service.py # Situational awareness
src/cairn/services/temporal_context.py       # Time context injection
src/cairn/memory/retriever.py               # Memory retrieval and ranking
src/cairn/memory/extractor.py               # Entity extraction
src/cairn/memory/graph_store.py             # Memory graph storage
src/cairn/rpc_handlers/conversations.py     # Conversation RPC
src/cairn/rpc_handlers/memories.py          # Memory RPC
```

### Working on The Play (Life Organization)
```
src/cairn/play_fs.py                   # Play operations (create_act, create_scene)
src/cairn/play_db.py                   # SQLite schema and CRUD (v13)
src/cairn/play/blocks_db.py            # Block storage
src/cairn/play/blocks_tree.py          # Block tree operations
src/cairn/play/markdown_parser.py      # Markdown → blocks
src/cairn/rpc_handlers/play.py         # RPC endpoints
apps/cairn-tauri/src/playOverlay.ts    # Frontend UI
```

### Working on Atomic Operations
```
src/cairn/atomic_ops/processor.py              # Classification and decomposition
src/cairn/atomic_ops/classifier.py             # LLM-based classification
src/cairn/atomic_ops/executor.py               # Execution with safety checks
src/cairn/atomic_ops/cairn_integration.py      # CAIRN bridge
src/cairn/atomic_ops/decomposer.py             # Task decomposition
src/cairn/atomic_ops/entity_resolver.py        # Entity resolution
src/cairn/atomic_ops/verifiers/pipeline.py     # Multi-layer verification pipeline
src/cairn/atomic_ops/verifiers/safety.py       # Safety verification
```

### Working on Health Pulse
```
src/cairn/cairn/health/runner.py               # Health check runner
src/cairn/cairn/health/snapshot.py             # Health state snapshots
src/cairn/cairn/health/anti_nag.py             # Anti-nag throttling
src/cairn/cairn/health/checks/                 # 9 individual checks
src/cairn/rpc_handlers/health.py               # Health RPC
```

### Working on Providers/LLM Integration
```
src/cairn/providers/factory.py         # Provider creation (Ollama only)
src/cairn/providers/base.py            # Provider interface
src/cairn/providers/ollama.py          # Ollama provider implementation
src/cairn/providers/secrets.py         # Keyring integration
src/cairn/ollama.py                    # Low-level Ollama client
```

### Working on Frontend
```
apps/cairn-tauri/src/main.ts           # App init, RPC bridge
apps/cairn-tauri/src/cairnView.ts      # CAIRN chat UI
apps/cairn-tauri/src/playOverlay.ts    # The Play organization UI
apps/cairn-tauri/src/settingsOverlay.ts # Settings panel
apps/cairn-tauri/src/lockScreen.ts     # Authentication screen
apps/cairn-tauri/src/types.ts          # TypeScript types
apps/cairn-tauri/src/react/            # React block editor components
```

### Core Infrastructure
```
src/cairn/agent.py                     # Main chat agent
src/cairn/app.py                       # FastAPI application
src/cairn/db.py                        # Database singleton
src/cairn/ui_rpc_server.py             # Tauri ↔ Python RPC server (stdio)
src/cairn/http_rpc.py                  # HTTP RPC client
src/cairn/mcp_server.py                # MCP server
src/cairn/config.py                    # Configuration
src/cairn/auth.py                      # PAM authentication
src/cairn/security.py                  # Security utilities
src/cairn/errors.py                    # Error types
```

---

## Testing

### Running Tests
```bash
# All tests (excludes slow/LLM tests)
PYTHONPATH="src" pytest tests/ -x --tb=short -q --no-cov

# With coverage
pytest

# Slow tests (require running Ollama)
pytest -m slow

# Specific test file
pytest tests/test_intent_engine.py -v
```

### Key Test Files
```
tests/test_intent_engine.py            # Intent pipeline
tests/test_atomic_ops_executor.py      # Atomic ops execution
tests/test_play_fs.py                  # Play filesystem operations
tests/test_play_db.py                  # Play database operations
tests/test_play_rpc.py                 # Play RPC handlers
tests/test_cairn.py                    # CAIRN agent
tests/test_agent_integration.py        # Agent integration
tests/test_conversation_lifecycle.py   # Conversation lifecycle
tests/test_compression_pipeline.py     # Compression pipeline
tests/test_memory_service.py           # Memory service
tests/test_memory_retriever.py         # Memory retrieval
tests/test_turn_delta_assessor.py      # Turn delta assessor
tests/test_state_briefing_service.py   # State briefings
tests/test_temporal_context.py         # Temporal context
tests/test_knowledge_browser.py        # Knowledge base browser
tests/test_health_*.py                 # Health check tests (12 files)
tests/test_ui_rpc_server.py            # RPC server
tests/test_providers.py                # Ollama provider
tests/test_rpc_handlers_base.py        # RPC base class
```

### Test Count
~1996 tests, 8 skipped. Zero tolerance for test failures on main.

---

## Commit Conventions

Follows Conventional Commits:

```bash
feat(cairn): Add calendar sync
fix(block-editor): Fix content persistence
refactor: Consolidate entry points
docs(architecture): Update CAIRN description
test: Add memory service tests
```

**Scope examples:** `cairn`, `play`, `atomic-ops`, `providers`, `rpc`, `ui`, `block-editor`, `documents`, `memory`, `health`

---

## Dependencies

### Core Runtime
```toml
fastapi = ">=0.115.0,<1.0.0"        # RPC server
uvicorn = ">=0.30.0,<0.32.0"        # ASGI server
pydantic = ">=2.8.0,<3.0.0"         # Data validation
httpx = ">=0.27.0,<1.0.0"           # HTTP client (Ollama)
tenacity = ">=8.2.0,<10.0.0"        # Retry with backoff
mistletoe = ">=1.3.0,<2.0.0"        # Markdown parsing (block editor)
python-dateutil = ">=2.8.0,<3.0.0"  # RRULE parsing (recurring events)
aiofiles = ">=23.0.0,<25.0.0"       # Async file ops (PWA)
```

### Authentication & Security
```toml
python-pam = ">=2.0.0,<3.0.0"       # PAM authentication
cryptography = ">=42.0.0,<44.0.0"   # AES-256-GCM encryption
keyring = ">=24.0.0,<26.0.0"        # API key storage
secretstorage = ">=3.3.0,<4.0.0"    # Linux D-Bus SecretService
```

### Optional
```toml
# pip install -e ".[semantic]"
sentence-transformers               # Vector embeddings

# pip install -e ".[documents]"
pypdf, python-docx, openpyxl        # Document ingestion (PDF, DOCX, XLSX)
```

---

## Source Tree Overview

```
src/cairn/
├── agent.py                 # Main chat agent
├── app.py                   # FastAPI app
├── db.py                    # Database singleton (reos.db)
├── ui_rpc_server.py         # Tauri RPC server (stdio)
├── http_rpc.py              # HTTP RPC client
├── mcp_tools.py             # MCP tool registry
├── mcp_server.py            # MCP server
├── play_db.py               # Play schema (v13)
├── play_fs.py               # Play operations
├── config.py, auth.py, security.py, errors.py, types.py
├── atomic_ops/              # 3x2x3 classification & execution
│   ├── processor.py, classifier.py, decomposer.py
│   ├── executor.py, cairn_integration.py
│   └── verifiers/           # Multi-layer verification
├── cairn/                   # CAIRN agent implementation
│   ├── intent_engine.py     # 4-stage intent pipeline
│   ├── surfacing.py         # Smart surfacing
│   ├── mcp_tools.py         # Tool implementations
│   ├── store.py             # Knowledge store
│   ├── coherence.py         # Coherence kernel
│   ├── identity.py          # Your Story
│   ├── extended_thinking.py # Thinking traces
│   ├── thunderbird.py       # Calendar bridge
│   └── health/              # Health pulse system
├── services/                # Background services
│   ├── conversation_service.py
│   ├── memory_service.py
│   ├── compression_pipeline.py, compression_manager.py
│   ├── turn_delta_assessor.py
│   ├── state_briefing_service.py
│   ├── temporal_context.py
│   └── chat_service.py, play_service.py, ...
├── memory/                  # Memory graph & retrieval
│   ├── retriever.py, extractor.py, graph_store.py
│   └── relationships.py
├── rpc_handlers/            # RPC endpoints (20 handlers)
├── providers/               # LLM providers (Ollama only)
├── reasoning/               # Reasoning engine
├── play/                    # Block storage & markdown
├── documents/               # Document extraction
└── migrations/              # Schema migrations
```

---

## Agent Delegation Notes

When working with the orchestration system from `~/.claude/CLAUDE.md`:

**scout** — Find where features live. Example: "Where is calendar sync implemented?"

**planner** — Non-trivial features. Example: "Plan how to add recurring event expansion."

**implementer** — Execute after plan approval. Knows Python 3.12+, ruff, mypy conventions.

**tester** — TDD workflow or coverage gaps.

**reviewer** — Post-implementation quality check.

**state-fidelity** — After features that display backend state in Tauri UI.

**debugger** — Diagnose issues in atomic_ops pipeline, intent engine, or provider calls.

**verifier** — Final checkpoint before declaring work complete.

---

## Common Patterns

### Adding a New CAIRN Tool

1. Define in `list_tools()` in `src/cairn/mcp_tools.py`
2. Implement in `CairnToolHandler.call_tool()` in `src/cairn/cairn/mcp_tools.py`
3. Add intent patterns to `INTENT_PATTERNS` in `intent_engine.py` (if natural language support needed)
4. Add to category mapping in `CATEGORY_TOOLS` in `intent_engine.py`
5. Write test in `tests/test_cairn.py` or a new test file

### Adding a New RPC Handler

1. Create handler in `src/cairn/rpc_handlers/`
2. Inherit from `BaseRPCHandler` (see `_base.py`)
3. Register in `src/cairn/ui_rpc_server.py`
4. Add TypeScript types in `apps/cairn-tauri/src/types.ts`
5. Call from frontend via `invoke("kernel_request", { method, params })`

### Adding a New Service

1. Create in `src/cairn/services/`
2. Follow singleton pattern (see `conversation_service.py`)
3. Wire into agent or RPC handler as needed
4. Add tests in `tests/test_<service_name>.py`

---

## Summary

Cairn is a local-first personal attention minder focused on small models (1B parameters) that run on accessible hardware (8GB RAM, no GPU). The architecture decomposes operations into atomic units, uses a 2-tier life organization system (Acts → Scenes), and features a conversation lifecycle that extracts meaning into persistent memory.

**When in doubt:**
1. Check this file for conventions and file locations
2. Follow the global workflow from ~/.claude/CLAUDE.md
3. Ask clarifying questions before implementing

**Mission:** Build the best personal AI assistant in the world. Then give it away.
