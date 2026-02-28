# Talking Rock Foundation

> **The philosophical and architectural bedrock for Talking Rock's AI assistant system.**

This document describes the core principles and architecture of Cairn. For detailed implementation, see the linked specialized documents.

---

## Mission

> **Center your data around you, not in a data center, so that your attention is centered on what you value. Local, zero trust AI. Small models and footprint, outsized impact and trust.**

## Vision

> **AI that partners with you and your values, not to automate you. Intent always verified, permission always requested, all learning available to be audited and edited by you.**

Talking Rock is an AI assistant that runs entirely on your computer. Not a thin client connecting to someone else's servers — the actual AI, running locally, under your control.

**Local isn't just about privacy (though you get that too). It's about ownership of your own data and the trust that only comes from it:**

- **When your data is centered around you**, no one else can read your conversations, train on your patterns, or sell your attention. The architecture makes this true by default, not by policy.
- **When inference is local and free**, every intent can be verified before execution, every classification decision can be inspected, and every memory the system builds about you can be read, corrected, or deleted. You audit the AI that knows you.
- **Small models on accessible hardware** — 1B parameters, 8GB RAM, no GPU — mean this isn't a privilege for the well-resourced. Outsized impact from a small footprint.

---

## The Kernel Principle

> **"If you can't verify it, decompose it."**

This single recursive rule governs all of Talking Rock's operations. Instead of prescribing complexity levels, levels emerge from recursive application of this constraint:

1. Can you verify this operation directly?
2. If yes → execute and verify
3. If no → decompose into smaller operations and repeat

This principle manifests in CAIRN's attention minding: complex attention demands are decomposed into verifiable coherence facets.

---

## Atomic Operations Architecture

Every user request is decomposed into **atomic operations**—the smallest meaningful units of work that can be classified, verified, and executed.

### The 3x2x3 Taxonomy

Each atomic operation is classified along three dimensions:

| Dimension | Options | Description |
|-----------|---------|-------------|
| **Destination** | `stream`, `file`, `process` | Where does output go? |
| **Consumer** | `human`, `machine` | Who consumes the result? |
| **Execution Semantics** | `read`, `interpret`, `execute` | What action is taken? |

**Examples:**
- "Show memory usage" → `(stream, human, read)` — display to user
- "Save this to notes.txt" → `(file, human, execute)` — persistent output for human
- "Run pytest" → `(process, machine, execute)` — spawn process for machine verification

See [Atomic Operations](./atomic-operations.md) for the complete taxonomy and classification pipeline.

---

## Agents as Operation Generators

CAIRN doesn't replace atomic operations — it **generates** them:

```
User Request
     │
     ▼
┌──────────────────────────────────────────────────────┐
│                  Agent Layer                          │
│               ┌────────────────┐                     │
│               │     CAIRN      │                     │
│               │   Attention    │                     │
│               │    Minder      │                     │
│               └───────┬────────┘                     │
│                       │                              │
│                       ▼                              │
│           ┌──────────────────────┐                   │
│           │  Atomic Operations   │                   │
│           │  (stream/file/proc)  │                   │
│           │  (human/machine)     │                   │
│           │  (read/interp/exec)  │                   │
│           └──────────────────────┘                   │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│              Verification Pipeline                    │
│  Syntax → Semantic → Behavioral → Safety → Intent    │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│              Execution + RLHF Feedback               │
└──────────────────────────────────────────────────────┘
                        │
                        ▼
┌──────────────────────────────────────────────────────┐
│         Conversation Lifecycle & Memory               │
│  Conversation → Compression → Memory → Reasoning     │
│  (Memories feed back into Classification pipeline)   │
└──────────────────────────────────────────────────────┘
```

### CAIRN: The Attention Minder

**Target: 1B parameters.** Surfacing and prioritization are pattern-matching tasks.

CAIRN helps you focus on what matters by:
- Surfacing the **next thing**, not everything
- Filtering through your stated identity (Coherence Kernel)
- Managing calendar/contacts via Thunderbird integration

CAIRN generates operations like:
- `CALENDAR` intents → `(stream, human, read)` for queries
- `PLAY` intents → `(file, human, execute)` for Scene creation

See [CAIRN Architecture](./cairn_architecture.md) for details.

---

## The Verification Pipeline

Every atomic operation passes through five verification layers:

| Layer | Purpose | Example Check |
|-------|---------|---------------|
| **Syntax** | Structurally valid? | Valid bash/Python syntax |
| **Semantic** | Makes logical sense? | File exists before edit |
| **Behavioral** | Expected side effects? | Command produces output |
| **Safety** | Safe to execute? | No dangerous patterns |
| **Intent** | Matches user's goal? | ML intent verification |

See [Verification Layers](./verification-layers.md) for the complete verification system.

---

## Conversation Lifecycle & Memory Architecture

Every AI chat interface treats conversations as disposable infinities. Talking Rock rejects this. A conversation is a unit of meaning with a beginning, a middle, and a deliberate end.

### Conversation Lifecycle

One conversation at a time. When it ends, the meaning is extracted, compressed, and woven into the user's ongoing narrative:

```
active → ready-to-close → compressing → archived
```

The compression pipeline runs multiple local LLM passes — entity extraction, narrative synthesis, state delta computation, embedding generation — all at zero marginal cost because inference is local.

### Memories as Reasoning Context

Memories are not passive records. They are the reference corpus for all reasoning. Every time Talking Rock processes a request — classifying intent, decomposing into atomic operations, verifying understanding — it searches the memory database. This is the feedback loop that makes the system compound in value:

```
Conversation → Memory → Reasoning Context → Better Understanding → Better Conversation → Richer Memory
```

### Your Story

Your Story is the permanent, un-archivable Act that represents *you* across all other Acts. It is the default destination for memories that don't belong to a specific project. Over time, Your Story becomes the primary source Talking Rock uses to understand who you are — distinct from what you're doing.

See [Conversation Lifecycle](./CONVERSATION_LIFECYCLE_SPEC.md) for the complete memory architecture.

---

## Learning from Feedback (RLHF)

Talking Rock learns from user feedback at multiple levels:

| Feedback Type | Signal | Strength |
|---------------|--------|----------|
| **Explicit Rating** | User rates 1-5 | Medium |
| **Correction** | User fixes classification | High |
| **Approval** | User approves/rejects | Medium |
| **Behavioral** | Retry, undo, abandon | High |
| **Long-term** | Persisted, reused, referenced | Highest |

See [RLHF Learning](./rlhf-learning.md) for the complete learning system.

---

## Philosophy: A Mirror, Not a Manager

> Every productivity tool asks: *"How can we capture what this person does?"*
>
> Talking Rock asks: *"How can this person see themselves clearly?"*

### Non-Coercion Principles

1. **Never guilt-trip** — "You haven't touched X in 30 days" → "X is waiting when you're ready"
2. **User decides priority** — System surfaces the need, user sets the number
3. **Defer is valid** — "Not now" is a legitimate response
4. **Completion isn't the only goal** — Some items are ongoing, some get archived unfinished

### Privacy by Architecture

Because Talking Rock runs locally:
- **No tracking** — We don't know you exist
- **No data collection** — Your conversations stay on your machine
- **No training** — Your data is never used to train models
- **Open source** — Read every line of code

**This isn't a privacy policy—it's architecture.** There's no server to send data to.

---

## Two-Tier Simplicity (The Play)

The Play uses a deliberately simple two-tier structure:

| Level | Timeframe | Purpose |
|-------|-----------|---------|
| **Acts** | Months to years | Life narratives |
| **Scenes** | Calendar events | When you're doing things |

**Your Story** is a special permanent Act that cannot be archived. It represents *you* — not what you're working on, but who you are. It is the default destination for conversation memories that don't belong to a specific Act.

**Why just two levels?** To remove the temptation to obscure responsibility in complexity.

See [The Play](./the-play.md) for the complete organizational system.

---

## Foundation Documents

| Document | Content |
|----------|---------|
| [The Reduction Hypothesis](./the-reduction-hypothesis.md) | Canonical form + local compute as parallel reductions of noise |
| [Atomic Operations](./atomic-operations.md) | 3x2x3 taxonomy and classification pipeline |
| [Conversation Lifecycle](./CONVERSATION_LIFECYCLE_SPEC.md) | Conversation lifecycle, memory extraction, and reasoning integration |
| [Verification Layers](./verification-layers.md) | 5-layer verification system |
| [RLHF Learning](./rlhf-learning.md) | Feedback collection and learning loop |
| [Classification](./classification.md) | LLM-native classification with few-shot learning |
| [Migration Guide](./migration-new-packages.md) | New top-level package structure |

## Agent Documentation

| Document | Agent |
|----------|-------|
| [CAIRN Architecture](./cairn_architecture.md) | Attention minder |
| [The Play](./the-play.md) | Life organization |

## Reference Documentation

| Document | Content |
|----------|---------|
| [Security](./security.md) | Safety limits and protections |
| [Testing Strategy](./testing-strategy.md) | Test approach |

---

*Talking Rock: Center your data around you. Center your attention on what you value.*
