# Talking Rock

## The Mission

> **Don't rent a data center. Center your data around you.**

Talking Rock is an AI assistant that runs entirely on your computer. Not a thin client connecting to someone else's servers—the actual AI, running locally, under your control.

**This is our competitive advantage.** Local inference isn't just about privacy (though you get that too). It's about economics:

- **Cloud AI costs money per token.** Every verification pass, every analysis, every safety check—they all cost the provider money. So they minimize them.
- **Local inference is essentially free.** Once you have the model, compute costs nothing extra. So we can verify every decision, analyze every context, check every action. Do things that subscription services can't afford at scale.

Big tech wants AI to be a subscription you pay forever. They collect your data, train on your conversations, and can change the rules anytime.

We believe AI should be:
- **Local** — The AI runs on your machine, not in a data center
- **Private** — Your conversations never leave your computer
- **Free** — No subscription, no "we changed our pricing"
- **Yours** — Open source, can't be taken away

**Our goal: Build the best AI assistant in the world. Then give it away.**

### A Mirror That Doesn't Sell Your Reflection

Every productivity tool asks: *"How can we capture what this person does?"*

Talking Rock asks: *"How can this person see themselves clearly?"*

**Zero trust. Local only. Encrypted at rest. Never phones home.**

The only report goes to the only stakeholder that matters: you.

---

## Development Priorities: Democratizing AI

True democratization means running on hardware people actually have. A 70B model that needs a $2000 GPU isn't democratized—it's just a different kind of paywall.

**Our target: 1B parameter models.** These run on 8GB RAM, integrated graphics, and five-year-old laptops. If your computer can run a web browser, it should be able to run Talking Rock.

### Current Priorities

| Priority | Agent | Target Model Size | Status |
|----------|-------|-------------------|--------|
| **1** | CAIRN | 1B parameters | Active development |

**Why 1B is the right target:**

CAIRN is an attention minder and life organizer. Surfacing tasks, managing priorities, understanding your context, and helping you focus are achievable at 1B parameters. The model needs to understand intent and match patterns, not generate complex code. This is where we deliver real value on minimal hardware.

**The honest reality:** We're prioritizing what we can ship on accessible hardware today, not what sounds impressive in a README.

---

## What Talking Rock Does

Talking Rock is CAIRN: a personal attention minder that helps you focus on what matters without overwhelming you.

You talk to CAIRN about your life—your projects, your priorities, what you're waiting on, what's coming up. CAIRN surfaces what needs your attention, keeps track of your context across conversations, and helps you see where you actually are without judging you for where you aren't.

**Why local matters here:** Because analysis and reasoning happen locally, every request can be examined and validated without cost concerns. Cloud services charge per token—we don't.

---

## CAIRN: The Attention Minder

**Thesis:** CAIRN helps you focus on what matters without overwhelming you. It shows you the next thing, not everything—and never guilt-trips you about what you haven't done.

**Target: 1B parameter models.** Surfacing and prioritization are pattern-matching tasks—achievable with smaller models.

### How CAIRN Works: The Journey of Your Day

**Step 1: You Ask What Needs Attention**
```
You: "What should I focus on today?"
```

**Step 2: CAIRN Checks Your Context**

CAIRN knows your life structure through "The Play":
```
[Context Check]
├─ Current Act: "Building my startup"
├─ Active Scene: "Launch MVP"
├─ Calendar: Meeting at 2pm, deadline Friday
├─ Waiting on: Response from designer
└─ Last touched: Database schema (3 days ago)
```

**Step 3: Smart Surfacing**

CAIRN surfaces what needs attention based on:
- What's blocking other work
- What has upcoming deadlines
- What you haven't touched recently (without guilt)
- What aligns with your stated priorities

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

CAIRN organizes everything with deliberate simplicity—just two levels:

| Level | Timeframe | Example |
|-------|-----------|---------|
| **Acts** | Life narratives (months to years) | "Building my startup", "Learning music" |
| **Scenes** | Calendar events within acts | "Launch MVP meeting", "Record vocals session" |

**Why just two levels?** To remove the temptation to obscure responsibility in complexity. Acts answer "What narrative does this belong to?" Scenes answer "When am I doing this?" That's enough.

This structure lets CAIRN understand context. When you say "what's next?", it knows which act you're in and what scenes are coming up.

### Core Capabilities

- **Project tracking** — Acts and Scenes with status and priority
- **Calendar integration** — Syncs with Thunderbird (including recurring events)
- **Contact knowledge** — Knows who's involved in what
- **Waiting-on tracking** — Knows what you're blocked on
- **Document knowledge base** — Import PDFs, Word docs, and more for semantic search
- **Coherence Kernel** — Filters distractions based on your stated identity and goals
- **Health Pulse** — Monitors data freshness, calibration alignment, and system health across three axes; surfaces findings through chat ("how are you doing?") and a passive UI indicator without intrusive nagging
- **Conversation Lifecycle** — One conversation at a time with deliberate closure; meaning is extracted and woven into your ongoing narrative
- **Memory Architecture** — Compressed meaning from conversations becomes active reasoning context for all future interactions
- **Your Story** — A permanent Act representing who you are across all other Acts, built from accumulated conversation memories

### Conclusion

CAIRN is a calm, non-judgmental life organizer. It respects your attention by showing you the next thing—not a wall of everything you haven't done. It's a mirror for self-reflection, not a surveillance tool that reports on you. Because it runs locally, your life data stays on your machine. No company sees your priorities, your goals, or your struggles.

---

## Safety: You're Always in Control

**Thesis:** Talking Rock has safety limits that can be tuned but not disabled. You approve every change, and everything runs locally where you can see exactly what's happening.

### Approval Required

- **Preview before changes** — See exactly what will change before any file is modified
- **Explicit approval** — All changes need your OK
- **Automatic backups** — Every modified file is backed up
- **Undo anything** — Rollback any change

### Built-in Limits

| Protection | Default | Tunable Range |
|------------|---------|---------------|
| Max iterations per task | 10 | 3-50 |
| Max run time | 5 minutes | 1-30 minutes |
| Auth attempts (rate limit) | 5/minute | N/A |

### Privacy by Architecture

Because Talking Rock runs locally:
- **No tracking** — We don't know you exist
- **No data collection** — Your conversations stay on your machine
- **No training** — Your data is never used to train models
- **Open source** — Read every line of code

**This isn't a privacy policy—it's architecture.** There's no server to send data to.

---

## Getting Started

### Quick Install (Experienced Users)

```bash
# 1. Install Ollama (runs AI models locally)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2:1b

# 2. Clone and install Talking Rock
git clone https://github.com/sefton37/talking-rock
cd talking-rock
pip install -e .

# 3. Run the app
cd apps/cairn-tauri
npm install
npm run tauri:dev
```

### Step-by-Step Install (Beginners)

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
# Clone the code
git clone https://github.com/sefton37/talking-rock
cd talking-rock

# Install Python dependencies
pip install -e .

# Install the desktop app
cd apps/cairn-tauri
npm install
```

**Step 3: Run It**

```bash
npm run tauri:dev
```

A window will open. Start talking to CAIRN!

---

## Is This For You?

Talking Rock is for you if:
- You want an AI assistant that respects your privacy
- You're tired of subscription fatigue
- You want a calm, non-judgmental organizer for your life
- You have modest hardware (8GB RAM, no GPU required)
- You believe software should work for users, not advertisers

### Requirements

- Linux (Ubuntu, Fedora, Mint, Arch, etc.)
- Python 3.12+
- 8GB RAM
- 10GB disk space
- No GPU required

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

---

## What's Built

### CAIRN (Attention Minder) — Active Development
- [x] The Play hierarchy (Acts → Scenes, 2-tier)
- [x] Smart surfacing ("what needs attention")
- [x] Calendar integration (Thunderbird)
- [x] Contact knowledge graph
- [x] Document knowledge base (PDF, DOCX, TXT, MD, CSV, XLSX)
- [x] Coherence Kernel for distraction filtering
- [x] 45 MCP tools
- [x] Conversation lifecycle (singleton constraint, closure, compression pipeline)
- [x] Memory architecture (extraction, routing, Your Story, semantic search)
- [x] Memory-augmented reasoning (memories inform classification, decomposition, verification)
- [ ] 1B model optimization and testing

### Infrastructure
- [x] Automatic backups and undo
- [x] Context preservation across conversations

---

## Documentation

### Foundation (Start Here)

- **[Foundation](docs/FOUNDATION.md)** — Core philosophy and architecture overview
- [Atomic Operations](docs/atomic-operations.md) — 3x2x3 classification taxonomy
- [Verification Layers](docs/verification-layers.md) — Verification system

### Getting Started

- [Beginner's Guide](docs/beginners-guide.md) — New to Linux? Start here
- [App Vision](docs/app-vision.md) — What we're building and why

### Agent Architecture

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

*Talking Rock: Local AI, real ownership, accessible hardware.*
