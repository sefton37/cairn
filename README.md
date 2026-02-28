# Talking Rock

> **Mission:** Center your data around you, not in a data center, so that your attention is centered on what you value. Local, zero trust AI. Small models and footprint, outsized impact and trust.

> **Vision:** AI that partners with you and your values, not to automate you. Intent always verified, permission always requested, all learning available to be audited and edited by you.

---

## Why This Exists

Big tech wants AI to be a subscription you pay forever. They collect your data, train on your conversations, and can change the rules anytime. They optimize for engagement, not for you.

Talking Rock is the opposite. The AI runs on your machine. Your data never leaves. There is no server to send it to, no company that sees your priorities, your goals, or your struggles.

**This isn't a privacy policy. It's architecture.** There's no data center involved.

### A Mirror, Not a Manager

Every productivity tool asks: *"How can we capture what this person does?"*

Talking Rock asks: *"How can this person see themselves clearly?"*

The only report goes to the only stakeholder that matters: you.

---

## What Talking Rock Does

Talking Rock is **CAIRN**: a personal attention minder that helps you focus on what you value without overwhelming you.

You talk to CAIRN about your life — your projects, your priorities, what you're waiting on, what's coming up. CAIRN surfaces what needs your attention, keeps track of your context across conversations, and helps you see where you actually are without judging you for where you aren't.

### How It Works

**You ask what needs attention:**
```
You: "What should I focus on today?"
```

**CAIRN checks your context** through "The Play" — your two-tier life organization system:
```
[Context Check]
├─ Current Act: "Building my startup"
├─ Active Scene: "Launch MVP"
├─ Calendar: Meeting at 2pm, deadline Friday
├─ Waiting on: Response from designer
└─ Last touched: Database schema (3 days ago)
```

**CAIRN surfaces what matters** based on what's blocking other work, what has deadlines, and what aligns with your stated priorities — without guilt:
```
[Today's Focus]
1. Database schema needs review (blocking frontend work)
2. Designer response expected today
3. Friday deadline: MVP demo prep

Waiting for you when ready:
- Marketing copy draft
- Test coverage improvements
```

### The Play: Your Life Structure

Two levels. That's it.

| Level | Timeframe | Example |
|-------|-----------|---------|
| **Acts** | Life narratives (months to years) | "Building my startup", "Learning music" |
| **Scenes** | Calendar events within acts | "Launch MVP meeting", "Record vocals session" |

**Why just two levels?** To remove the temptation to obscure responsibility in complexity. Acts answer "What narrative does this belong to?" Scenes answer "When am I doing this?" That's enough.

### Core Capabilities

- **Smart surfacing** — Shows you the next thing, not everything
- **Calendar integration** — Syncs with Thunderbird (including recurring events)
- **Contact knowledge** — Knows who's involved in what
- **Waiting-on tracking** — Knows what you're blocked on
- **Document knowledge base** — Import PDFs, Word docs, and more for semantic search
- **Coherence Kernel** — Filters distractions based on your stated identity and goals
- **Health Pulse** — Monitors data freshness and calibration without nagging
- **Conversation lifecycle** — One conversation at a time with deliberate closure; meaning is extracted and woven into your ongoing narrative
- **Memory architecture** — Compressed meaning from conversations becomes active reasoning context, auditable and editable by you
- **Your Story** — A permanent record of who you are, built from accumulated conversation memories

---

## Safety: Intent Verified, Permission Requested, Learning Auditable

These aren't features. They're the architecture.

### Intent Always Verified

Every request passes through a 5-layer verification pipeline (Syntax, Semantic, Behavioral, Safety, Intent) before anything happens. Because inference is local, verification is free — so we verify everything.

### Permission Always Requested

- **Preview before changes** — See exactly what will change before any file is modified
- **Explicit approval** — All changes need your OK
- **Automatic backups** — Every modified file is backed up
- **Undo anything** — Rollback any change

### All Learning Auditable and Editable

When a conversation ends, CAIRN extracts the meaning — what was decided, what changed, what's open. You see every extracted memory before it is stored. You can edit, redirect, or reject any of it. Which memories influenced which decisions is traceable. Nothing is learned behind your back.

### Built-in Limits

| Protection | Default | Tunable Range |
|------------|---------|---------------|
| Max iterations per task | 10 | 3-50 |
| Max run time | 5 minutes | 1-30 minutes |
| Auth attempts (rate limit) | 5/minute | N/A |

---

## Small Models, Outsized Impact

True democratization means running on hardware people actually have. A 70B model that needs a $2000 GPU isn't democratized — it's just a different kind of paywall.

**Target: 1B parameter models.** These run on 8GB RAM, integrated graphics, and five-year-old laptops. If your computer can run a web browser, it should be able to run Talking Rock.

CAIRN is an attention minder. Surfacing tasks, managing priorities, understanding your context, and helping you focus are achievable at 1B parameters. The model needs to understand intent and match patterns, not generate complex code.

Because inference is local, it's essentially free after download. Every verification pass, every analysis, every safety check costs nothing extra. Cloud services charge per token and minimize verification to save money. We can verify every decision, analyze every context, check every action — because the economics don't punish thoroughness.

---

## Getting Started

### Quick Install

```bash
# 1. Install Ollama (runs AI models locally)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

# 2. Clone and install Talking Rock
git clone https://github.com/sefton37/talking-rock
cd talking-rock
pip install -e .

# 3. Run the desktop app
cd apps/cairn-tauri
npm install
npm run tauri:dev
```

### Step-by-Step (Beginners)

**Step 1: Install Ollama**

Ollama lets you run AI models on your own computer. Open a terminal and paste:
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

Then download a small model:
```bash
ollama pull llama3.2:1b
```

**Step 2: Install Talking Rock**

```bash
git clone https://github.com/sefton37/talking-rock
cd talking-rock
pip install -e .
cd apps/cairn-tauri
npm install
```

**Step 3: Run It**

```bash
npm run tauri:dev
```

A window will open. Start talking to CAIRN.

### Requirements

- Linux (Ubuntu, Fedora, Mint, Arch, etc.)
- Python 3.12+
- 8GB RAM
- 10GB disk space
- No GPU required

---

## Is This For You?

Talking Rock is for you if:
- You want an AI that partners with your values, not one that automates you
- You're tired of subscription fatigue
- You want a calm, non-judgmental organizer for your life
- You have modest hardware (8GB RAM, no GPU required)
- You believe your data should be centered around you, not in a data center

### How It Compares

| Feature | ChatGPT | Copilot | Talking Rock |
|---------|---------|---------|--------------|
| Works offline | No | No | **Yes** |
| Your data stays private | No | No | **Yes** |
| Free forever | No | No | **Yes** |
| Open source | No | No | **Yes** |
| Runs on 8GB RAM | N/A | N/A | **Yes** |
| Life organization | No | No | **Yes** |
| Learns from conversations | No | No | **Yes** |
| Learning auditable/editable | No | No | **Yes** |
| Intent verified before action | No | No | **Yes** |

---

## What's Built

### CAIRN (Attention Minder) — Active Development
- [x] The Play hierarchy (Acts and Scenes, 2-tier)
- [x] Smart surfacing ("what needs attention")
- [x] Calendar integration (Thunderbird)
- [x] Contact knowledge graph
- [x] Document knowledge base (PDF, DOCX, TXT, MD, CSV, XLSX)
- [x] Coherence Kernel for distraction filtering
- [x] 45 MCP tools
- [x] Conversation lifecycle (singleton constraint, closure, compression pipeline)
- [x] Memory architecture (extraction, routing, Your Story, semantic search)
- [x] Memory-augmented reasoning (memories inform classification, decomposition, verification)
- [x] Health Pulse (data freshness, calibration, system health — no nagging)
- [ ] 1B model optimization and testing

### Infrastructure
- [x] 5-layer verification pipeline (intent always verified)
- [x] Approval workflow (permission always requested)
- [x] Memory review gate (all learning auditable and editable)
- [x] Automatic backups and undo
- [x] Context preservation across conversations

---

## Documentation

### Foundation
- **[Foundation](docs/FOUNDATION.md)** — Core philosophy and architecture
- [Atomic Operations](docs/atomic-operations.md) — 3x2x3 classification taxonomy
- [Verification Layers](docs/verification-layers.md) — 5-layer verification system

### Getting Started
- [Beginner's Guide](docs/beginners-guide.md) — New to Linux? Start here
- [App Vision](docs/app-vision.md) — What we're building and why

### Architecture
- [CAIRN Architecture](docs/cairn_architecture.md) — Attention minder design
- [Conversation Lifecycle](docs/CONVERSATION_LIFECYCLE_SPEC.md) — Conversation lifecycle, memory extraction, and Your Story
- [The Play](docs/the-play.md) — Life organization system

### Reference
- [Security Design](docs/security.md) — How we protect your system
- [Classification](docs/classification.md) — LLM-native 3x2x3 taxonomy
- [Technical Roadmap](docs/tech-roadmap.md) — Development plans

---

## Contributing

Talking Rock is open source (MIT license). We welcome:
- Bug reports and feature requests
- Code contributions (especially CAIRN optimization)
- Documentation improvements
- Testing on different Linux distributions
- Small model benchmarking and optimization

See [CONTRIBUTING.md](.github/CONTRIBUTING.md) for guidelines.

**Current focus areas:**
1. CAIRN performance on 1B models
2. Prompt engineering for small models
3. Hardware compatibility testing

---

## License

MIT — Do whatever you want with it.

---

*Talking Rock: Center your data around you. Center your attention on what you value.*
