# Talking Rock Desktop App Vision

## Mission

**Center your data around you, not in a data center, so that your attention is centered on what you value.**

Local, zero-trust AI. Small models and small footprint. Outsized impact and trust.

## Vision

AI that partners with you and your values — not to automate you. Intent always verified, permission always requested, all learning available to be audited and edited by you.

### A Mirror That Doesn't Sell Your Reflection

Every productivity tool asks: *"How can we capture what this person does?"*

Talking Rock asks: *"How can this person see themselves clearly?"*

**Zero trust. Local only. Encrypted at rest. Never phones home.**

The only report goes to the only stakeholder that matters: you.

---

## Core Pillars

### 1. Onboarding & Configuration
**Get Talking Rock to know you and your system**

- **First Run Experience**:
  - Check for Ollama installation
  - Guide user through `ollama pull llama3.2` (or model of choice)
  - Test connectivity and model response
  - Run initial system snapshot (packages, services, containers)
  - Set preferences (auto-approve safe commands, learning mode, etc.)

- **System Discovery**:
  - Automatically detect distro, package manager, installed software
  - Build initial RAG context from system state
  - Offer to set up shell integration (optional)

- **Settings Panel**:
  - Model selection (switch between llama3.2, qwen, mistral, etc.)
  - Safety preferences (circuit breaker limits, sudo prompts)
  - Privacy settings (what to snapshot, log retention)
  - Learning mode toggle (show/hide command breakdowns)

### 2. Conversational Interface
**Talk to CAIRN — your attention minder and life organizer**

- **Chat Window** (center pane):
  - Natural language input — CAIRN is your conversational partner
  - Intent is always verified before any action is taken
  - Command preview boxes (approve/reject/explain) when CAIRN proposes actions
  - Live output streaming during execution
  - Post-execution summaries (what changed, how to undo)
  - Learning tooltips (command breakdowns, pattern explanations)

- **Conversation Lifecycle** (see [Conversation Lifecycle Spec](./CONVERSATION_LIFECYCLE_SPEC.md)):
  - One conversation at a time — depth over breadth
  - Deliberate closure with meaning extraction
  - Memory review: you see and edit what the system learned before it's kept
  - Memories feed back into future conversations as reasoning context

- **Context Awareness**:
  - System state automatically included (failed services, low disk, etc.)
  - The Play context (current Act, related projects)
  - Conversation memories (retrieved via semantic search for disambiguation)
  - Conversation history (refer to "it", "that service", "the error from before")

### 3. The Play (CAIRN's Domain)
**Your two-tier organizational system**

- **Structure** (deliberately simple):
  - **Acts** = Life narratives (months to years)
  - **Scenes** = Calendar events that define the narrative's journey
  - Markdown notebooks at each level

- **Philosophy**:
  - Two levels prevent obscuring responsibility in complexity
  - Acts answer "What narrative does this belong to?"
  - Scenes answer "When am I doing this?"

- **CAIRN Features**:
  - Activity tracking (when you last touched things)
  - Calendar sync with Thunderbird (including recurring events)
  - Priority surfacing without guilt-tripping
  - Coherence kernel filtering (blocks distractions based on identity)
  - Health monitoring across 3 axes (context freshness, calibration alignment, system integrity) — surfaces findings through chat ("how are you doing?") and a passive UI indicator, never nagging

- **Navigation**:
  - Tree view of Acts/Scenes
  - Quick access to recent items
  - Contact knowledge graph (people ↔ projects)

### 4. Inspector Pane
**Full transparency for every response**

- Click any response to see:
  - What context was provided
  - What tools were called
  - What alternatives were considered
  - Why this approach was chosen
  - Which memories influenced the reasoning
  - Confidence level

Everything CAIRN does is auditable. Nothing is hidden.

---

## UI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  Talking Rock                                Settings | Help     │
├──────────────┬──────────────────────────────┬───────────────────┤
│              │                              │                   │
│  Nav Panel   │      Chat / Main View        │  Inspector Pane   │
│              │                              │                   │
│ The Play     │  User: What should I focus   │  [Click response  │
│ ├─ Act 1     │        on today?             │   to see trail]   │
│ │  ├─ Scene  │                              │                   │
│ └─ Act 2     │  CAIRN: Based on your Play   │  Context Used:    │
│    └─ Scene  │  and recent memories, here's │  - The Play       │
│              │  what needs attention...     │  - 3 memories     │
│              │                              │                   │
│ Recent       │  User: Add a scene for the   │  Tools Called:    │
│ ├─ Planning  │        Thursday review       │  - play_surface   │
│ └─ Health    │                              │  - create_scene   │
│              │  CAIRN: I'll create that.    │                   │
│ Health       │  Confirm?                    │  Intent verified  │
│  ● Good      │                              │  before action    │
│              │  [Yes] [No] [Edit]           │                   │
│              │                              │  Confidence: 95%  │
└──────────────┴──────────────────────────────┴───────────────────┘
```

---

## User Journeys

### Journey 1: First-Time Setup
1. User launches Talking Rock
2. Welcome screen: "Let's set up Talking Rock"
3. Check: Is Ollama installed? → If not, guide to install
4. Check: Models available? → Guide to `ollama pull llama3.2`
5. Test: Can we connect and get a response?
6. Scan: Initial system snapshot (takes 10s)
7. Done: "Talking Rock is ready. Start by telling CAIRN about yourself."

### Journey 2: Daily Planning (CAIRN)
1. User opens Talking Rock
2. If an active conversation exists, CAIRN resumes it ("We were discussing...")
3. If no active conversation, CAIRN surfaces: "Good morning. Based on your memories and Play, here's what needs attention..."
4. Startup greeting is memory-driven: open threads, waiting-ons, recent decisions, stale items — all sourced from accumulated conversation memories
5. User asks clarifying questions
6. CAIRN verifies intent before any changes, asks permission before acting
7. User updates priorities based on their own decisions — CAIRN surfaces options, never mandates
8. When done, user closes the conversation; meaning is extracted, reviewed, and routed to an Act or Your Story

---

## What Makes Talking Rock Different

### vs. Terminal Emulators
- Understands **intent**, verifies it, asks permission before executing
- The Play for life organization
- Inspector pane for full transparency
- Every decision is auditable

### vs. AI Chat Apps
- Knows **YOUR context** (not generic advice)
- Actions require **your approval** (intent verified, permission requested)
- Safety is **built-in** (circuit breakers, previews)
- Everything is **local** (no cloud, no privacy leak)
- All learning is **visible and editable** by you

### vs. Productivity Apps
- **Data sovereignty**: Your data lives on your machine, full stop
- **Partnership, not automation**: CAIRN surfaces options and verifies intent — you decide
- **Auditable AI**: Every memory, every inference, every decision trail is open to inspection
- **Non-coercive**: Surfaces options, never guilt-trips
- **Identity-aware**: Coherence kernel filters distractions based on your values

---

## The Honest Tradeoff: Speed vs. Trust

Talking Rock doesn't try to beat big tech on speed. We optimize for **verification and user sovereignty**.

| Dimension | Big Tech | Talking Rock |
|-----------|----------|--------------|
| **Speed** | 5-15 seconds | 15-45 seconds |
| **Cost** | $20-500/month | Free |
| **First-try success** | 90-95% | 85-90% (but safer) |
| **Ownership** | Their cloud, their rules | Your machine, your data |
| **Trust** | Optimized for speed | Optimized for verification |
| **Learning** | Opaque, inaccessible | Visible, editable by you |

**The user perception we're designing for:**
> "Takes longer and sometimes needs tweaking, but it checks its work, I own everything, and I can see exactly what it learned about me."

**Value proposition:** All you need is patience.

---

## Design Principles

### 1. Calm Technology
- No urgent red alerts, no stress inducement
- Gentle notifications, user always in control
- Metrics inform, they don't judge

### 2. Progressive Disclosure
- Simple queries get simple answers
- Click for details (inspector pane)
- Learning mode is optional, not forced

### 3. Capability Transfer
- Show commands, explain patterns
- Celebrate when users "graduate"
- Success = user needs Talking Rock less over time

### 4. Local-First Always
- No cloud calls for core features
- User owns all data
- Works offline (except Ollama model download)

### 5. Transparent AI
- Every response shows reasoning trail
- No hidden decisions
- User can audit everything — including every memory CAIRN has formed about them

---

## Success Metrics

**We'll know Talking Rock is working when:**

1. **First-time users** set up and complete a task in <10 minutes
2. **Learning happens**: Users type raw commands instead of asking
3. **Trust is built**: Users approve actions because they see the reasoning
4. **CAIRN helps**: Users report feeling less overwhelmed, not more
5. **Sovereignty is real**: Users have reviewed, edited, or rejected at least one memory

**What we DON'T measure:**
- Daily active usage (less is good if they learned!)
- Actions executed (manual > automated for learning)
- Time in app (efficiency is the goal)

---

## Closing Thoughts

> **Don't rent a data center. Center your data around you.**

Talking Rock is not trying to replace your brain or make decisions for you.

It's trying to make your attention **organized**, your values **reflected**, and your AI partnership **honest** — all through a local, private, transparent AI companion that works for you.

**CAIRN** helps you see what matters, surfaces open threads, and verifies intent before acting. Over time, you need it less because you've internalized the patterns. Meanwhile, CAIRN understands you more because each conversation's meaning is extracted, reviewed by you, and woven into your ongoing narrative — creating a compounding loop of better understanding.

That's not a bug. That's the whole point.

*Talking Rock: AI that partners with you, on your terms.*
