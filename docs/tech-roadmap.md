# Talking Rock Technical Roadmap

## Mission & Vision

**Mission:** Center your data around you, not in a data center, so that your attention is centered on what you value. Local, zero trust AI. Small models and footprint, outsized impact and trust.

**Vision:** AI that partners with you and your values, not to automate you. Intent always verified, permission always requested, all learning available to be audited and edited by you.

> **Don't rent a data center. Center your data around you.**

Talking Rock exists to prove that the best AI tools don't require:
- Monthly subscriptions to trillion-dollar companies
- Sending your data to someone else's servers
- Trusting black boxes you can't inspect or modify
- Accepting whatever "engagement-optimized" features they decide to ship

Talking Rock is:
- **Open source**: See how it works, fix bugs, add features
- **Local-first**: Everything runs on your hardware
- **Private**: Your data never leaves your machine
- **Yours**: No subscription, no lock-in, no rent

---

## What We're Building

### CAIRN — Attention Minder

CAIRN is the single agent at the heart of Talking Rock. It is your default conversational partner: it manages The Play (your life knowledge base), protects your attention from noise and distraction, and builds a persistent understanding of who you are and what you value over time.

CAIRN's principles:
- **Transparency over magic** — Every action is explainable. No surprises.
- **User sovereignty over engagement** — You control what happens. We optimize for your goals, not retention.
- **Capability transfer over dependency** — We want you to need us less, not more.
- **Safety without surveillance** — Protection that doesn't require watching you.

**The core value proposition:**

Your data lives on your machine. Every intent is verified before execution. Every memory CAIRN builds about you is visible, editable, and deletable. The AI learns from you — not about you for someone else's benefit.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         Talking Rock Architecture                            │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                     User Interface Layer                            │     │
│  │                                                                     │     │
│  │   Tauri Desktop App              HTTP API                          │     │
│  │   ├── Chat Window                ├── JSON-RPC                      │     │
│  │   ├── The Play Navigator         └── MCP Server                    │     │
│  │   ├── Diff Preview                                                  │     │
│  │   └── Inspector Pane                                                │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                      │                                       │
│                                      ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                          CAIRN Agent                                │     │
│  │                                                                     │     │
│  │  ┌──────────────────────┐  ┌──────────────────┐  ┌──────────────┐  │     │
│  │  │  Atomic Operations   │  │   Verification   │  │ Conversation │  │     │
│  │  │                      │  │                  │  │  Lifecycle   │  │     │
│  │  │ • Classify (3x2x3)   │  │ • Intent verify  │  │              │  │     │
│  │  │ • Decompose          │  │ • Safety checks  │  │ • Memory     │  │     │
│  │  │ • Execute            │  │ • Diff preview   │  │ • Summaries  │  │     │
│  │  │ • Verify             │  │ • Audit log      │  │ • Briefings  │  │     │
│  │  └──────────────────────┘  └──────────────────┘  └──────────────┘  │     │
│  │                                                                     │     │
│  │  ┌──────────────────────────────────────────────────────────────┐   │     │
│  │  │                    The Play (Life KB)                         │   │     │
│  │  │                                                               │   │     │
│  │  │   Acts (narratives)  →  Scenes (events/tasks)                │   │     │
│  │  │   Notes  ·  Attachments  ·  Context selection                │   │     │
│  │  └──────────────────────────────────────────────────────────────┘   │     │
│  │                                                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                      │                                       │
│                                      ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                     Model Backend (Ollama Only)                     │     │
│  │                                                                     │     │
│  │   Ollama (Local)                                                    │     │
│  │   └── llama3.1 (8B)     └── qwen      └── mistral                 │     │
│  │   └── nomic-embed (embeddings)                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                      │                                       │
│                                      ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────┐     │
│  │                         Storage Layer                               │     │
│  │                                                                     │     │
│  │   SQLite Database              File System                          │     │
│  │   ├── Conversations            ├── The Play (local files)          │     │
│  │   ├── Memories & Embeddings    └── File Backups                    │     │
│  │   ├── Project Memory                                                │     │
│  │   └── Audit Log                                                     │     │
│  └────────────────────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Current State (What's Built)

### The Play (Complete)
- [x] Two-tier organizational structure (Acts → Scenes)
- [x] Markdown notebooks at each level
- [x] File attachments
- [x] Context selection (active Acts provide context)
- [x] Repository assignment to Acts

### CAIRN (Active Development)
- [x] 4-stage intent pipeline (extract, verify, execute, respond)
- [x] Atomic operations framework (3x2x3 taxonomy)
- [x] Multi-layer verification pipeline with safety checks
- [x] Coherence kernel (distraction filtering via identity)
- [x] Health pulse (data freshness, calibration, system health)
- [x] Conversation lifecycle (active → compressing → archived)
- [x] 4-stage compression pipeline (entity extraction, narrative, state deltas, embeddings)
- [x] Memory storage with deduplication, signal strengthening, and correction chains
- [x] Memory as reasoning context (memories augment classification and verification)
- [x] Per-turn delta assessor (background memory extraction after every turn)
- [x] State briefing service (situational awareness document, 24-hour cache)
- [x] Temporal context injection (current time, session gap, calendar lookahead)
- [x] FTS5 full-text search over messages and memories
- [x] Knowledge base browser (RPC endpoints for memory search, supersession chains, influence logs)
- [x] Schema v13 with conversation summaries, state briefings, and turn assessments

---

## The Roadmap

### Phase 1: Foundation
**Status: Complete**

- Working attention minder with safety and verification
- The Play for life organization and context
- Contract-based intent prevents hallucination
- Execution-based verification uses output as ground truth

---

### Phase 2: Deeper Understanding
**Goal: Know the codebase and your context like a trusted collaborator**

The gap: CAIRN can search for patterns in files and notes. The next step is semantic understanding — dependency graphs, symbol tables, semantic search across everything you've written or stored.

#### 2.1 Repository Map

```python
# src/cairn/code_mode/repo_map.py

class RepositoryMap:
    """Semantic understanding of a codebase."""

    def build(self) -> None:
        """Build the repository map."""
        self._build_dependency_graph()
        self._build_symbol_table()
        self._build_embeddings()

    def get_context_for_file(self, path: str) -> str:
        """Get relevant context for working on a file."""

    def semantic_search(self, query: str, k: int = 10) -> list[CodeChunk]:
        """Find code relevant to a natural language query."""

    def find_callers(self, function: str) -> list[Location]:
        """Find all places that call a function."""

    def find_usages(self, symbol: str) -> list[Location]:
        """Find all usages of a symbol."""
```

**Why it matters:**
- Context is everything. With a repo map, CAIRN sees relevant code, not random files.
- Semantic search finds things by meaning, not just name.
- Dependency tracking prevents breaking changes.

**Implementation:**
1. Parse ASTs for Python, TypeScript, Rust, Go
2. Build call graph and import graph
3. Embed code chunks using local embedding model (nomic-embed, all-MiniLM)
4. Store in SQLite with vector similarity extension

---

#### 2.2 LSP Integration

```python
# src/cairn/code_mode/lsp_bridge.py

class LSPBridge:
    """Bridge to Language Server Protocol for real-time feedback."""

    async def get_diagnostics(self, file: str) -> list[Diagnostic]:
        """Get current errors/warnings for a file."""

    async def get_definition(self, file: str, line: int, col: int) -> Location:
        """Go to definition."""

    async def find_references(self, file: str, line: int, col: int) -> list[Location]:
        """Find all references to symbol at position."""
```

**Why it matters:**
- Real-time type errors without running tests
- "What does this function return?" answered instantly
- Rename refactoring that doesn't break things

---

### Phase 3: User Experience
**Goal: Make it feel transparent while staying trustworthy**

#### 3.1 Diff Preview UI

```typescript
// apps/cairn-tauri/src/components/DiffPreview.tsx

interface DiffPreviewProps {
  changes: FileChange[];
  onApprove: (changes: FileChange[]) => void;
  onReject: () => void;
  onApproveFile: (path: string) => void;
  onRejectFile: (path: string) => void;
}

// Show:
// - File-by-file changes
// - Hunk-by-hunk diffs
// - Accept/reject per file
// - Accept/reject per hunk
// - "Explain this change" button
```

**Why it matters:**
- Intent is always verified before execution — this is the visual form of that.
- No surprises, no "what did it do?"
- Users MUST see what's changing before it happens.

---

#### 3.2 Streaming Execution UI

```typescript
// apps/cairn-tauri/src/components/ExecutionStream.tsx

interface ExecutionStreamProps {
  state: ExecutionState;
  onPause: () => void;
  onResume: () => void;
  onCancel: () => void;
}

// Show:
// - Current phase (Intent, Verify, Execute, etc.)
// - Progress through steps
// - Live output
// - "Pause and let me look" button
```

**Why it matters:**
- Transparency builds trust.
- Users can interrupt when they see something wrong.
- Educational: watch how the AI works.

---

#### 3.3 Inspector Pane

```typescript
// apps/cairn-tauri/src/components/Inspector.tsx

interface InspectorProps {
  message: ChatMessage;
}

// Show:
// - What context was provided
// - What tools were called
// - Which memories influenced the response
// - Why this approach was chosen
// - Confidence level
```

**Why it matters:**
- "Why did you do that?" always has an answer.
- Auditable learning: see exactly which memories shaped a response.
- Debugging AI decisions.

---

### Phase 4: Intelligence & Memory
**Goal: Get smarter about YOU over time, visibly and editably**

> **Note:** The conversation lifecycle and memory architecture (see [CONVERSATION_LIFECYCLE_SPEC.md](./CONVERSATION_LIFECYCLE_SPEC.md)) defines a unified memory system where conversations produce memories that feed into all reasoning. This phase extends that system toward richer user-visible controls.

#### 4.1 Memory Editing UI

Users should be able to see, correct, and delete every memory CAIRN holds about them.

```python
# Already built in memory_service.py
# Phase 4 adds the user-facing interface:

# RPC endpoints (already implemented):
# lifecycle/memories/search
# lifecycle/memories/list_enhanced
# lifecycle/memories/supersession_chain
# lifecycle/memories/influence_log

# Remaining: Tauri UI components for:
# - Memory browser (list, filter by Act, entity type)
# - Memory editor (correct a fact, mark as rejected)
# - Influence explorer (this memory shaped these responses)
```

**Why it matters:**
- All learning must be auditable and editable — this is the mission.
- Trust requires transparency. Users who can see and correct CAIRN's model of them will trust it more, not less.

---

#### 4.2 Test-First Contracts

```python
# Enhanced contract generation

class ContractBuilder:
    def build_from_intent(self, intent: DiscoveredIntent) -> Contract:
        # Generate actual test code, not just patterns
        test_code = self._generate_test_code(intent)

        criteria.append(AcceptanceCriterion(
            type=CriterionType.TEST_CODE_PASSES,
            description="Generated tests pass",
            test_code=test_code,
        ))

        return Contract(
            acceptance_criteria=criteria,
            test_file=self._write_test_file(test_code),
        )
```

**Why it matters:**
- TDD by default.
- Tests ARE the specification.
- No ambiguity about what "done" means.

---

#### 4.3 Multi-path Exploration

```python
# src/cairn/code_mode/explorer.py

class Explorer:
    """Try multiple approaches when unsure."""

    def explore(self, problem: str, n_paths: int = 3) -> list[Approach]:
        """Generate and evaluate multiple approaches."""

        approaches = []
        for i in range(n_paths):
            approach = self._generate_approach(problem, i)
            score = self._evaluate_approach(approach)
            approaches.append((approach, score))

        return sorted(approaches, key=lambda x: x[1], reverse=True)
```

**Why it matters:**
- Hard problems have multiple solutions.
- Try several, pick the best.
- Don't get stuck on first idea.

---

### Phase 5: Ecosystem
**Goal: Integrate with everything users rely on**

#### 5.1 MCP Tool Integration

```python
# Already have MCP server, extend it

def get_context_tools(active_act: Act) -> list[Tool]:
    return [
        Tool(name="cairn_read_file", ...),
        Tool(name="cairn_write_file", ...),
        Tool(name="cairn_semantic_search", ...),
        Tool(name="cairn_find_references", ...),
    ]
```

---

#### 5.2 Documentation Lookup

```python
# src/cairn/code_mode/docs.py

class DocumentationLookup:
    """Fetch documentation for unknown APIs."""

    def lookup(self, symbol: str, language: str) -> Documentation | None:
        # Check local cache first
        cached = self._cache.get(symbol, language)
        if cached:
            return cached

        doc = self._fetch_from_source(symbol, language)
        if doc:
            self._cache.set(symbol, language, doc)

        return doc
```

**Why it matters:**
- Don't hallucinate APIs — look them up.
- Local cache for speed and privacy.

---

## Implementation Priority

### Tier 0: Active Development

| Feature | Why | Effort |
|---------|-----|--------|
| **Memory Editing UI** | Mission-critical: auditable, editable learning | Medium |
| **Diff Preview UI** | Verified intent must be visible before execution | Medium |
| **Inspector Pane** | Transparency into which memories shaped responses | Medium |

### Tier 1: High Impact, Build Next

| Feature | Why | Effort |
|---------|-----|--------|
| **Repository Map** | 10x better context for technical work | High |
| **Test-First Contracts** | Verification done right | Medium |
| **Streaming Execution UI** | Transparency, trust | Medium |

### Tier 2: Deeper Capability

| Feature | Why | Effort |
|---------|-----|--------|
| **LSP Integration** | Real-time feedback | High |
| **Multi-path Exploration** | Handles hard problems | High |
| **Documentation Lookup** | Prevent hallucination | Medium |

---

### Phase 6: Specialized Agents
**Goal: Extend the Talking Rock ecosystem with domain-specific agents that follow the established pattern: rely on an open-source tool for data ingestion, add local AI intelligence on top.**

Each agent is a Talking Rock ecosystem child — local-first, Ollama-only, SQLite-backed, privacy-first. Each inherits all shared constraints. Each follows the Cairn pattern of partnering with existing tools rather than reinventing data pipelines.

#### 6.1 Assay — Dialectic-Scored RSS Feed Reader

**What it does:** Reads your RSS feeds, scores articles against dialectics you care about, and surfaces the most relevant 1-2x daily.

**Key concept — Dialectics:** Rather than pre-defined scoring dimensions (like Sieve's 7-dimension rubric), Assay discovers what tensions matter to you through conversation. A dialectic is a pair of opposing lenses — e.g., "centralization vs. decentralization", "efficiency vs. resilience", "individual liberty vs. collective safety". You define these through natural dialogue; Assay learns your intellectual landscape.

**How it works:**
1. **Feed ingestion** — Subscribe to RSS/Atom feeds. Assay fetches and stores articles locally.
2. **Dialectic discovery** — Through conversation, Assay surfaces candidate dialectics from your reading patterns and interests. You confirm, refine, or reject them.
3. **LLM scoring** — Each article is scored against your dialectics using local Ollama inference. The score isn't "good/bad" — it's "how strongly does this article engage with tensions you care about?"
4. **Surfacing** — 1-2x daily, Assay presents the highest-scoring articles with brief explanations of which dialectics they engage and why.

**Design principles:**
- **Your lens, not ours** — Sieve has Abend's voice and fixed dimensions. Assay has YOUR voice and YOUR dimensions.
- **Discovery through dialogue** — Dialectics emerge from conversation, not configuration files.
- **Never optimize for volume** — surfacing fewer, higher-quality articles is always better.
- **Transparent scoring** — you see exactly which dialectics drove each article's score and can adjust.

**Data backbone:** RSS/Atom feed parsing (likely `feedparser` or similar). No external service dependency.

**Relationship to Sieve:** Sieve is editorial intelligence in a specific analytical voice. Assay is personal intelligence in YOUR voice. They could share feeds but serve fundamentally different purposes. Sieve publishes; Assay whispers.

---

#### 6.2 Aurum — Financial Awareness via Actual Budget

**What it does:** Partners with [Actual Budget](https://actualbudget.org/) (open-source, self-hosted budgeting tool) to add AI-powered financial awareness. Actual connects to your bank, aggregates and stores your financial data. Aurum adds intelligence on top.

**Key capabilities:**
1. **Expense classification** — LLM-driven categorization of transactions that learns your patterns over time. "Was this grocery or restaurant?" becomes automatic.
2. **Receipt decomposition** — The killer feature. Cross-references email receipts against credit card charges to break aggregate charges into component parts. An Amazon order with a book, a cable, and a kitchen tool becomes three categorized line items, not one opaque "AMAZON.COM" charge.
3. **Pattern surfacing** — "You spent 40% more on dining out this month than your 3-month average." Not judgmental — observational. Mirror, not manager (inheriting Cairn's philosophy).
4. **Anomaly detection** — Flag unusual charges, duplicate charges, or charges that don't match any known receipt.

**Data backbone:** [Actual Budget](https://actualbudget.org/) handles bank sync (via SimpleFIN or GoCardless), transaction storage, and the core budgeting interface. Aurum reads from Actual's SQLite database and adds an AI conversational layer. Aurum does NOT replace Actual — it augments it.

**Receipt decomposition flow:**
```
Email receipt (via Thunderbird bridge, shared with Cairn)
  → Parse line items, quantities, prices
  → Match against credit card charge (amount, merchant, date)
  → Split the single transaction into N categorized sub-items
  → Store decomposition in Aurum's DB, reference original Actual transaction
```

**Design principles:**
- **Actual is the source of truth** — Aurum never modifies Actual's data. It reads and annotates.
- **Mirror, not manager** — surfaces patterns without guilt. "You spent X" not "You shouldn't spend X."
- **Receipt matching is best-effort** — when uncertain, ask rather than guess. Transparent confidence.
- **Privacy is non-negotiable** — financial data never leaves your machine. Local inference only.

**Relationship to Cairn:** Aurum could surface financial insights through Cairn's attention system — "heads up, your electricity bill was 2x normal" in the What Needs Attention pane. The Play could have a Finance Act with Scenes for budget reviews. Aurum's data enriches Cairn's understanding of your life without Cairn needing to understand finance directly.

---

#### Agent Pattern Summary

| Agent | Data Backbone | AI Layer | Cadence |
|-------|--------------|----------|---------|
| **Cairn** | Thunderbird (email/calendar/contacts) | Attention minding, memory, life organization | Always-on |
| **ReOS** | Linux system (procfs, systemd, packages) | Natural language system control | On-demand |
| **RIVA** | Git repos, project docs | Agent orchestration, plan enforcement | On-demand |
| **Assay** | RSS/Atom feeds | Dialectic scoring, article surfacing | 1-2x daily |
| **Aurum** | Actual Budget (bank sync) | Expense classification, receipt decomposition | Daily |

The pattern: **open-source tool handles data ingestion → local LLM adds intelligence → user stays in control.**

---

## What Makes Talking Rock Different

### vs Typical Cloud AI Assistants

| Aspect | Cloud AI (ChatGPT, Gemini, etc.) | Talking Rock |
|--------|----------------------------------|--------------|
| **Where data lives** | Their servers | Your machine only |
| **Who can see it** | The company and their partners | You, and no one else |
| **Cost** | $20+/month | Free forever |
| **Intent verification** | None — acts immediately | Always verified before execution |
| **Learning visibility** | Opaque | Every memory is visible and editable |
| **Optimization target** | Engagement, retention | Your goals, your attention |
| **Source** | Proprietary | Open source |
| **Model choice** | Their models, their terms | Any Ollama-compatible model |

### The Honest Tradeoff

| Dimension | Cloud AI | Talking Rock |
|-----------|----------|--------------|
| **Speed** | Fast (large remote models) | Slower (small local models) |
| **Cost** | $20–500/month | Free forever |
| **Privacy** | Your data leaves your machine | Your data never leaves your machine |
| **Trust** | Optimized for engagement | Optimized for verification |
| **Ownership** | Their cloud, their rules | Your machine, your data |
| **Learning** | Opaque, used to train their models | Transparent, editable, yours |

**What we can do that they can't:**

1. **Fully Local**: Your data never leaves your machine. Period.
2. **Verified Intent**: Every action is confirmed before execution.
3. **Auditable Learning**: Every memory CAIRN builds about you is visible and editable.
4. **Open Source**: Security audits, bug fixes, feature additions by community.
5. **No Rent**: One install, free forever.
6. **Small Footprint**: 8B models, 16GB RAM.

**User perception we design for:**
> "Takes longer than the cloud tools, but I trust it completely. It's mine."

---

## Development Principles

### From the Charter

> Talking Rock exists to protect, reflect, and return human attention.

Applied to CAIRN:
- **Protect**: Don't break things. Don't break trust. Diff preview, backups, verified intent.
- **Reflect**: Show reasoning. Inspector pane, influence logs, transparent memory.
- **Return**: Don't waste attention. Get it right, then get out of the way.

### Anti-Patterns We Avoid

1. **Engagement optimization**: We WANT users to finish and leave.
2. **Dependency creation**: We WANT users to learn and need us less.
3. **Lock-in**: We WANT users to be able to leave (but never want to).
4. **Black boxes**: We WANT users to understand how it works.
5. **Silent learning**: We WANT users to see and correct what CAIRN knows about them.

### Success Metrics

**We'll know we succeeded when:**
- Users trust CAIRN enough to let it act on their behalf.
- Users can see and edit everything CAIRN has learned about them.
- Users choose Talking Rock over paid cloud alternatives.
- Users contribute improvements back.

**Anti-metrics:**
- Session length (shorter is better if task is done).
- Retention (we want capability transfer, not dependency).
- "Engagement" (if they're done, they're done).

---

## Technical Decisions

### Why Python for the Kernel

- Ollama bindings are mature.
- AST parsing for Python/TS is well-supported.
- Same language as many target codebases.
- Rapid iteration during development.

### Why Tauri for the UI

- Native performance.
- Rust backend for speed-critical paths.
- Web frontend for rapid UI development.
- Cross-platform (Linux focus, but Windows/Mac possible).

### Why SQLite for Storage

- Zero configuration.
- Single file, easy backup.
- Fast enough for our needs.
- Vector extensions available (sqlite-vec).

### Why Ollama-Only

CAIRN uses Ollama exclusively for local inference. No cloud providers. This is not a technical limitation — it is a mission decision. The mission is local, zero trust AI. Cloud providers, however convenient, are incompatible with that mission. Ollama gives users full model choice (llama3.2, qwen, mistral, and many others) while keeping every inference on their hardware.

---

## Getting Involved

### For Contributors

1. **Read the Charter**: Understand the philosophy.
2. **Pick an issue**: Start small, grow from there.
3. **Follow the patterns**: Code style, testing, documentation.
4. **Ask questions**: We're happy to help.

### Priority Areas

- **Memory Editing UI**: Need TypeScript/Tauri skills.
- **Repository Map**: Need AST parsing expertise.
- **LSP Integration**: Need language server experience.
- **Diff Preview UI**: Need TypeScript/React skills.
- **Documentation**: Always welcome.

### Testing Strategy

- Unit tests for core logic.
- Integration tests for full flows.
- Local-only (no cloud calls).
- Temporary resources, isolated DB.

---

## Timeline

**Q1–Q4 2025: Foundation**
- [x] CAIRN intent pipeline (extract, verify, execute, respond)
- [x] Atomic operations framework (3x2x3 taxonomy)
- [x] The Play (Acts, Scenes, notebooks, context selection)
- [x] Safety layer (command blocking, risk assessment, circuit breakers)
- [x] Multi-layer verification pipeline
- [x] Health pulse system

**2026: Conversation Lifecycle & Memory (Complete)**
- [x] Phase 1: Conversation singleton and messages (active, close, archive)
- [x] Phase 2: Compression pipeline (entity extraction, narrative, state deltas, embeddings)
- [x] Phase 3: Memory storage and routing (Your Story, Act-directed, signal strengthening, correction chains)
- [x] Phase 4: Memory as reasoning context (augments classification, decomposition, verification)
- [x] Phase 5: Compounding loop (cross-conversation thread resolution, pattern learning)
- [x] Phase 6: Continuous conversation (per-turn assessor, state briefings, FTS5 search, temporal context)

See [Conversation Lifecycle Spec](./CONVERSATION_LIFECYCLE_SPEC.md) for full implementation details.

**Next: User-Facing Transparency**
- [ ] Memory editing UI (see, correct, delete every memory CAIRN holds)
- [ ] Diff preview UI (see changes before they happen)
- [ ] Inspector pane (which memories shaped this response)
- [ ] Streaming execution UI (watch the pipeline, pause at any step)

**Future: Deeper Capability**
- [ ] Repository map (dependency graph, semantic code search)
- [ ] LSP integration (real-time type feedback)
- [ ] Test-first contracts (generate test code as specification)
- [ ] Multi-path exploration (try several approaches, pick the best)
- [ ] Documentation lookup (prevent API hallucination)
- [ ] Plugin system
- [ ] Community patterns library

**Future: Specialized Agents**
- [ ] Assay — Dialectic-scored RSS feed reader
- [ ] Aurum — Financial awareness via Actual Budget

---

## Closing

Talking Rock isn't trying to be:
- A startup looking for exit
- A VC-funded growth machine
- A data collection operation disguised as a product

Talking Rock is:
- A tool that respects its users
- A project that believes in open source
- A proof that local, verified, auditable AI is not a compromise — it's the goal

The large cloud companies have more engineers, more compute, more data. But they also have shareholders to please, engagement to optimize, and your data to monetize.

We have none of that. Your data centers around you. Your intent is always verified. Your learning is always yours.

**That's the mission. Let's build it.**
