# Parse Gate Architecture

Context-aware natural language command proposals for ReOS shell integration.

## Kernel Principles

1. **"Native until foreign. Foreign until confirmed."** - Bash handles commands natively; only unrecognized input goes to NL processing
2. **"If you can't verify it, decompose it."** - Check system state before proposing
3. **"Verify it's a command, or retry. Never propose garbage."** - Three-layer extraction

---

## The Problem

User says: `run gimp`

**Without context**: LLM might propose `sudo apt install gimp` (assumes not installed)

**With context**:
- If gimp installed → propose `gimp`
- If gimp NOT installed → propose `sudo apt install gimp`

---

## Architecture

```
User: "run gimp"
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│   CONTEXT LAYER                                              │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ 1. Intent Analysis                                     │ │
│   │    - Extract verb: "run", "install", "start"           │ │
│   │    - Extract target: "gimp"                            │ │
│   └───────────────────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ 2. Context Gathering (hierarchical lookup)            │ │
│   │    Level 1: which <target> → executable path          │ │
│   │    Level 2: dpkg -s <target> → package installed?     │ │
│   │    Level 3: apt-cache show → package available?       │ │
│   │    Level 4: systemctl show → is it a service?         │ │
│   │    Level 5: FTS5/semantic search → find by description│ │
│   └───────────────────────────────────────────────────────┘ │
│   ┌───────────────────────────────────────────────────────┐ │
│   │ 3. Context Decision                                    │ │
│   │    can_verify=True → enrich LLM prompt with context   │ │
│   │    can_verify=False → proceed with uncertainty flag    │ │
│   └───────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│   LLM PROMPT (enriched with context)                         │
│   "System Context:                                           │
│    - gimp: installed at /usr/bin/gimp                        │
│    Request: run gimp"                                        │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│   THREE-LAYER EXTRACTION                                     │
│   Layer 1: Sanitize (strip markdown, backticks, prefixes)   │
│   Layer 2: Validate (is it actually a command?)             │
│   Layer 3: Safety (block dangerous patterns)                │
└─────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│   USER CONFIRMATION                                          │
│   "Proposed: gimp"                                          │
│   "[y/n/e]: "                                               │
└─────────────────────────────────────────────────────────────┘
```

---

## Intent Pattern Matching

| Verb Pattern | Intent | Context Needed |
|--------------|--------|----------------|
| run, launch, open, execute | Run program | Is it in PATH? |
| install, add, get, download | Install package | Already installed? |
| remove, uninstall, delete, purge | Remove package | Is it installed? |
| start, restart, reload | Service control | Is it a service? |
| stop, kill, terminate | Service control | Is it a service? |
| enable, disable | Service config | Is it a service? |
| update, upgrade | Package update | Package manager type |

### Package Aliases

Common name mappings for user convenience:

```python
PACKAGE_ALIASES = {
    "chrome": "google-chrome-stable",
    "vscode": "code",
    "vs code": "code",
    "python": "python3",
    "node": "nodejs",
    "postgres": "postgresql",
}
```

---

## Hybrid Search Architecture

When exact matches fail, Parse Gate uses a hybrid search approach:

```
Query: "picture editor"
         │
         ▼
┌─────────────────────────────────────┐
│ Level 1: Exact Match (fastest)      │
│   which picture → NOT FOUND         │
│   which editor → NOT FOUND          │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Level 2: FTS5 Keyword Search (<10ms)│
│   "picture OR editor" in packages   │
│   Matches: packages with these words│
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Level 3: Semantic Vector Search     │
│   Embed query with MiniLM-L6-v2     │
│   Cosine similarity > 0.5           │
│   "picture editor" ≈ "GIMP" (0.72)  │
└─────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────┐
│ Result: GIMP - GNU Image            │
│         Manipulation Program        │
└─────────────────────────────────────┘
```

### FTS5 Full-Text Search

SQLite FTS5 indexes all installed packages and desktop applications:

```sql
-- Package search
CREATE VIRTUAL TABLE packages_fts USING fts5(
    name, description, is_installed, category,
    tokenize='porter unicode61'
);

-- Desktop app search
CREATE VIRTUAL TABLE desktop_apps_fts USING fts5(
    desktop_id, name, generic_name, comment, keywords,
    tokenize='porter unicode61'
);
```

**Data sources:**
- Installed packages from `dpkg-query`
- Desktop apps from `.desktop` files in `/usr/share/applications`

### Semantic Vector Search

For synonym matching when FTS5 fails:

```python
# Uses sentence-transformers (optional dependency)
model = SentenceTransformer("all-MiniLM-L6-v2")  # 22MB, fast

# Pre-computed embeddings stored in SQLite
CREATE TABLE semantic_embeddings (
    id TEXT PRIMARY KEY,
    source_type TEXT,      -- 'package' or 'desktop'
    name TEXT,
    description TEXT,
    embedding BLOB,        -- numpy float32 array
    indexed_at TEXT
);

# Query: embed and find nearest neighbors
query_embedding = model.encode("picture editor")
# Cosine similarity with stored embeddings
# Returns: GIMP (0.72), Inkscape (0.68), Krita (0.65)
```

---

## Context Output Format

The `ShellContext` dataclass formats context for the LLM:

```
System Context:
- gimp: executable at /usr/bin/gimp
- nginx service: active, enabled at boot
- nodejs: package installed (v18.19.0)
- unknown-app: NOT FOUND directly, but similar programs found:
  • GIMP: Create images and edit photographs
  • Inkscape: Vector graphics editor
```

---

## Safety Layer

Three-layer protection before any command is proposed:

### Layer 1: Output Sanitization
- Strip markdown code blocks (```bash ... ```)
- Remove backticks, prefixes ("Command:", "Run:")
- Handle multi-line responses

### Layer 2: Command Validation
- Reject if starts with articles/pronouns
- Reject questions (ends with ?)
- Reject prose (>15 words without shell operators)
- Must look like a plausible command

### Layer 3: Dangerous Pattern Blocking
```python
BLOCKED_PATTERNS = [
    r"rm\s+-rf\s+/\s*$",      # rm -rf /
    r"dd\s+if=.*of=/dev/sd",  # dd to disk
    r"mkfs\s+/dev/sd",        # format disk
    r":\(\)\s*\{.*\}",        # fork bombs
    r"chmod\s+-R\s+777\s+/",  # world-writable root
]
```

---

## Files

| File | Purpose |
|------|---------|
| `src/reos/shell_context.py` | Context gathering, intent analysis |
| `src/reos/shell_propose.py` | Command proposal with LLM |
| `src/reos/system_index.py` | FTS5 and semantic indexing |
| `scripts/reos-shell-integration.sh` | Bash integration |

---

## Example Flows

### Flow 1: "run gimp" (installed)
```
Intent: run, Target: gimp
Context: which gimp → /usr/bin/gimp ✓
LLM Prompt: "gimp is installed at /usr/bin/gimp. Request: run gimp"
Proposal: gimp
```

### Flow 2: "run gimp" (not installed)
```
Intent: run, Target: gimp
Context: which gimp → None, dpkg -s gimp → not installed
         apt-cache show gimp → available
LLM Prompt: "gimp is available but NOT installed. Request: run gimp"
Proposal: sudo apt install gimp
```

### Flow 3: "picture editor" (semantic search)
```
Intent: run, Target: picture editor
Context: No exact match found
         FTS5: No high-quality matches
         Semantic: GIMP (0.72), Inkscape (0.68)
LLM Prompt: "Similar programs found: GIMP (image editor). Request: picture editor"
Proposal: gimp
```

### Flow 4: "start nginx" (service)
```
Intent: service_start, Target: nginx
Context: systemctl show nginx → LoadState=loaded, ActiveState=inactive
LLM Prompt: "nginx is a systemd service, currently inactive. Request: start nginx"
Proposal: sudo systemctl start nginx
```

---

## Design Principles

1. **Fast path**: Skip context for unambiguous commands
2. **Fail open**: If context gathering fails, proceed without it
3. **Cache friendly**: Use steady state cache when available
4. **Hierarchical**: Check cheap lookups before expensive ones
5. **User confirms**: All proposals require user approval

---

## Dependencies

**Required:**
- SQLite with FTS5 (built-in)

**Optional:**
- `sentence-transformers` for semantic search
  ```bash
  pip install reos[semantic]
  ```

Without semantic search, Parse Gate still works with FTS5 keyword matching.
