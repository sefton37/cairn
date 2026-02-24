# ReOS (Talking Rock) Project Guide

> **See `~/.claude/CLAUDE.md` for the comprehensive workflow (Comprehension → Clarification → Planning → Execution).** This document provides ReOS-specific context only.

---

## What This Is

**Talking Rock** is a local-first AI assistant with three specialized agents:
- **CAIRN** (Priority 1) - Attention minder and life organizer (1B models)
- **ReOS** (Priority 2) - Natural language Linux system control (1-3B models)
- **RIVA** (Frozen — NOL backend ready) - Code verification engine (7-8B+ models, NOL infrastructure complete)

**Core philosophy:** Local inference is essentially free, enabling verification and analysis at scale that cloud services can't afford. Zero trust, local only, encrypted at rest, never phones home.

---

## Architecture Quick Reference

Read these first when working on the project:
- **[ARCHITECTURE.md](src/reos/architecture/ARCHITECTURE.md)** - System overview, data models, component architecture
- **[README.md](README.md)** - Mission statement, agent descriptions, development priorities
- **[CONVERSATION_LIFECYCLE_SPEC.md](docs/CONVERSATION_LIFECYCLE_SPEC.md)** - Conversation lifecycle, memory extraction, reasoning integration
- **[CAIRN_SIMPLIFICATION_PLAN.md](docs/archive/CAIRN_SIMPLIFICATION_PLAN.md)** - Recent optimization work (archived)

### Key Architectural Patterns

#### 1. Atomic Operations (3x2x3 Taxonomy)

Every user request is classified and recorded as an atomic operation:

```python
# Classification dimensions
destination_type: "stream" | "file" | "process"  # Where output goes
consumer_type: "human" | "machine"               # Who consumes result
execution_semantics: "read" | "interpret" | "execute"  # What action

# Examples
"show memory usage"     → (stream, human, read)
"save to notes.txt"     → (file, human, execute)
"run pytest"            → (process, machine, execute)
"what's next today?"    → (stream, human, interpret)
```

**Location:** `src/reos/atomic_ops/` - processor, executor, cairn_integration

#### 2. The Play (2-Tier Life Organization)

```python
Act        # Life narrative (Career, Health, Family) - months to years
  └─ Scene # Calendar event or task within the narrative

SceneStage = "planning" | "in_progress" | "awaiting_data" | "complete"
```

Philosophy: Two levels prevent obscuring responsibility in complexity. Acts answer "What narrative?" Scenes answer "When am I doing this?"

**Location:** `src/reos/play_fs.py`, `src/reos/play_db.py`

#### 3. CAIRN Intent Engine (4-Stage Pipeline)

```
Stage 1: Extract Intent    → Pattern matching → Category (CALENDAR, PLAY, SYSTEM)
Stage 2: Verify Intent     → Check tool availability, build args
Stage 3: Execute Tool      → Call MCP tool with extracted args
Stage 4: Generate Response → Strictly from tool results (no hallucination)
```

**Location:** `src/reos/cairn/intent_engine.py`

#### 4. MCP Tools System

45+ tools organized by category:
- `cairn_*` - The Play CRUD, calendar, contacts, knowledge (CairnToolHandler)
- `linux_*` - System operations (linux_tools.py)
- `reos_*` - Git/repo operations (git_tools.py)
- `memory_*` - Conversation lifecycle, memory search, reasoning context (planned)

**Location:** `src/reos/mcp_tools.py`, `src/reos/cairn/mcp_tools.py`

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
- **13 new MCP tools** for memory management (search, routing, explanation)

**Spec:** [CONVERSATION_LIFECYCLE_SPEC.md](docs/CONVERSATION_LIFECYCLE_SPEC.md)

**New database tables:**
- `conversations` — Conversation lifecycle tracking
- `messages` — Message storage within conversations
- `memories` — Compressed meaning blocks with embeddings
- `memory_entities` — Extracted entities (people, tasks, decisions)
- `memory_state_deltas` — Knowledge graph changes from conversations
- `classification_memory_references` — Transparency: which memories influenced reasoning

**New block types:** `conversation`, `message`, `memory`

> `memory_entity` is stored in the `memory_entities` relational table (not as blocks). See the spec's Block Integration section for details.

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
pytest --cov           # Minimum 45% coverage required
```

### Configuration (pyproject.toml)

```toml
[tool.ruff]
line-length = 100
target-version = "py312"
select = ["E", "F", "I", "UP", "B"]

[tool.pytest.ini_options]
addopts = "--cov=reos --cov-report=term-missing --cov-fail-under=45"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_ignores = true
strict_equality = true
```

### Code Conventions

- **Type hints:** Use `|` for unions (e.g., `str | None`), not `Optional[]`
- **Error handling:** Fail loudly with context. Use structured error types in `src/reos/errors.py`
- **Dataclasses:** Prefer dataclasses over dicts for structured data
- **Docstrings:** Required for public functions; explain WHY, not WHAT
- **File organization:** Follow existing structure (`cairn/`, `atomic_ops/`, `providers/`, `rpc_handlers/`)

---

## Recent Design Decisions

### 1. CAIRN Simplification (2026-01)
**Context:** Simple conversational queries were going through 11 processing layers.

**Changes:**
- Intent-aware verification (FAST mode for READ/INTERPRET on STREAM destinations)
- Removed redundant decomposition calls
- Conditional intent enhancement (only when contextual references present)

**Result:** Personal questions now ~6 layers instead of 11, preserving full verification for mutations.

See [CAIRN_SIMPLIFICATION_PLAN.md](docs/archive/CAIRN_SIMPLIFICATION_PLAN.md)

### 2. Ollama-Only Provider Strategy
**Decision:** ReOS uses Ollama exclusively for local inference. No cloud providers.

**Rationale:** Mission alignment (local-first), cost (free after download), privacy (no data leaves machine).

**Implementation:** `src/reos/providers/factory.py` creates Ollama provider only. Anthropic provider removed.

### 3. RIVA NOL Integration (2026-02) — Infrastructure Only
**Decision:** When RIVA unfreezes, it will use NoLang as its code generation backend. The infrastructure is built but RIVA itself remains frozen.

**Rationale:** RIVA was frozen because LLM-generated code is ambiguous and unverifiable. NoLang solves this — one canonical form per computation, structural verification before execution, 65 opcodes with no naming decisions. The infrastructure is ready so that when RIVA unfreezes, the LLM generates fixed-width instructions instead of Python/JS, and the verifier confirms correctness before any byte executes.

**Key components (implemented, not wired to production):**
- `NolBridge` (`src/reos/code_mode/nol_bridge.py`) — Python subprocess wrapper around `nolang` CLI
- `IntentToNolTranslator` (`src/reos/code_mode/intent_to_nol.py`) — Converts intentions to NOL function signatures
- `NOL_STRUCTURAL` verification layer in `verification_layers.py` — Runs before SYNTAX

**Status:** Infrastructure complete, 73 integration tests passing. `CodeExecutor.use_nol` exists but is never set to True in production. `_generate_nol_assembly()` is a stub. RIVA development remains frozen while CAIRN and ReOS prove small-model viability.

### 4. Conversation Lifecycle & Memory Architecture (2026-02)
**Decision:** Conversations are units of meaning with a deliberate lifecycle. Memories are active reasoning context, not passive storage.

**Key choices:**
- Singleton constraint (one conversation at a time) — depth over breadth
- 4-stage local compression pipeline (entity extraction, narrative, state deltas, embeddings)
- Your Story as permanent, un-archivable Act for cross-cutting identity context
- Memories augment classification, decomposition, and verification at every pipeline stage

**Spec:** [CONVERSATION_LIFECYCLE_SPEC.md](docs/CONVERSATION_LIFECYCLE_SPEC.md)

---

## Key Files by Use Case

### Working on CAIRN (Attention Minder)
```
src/reos/cairn/intent_engine.py    # 4-stage pipeline
src/reos/cairn/surfacing.py        # Smart surfacing algorithms
src/reos/cairn/mcp_tools.py        # CAIRN tool implementations
src/reos/cairn/store.py            # Knowledge storage (SQLite)
src/reos/cairn/thunderbird.py      # Calendar/contacts bridge
src/reos/atomic_ops/cairn_integration.py  # Bridge to atomic ops system
```

### Working on Conversation Lifecycle & Memory
```
docs/CONVERSATION_LIFECYCLE_SPEC.md  # Complete specification and schema
# Implementation files (planned, not yet created):
# src/reos/cairn/memory.py           # Memory extraction, storage, search
# src/reos/cairn/compression.py      # 4-stage compression pipeline
# src/reos/rpc_handlers/conversations.py  # Conversation lifecycle RPC
```

### Working on The Play (Life Organization)
```
src/reos/play_fs.py                # Play operations (create_act, create_scene)
src/reos/play_db.py                # SQLite schema and CRUD
src/reos/rpc_handlers/play.py      # RPC endpoints
apps/reos-tauri/src/playOverlay.ts # Frontend UI
```

### Working on ReOS (System Helper)
```
src/reos/shell_cli.py              # Shell CLI entry point
src/reos/linux_tools.py            # System operations
src/reos/atomic_ops/executor.py    # Command execution safety
```

### Working on Atomic Operations
```
src/reos/atomic_ops/processor.py   # Classification and decomposition
src/reos/atomic_ops/executor.py    # Execution with safety checks
src/reos/atomic_ops/cairn_integration.py  # CAIRN bridge
src/reos/atomic_ops/classification_context.py  # Few-shot learning for LLM classification
```

### Working on Providers/LLM Integration
```
src/reos/providers/factory.py      # Provider creation (Ollama only)
src/reos/providers/base.py         # Provider interface
src/reos/providers/secrets.py      # Keyring integration
```

### Working on RIVA / NOL Integration
```
src/reos/code_mode/nol_bridge.py          # NolBridge: assemble, verify, run via subprocess
src/reos/code_mode/intent_to_nol.py       # IntentToNolTranslator, NolMemoCache
src/reos/code_mode/executor.py            # CodeExecutor with use_nol flag
src/reos/code_mode/intention.py           # Action.nol_assembly, WorkContext.nol_bridge
src/reos/code_mode/optimization/verification_layers.py  # NOL_STRUCTURAL layer
src/reos/config.py                        # NOL_BINARY_PATH configuration
tests/test_nol_bridge.py                  # Bridge tests (37)
tests/test_riva_nol_integration.py        # Integration tests (22)
tests/test_intent_to_nol.py              # Translator tests (14)
```

### Working on Frontend
```
apps/reos-tauri/src/main.ts        # App init, RPC bridge
apps/reos-tauri/src/cairnView.ts   # CAIRN chat UI
apps/reos-tauri/src/playOverlay.ts # The Play organization UI
apps/reos-tauri/src/types.ts       # TypeScript types
```

---

## Testing Strategy

### Current State
- **Coverage:** 45% minimum (enforced in CI)
- **Framework:** pytest with pytest-cov
- **Location:** `tests/`

### Test Organization
```
tests/
  test_agent.py                  # Agent routing
  test_cairn_intent_engine.py    # Intent pipeline
  test_atomic_ops.py             # Classification and execution
  test_providers.py              # Ollama provider
  test_play.py                   # The Play CRUD
  test_rpc_handlers_base.py      # RPC base class
```

### Running Tests
```bash
# All tests with coverage
pytest --cov

# Specific test file
pytest tests/test_cairn_intent_engine.py -v

# Watch mode (requires pytest-watch)
ptw
```

---

## Commit Conventions

Observed from git history (follows Conventional Commits):

```bash
feat: Add new feature
feat(cairn): Add calendar sync
feat(documents): Add /document slash command

fix: Bug fix without scope
fix(block-editor): Fix content persistence

refactor: Code restructuring
refactor: Consolidate entry points

docs: Documentation only
docs(architecture): Update CAIRN description

test: Testing only
test(metrics): Add metrics DB test
```

**Scope examples:** `cairn`, `play`, `riva`, `atomic-ops`, `providers`, `rpc`, `ui`, `block-editor`, `documents`

---

## Dependencies

### Core Runtime
```toml
fastapi = ">=0.115.0,<1.0.0"       # RPC server
uvicorn = ">=0.30.0,<0.32.0"       # ASGI server
pydantic = ">=2.8.0,<3.0.0"        # Data validation
httpx = ">=0.27.0,<1.0.0"          # HTTP client (Ollama)
tenacity = ">=8.2.0,<10.0.0"       # Retry with backoff
```

### Authentication & Security
```toml
python-pam = ">=2.0.0,<3.0.0"      # PAM authentication
cryptography = ">=42.0.0,<44.0.0"  # AES-256-GCM encryption
keyring = ">=24.0.0,<26.0.0"       # API key storage
```

### Optional (install with pip install -e ".[semantic]")
```toml
sentence-transformers  # Vector embeddings
tree-sitter           # AST parsing (RIVA)
pypdf                 # Document ingestion
```

---

## Agent Delegation Notes

When working with the 12-agent orchestration system from `~/.claude/CLAUDE.md`:

### When to Invoke Agents for ReOS Work

**scout** - Use for finding where features live in the codebase. Example: "Where is calendar sync implemented?"

**planner** - Use for non-trivial features. Example: "Plan how to add recurring event expansion to CAIRN surfacing."

**implementer** - Use after plan approval. Knows Python 3.12+, ruff, mypy, pytest conventions from this file.

**tester** - Use for TDD workflow. Knows 45% coverage requirement, pytest conventions.

**reviewer** - Use after implementation. Checks for type hints, error handling, docstrings.

**state-fidelity** - Use after features that display backend state in Tauri UI. Example: After implementing new Play overlay features.

**documenter** - Use for substantial doc updates. Knows ARCHITECTURE.md, README.md structure.

**debugger** - Use for diagnosing issues. Add logging to atomic_ops pipeline, intent engine, or provider calls.

**verifier** - Use as final checkpoint before declaring work complete.

### This File's Role

This CLAUDE.md provides project context that agents need but shouldn't spend tokens discovering:
- Architecture patterns (atomic ops, The Play, intent engine)
- Code quality standards (Python 3.12+, ruff, mypy, 45% coverage)
- Recent design decisions (CAIRN simplification, Ollama-only, RIVA NOL integration)
- Key file locations by use case
- Commit conventions

---

## Common Patterns

### Adding a New CAIRN Tool

1. Define in `list_tools()` in `src/reos/mcp_tools.py`
2. Implement in `CairnToolHandler.call_tool()` in `src/reos/cairn/mcp_tools.py`
3. Add intent patterns to `INTENT_PATTERNS` in `intent_engine.py` (if natural language support needed)
4. Add to category mapping in `CATEGORY_TOOLS` in `intent_engine.py`
5. Write test in `tests/test_cairn_mcp_tools.py`

### Adding a New Atomic Operation Classification

Atomic ops use the 3x2x3 taxonomy. Most work involves tuning classification in `processor.py`, not adding new categories.

If genuinely new semantics needed:
1. Update `ExecutionSemantics` enum in `src/reos/types.py`
2. Update classification logic in `src/reos/atomic_ops/processor.py`
3. Update verification mode selection in `src/reos/atomic_ops/cairn_integration.py`
4. Add tests in `tests/test_atomic_ops.py`

### Adding a New RPC Handler

1. Create handler in `src/reos/rpc_handlers/`
2. Inherit from `BaseRPCHandler` (see `_base.py` for example)
3. Register in `src/reos/ui_rpc_server.py`
4. Add TypeScript types in `apps/reos-tauri/src/types.ts`
5. Call from frontend via `invoke("rpc_call", { method, params })`

---

## Summary

This is a local-first AI assistant focused on democratizing AI through small models (1-3B parameters) that run on accessible hardware (8GB RAM, no GPU). The architecture decomposes operations into atomic units, uses a 2-tier life organization system (Acts → Scenes), and prioritizes verification/safety because local inference is free.

**When in doubt:**
1. Read ARCHITECTURE.md for system overview
2. Check this file for conventions and recent decisions
3. Follow the global workflow from ~/.claude/CLAUDE.md
4. Ask clarifying questions before implementing

**Mission:** Build the best AI assistant in the world. Then give it away.
