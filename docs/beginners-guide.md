# Beginner's Guide to Talking Rock

## What is Talking Rock?

Talking Rock is a local-first AI assistant with one agent: **CAIRN** — your personal attention minder and life organizer.

Everything runs on your machine. Your data never leaves. No accounts, no subscriptions, no surveillance. Small models, outsized impact — AI that partners with your values, not around them.

## Quick Start

### 1. Install Dependencies

```bash
# Ollama (local LLM)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2

# Python 3.12+
# (use your distro's package manager)
```

### 2. Install Talking Rock

```bash
git clone https://github.com/sefton37/cairn.git
cd cairn
pip install -e .
```

### 3. Run

```bash
# Start the desktop app
cd apps/cairn-tauri && npm install && npm run tauri:dev
```

## Your First Conversations

### With CAIRN (Attention Minder)

```
You: Create an act called "Side Projects"
CAIRN: Created Act "Side Projects". Want to add a Scene?

You: What needs my attention?
CAIRN: Based on your Play:
       - Scene "Review PR #42" is waiting on Alex since Monday
       - Scene "Learn Rust" has a session scheduled for tomorrow
```

CAIRN helps you organize without guilt-tripping. The Play uses two levels:
- **Acts** = Life narratives (months to years)
- **Scenes** = Calendar events that make up the moments
- **Your Story** = A permanent record of who you are, built from conversation memories

When you finish a conversation with CAIRN, it extracts the meaning — what was decided, what changed, what's open — and shows you before saving. Over time, CAIRN learns your patterns and gets better at understanding what you need.

## Key Principles

1. **Local-first** — All data stays on your machine, encrypted at rest
2. **Intent always verified** — Every action is classified and confirmed before execution
3. **Permission always requested** — Mutations are previewed and require your approval
4. **All learning auditable and editable by you** — Every memory CAIRN forms can be reviewed, corrected, or deleted
5. **Transparency** — Every action is explained, not just performed
6. **Non-coercive** — Surfaces options, never guilt-trips or gamifies

## Next Steps

- Set up The Play: `docs/the-play.md`
- Understand conversations & memory: `docs/CONVERSATION_LIFECYCLE_SPEC.md`
- Explore CAIRN architecture: `docs/cairn_architecture.md`

## Getting Help

- Issues: https://github.com/sefton37/talking_rock/issues
