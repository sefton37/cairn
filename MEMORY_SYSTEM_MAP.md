# Cairn Memory System - Complete Architecture Map

**Author:** Scout (Codebase Reconnaissance)  
**Date:** 2026-03-20  
**Scope:** Conversation turn → assessment → extraction → storage → retrieval → context injection

---

## Executive Summary

Cairn's memory system is a 4-stage local inference pipeline that converts conversation turns into persistent, searchable knowledge. The pipeline runs asynchronously (zero latency to user), deduplicates memories via embedding similarity + LLM judgment, and injects contextual knowledge into every conversation turn.

**Key Innovation:** Memories are *reasoning context*, not passive storage. Every classification, decomposition, and verification pass searches memory. This creates a feedback loop: Conversation → Memory → Better Context → Better Understanding.

---

## 1. TurnDeltaAssessor (Per-Turn Memory Capture)

**File:** `src/cairn/services/turn_delta_assessor.py` (495 lines)

### What It Does
After CAIRN responds to a user message, lightweight LLM classification (temperature=0.1) decides if new knowledge emerged. If yes, creates a memory immediately via `MemoryService.store()`.

### Design Decisions
- **Two-state only:** `NO_CHANGE` vs `CREATE` (no UPDATE). Deduplication happens later.
- **Conservative classification:** Questions, casual chat, and re-statements default to NO_CHANGE.
- **JSON parse failures safe:** Defaults to NO_CHANGE, never raises.
- **All new memories are pending_review:** User gates them before reasoning context injection.
- **Background execution:** Runs in daemon thread via `TurnAssessmentQueue`. Zero latency impact on chat.

### Data Flow

```
User message + CAIRN response
    ↓
TurnDeltaAssessor.assess_turn()
    ├─ _classify_turn() [Ollama chat_json, temp=0.1]
    │   → Returns (assessment: 'NO_CHANGE'|'CREATE', what: description)
    │
    ├─ [if CREATE] _extract_and_store()
    │   ├─ Runs CompressionPipeline stages 1-3
    │   │   ├─ Stage 1: extract_entities()
    │   │   ├─ Stage 2: compress_narrative()
    │   │   └─ Stage 3: detect_state_deltas()
    │   │   (Stage 4 embedding deferred to MemoryService)
    │   │
    │   └─ MemoryService.store() → creates Memory with status='pending_review'
    │
    └─ _persist_assessment() → writes to turn_assessments table (audit trail)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `assess_turn()` | Main entry point. Synchronous. Runs classification + store + audit. |
| `_classify_turn()` | Ollama chat_json with CLASSIFICATION_SYSTEM/USER prompts. Returns (assessment, what). |
| `_extract_and_store()` | Runs compression stages 1-3, calls MemoryService.store(). |
| `_persist_assessment()` | Writes row to turn_assessments table for audit trail. |

### Prompts

**CLASSIFICATION_SYSTEM:**
> "You are a knowledge detector. Given a conversation turn, decide if genuinely NEW knowledge was established — a decision made, a fact revealed, a preference stated, a commitment given. Be CONSERVATIVE."

**CLASSIFICATION_USER:**
```
User said: {user_message}
CAIRN responded: {cairn_response}
Known context: {known_memories}

Did this turn establish NEW knowledge?
{"assessment": "NO_CHANGE" | "CREATE", "what": "one sentence or empty"}

Rules:
- NO_CHANGE for questions, casual chat, known information
- CREATE only for clear decisions, commitments, preferences, facts
- When in doubt, NO_CHANGE
```

### Background Queue (`TurnAssessmentQueue`)

**Singleton pattern:** `get_turn_assessment_queue()` lazy-creates and starts daemon thread.

```python
queue = get_turn_assessment_queue()
queue.submit(
    conversation_id="conv-abc",
    turn_position=3,
    user_message="I've decided to use PostgreSQL",
    cairn_response="That makes sense...",
)
# Returns immediately — processing happens asynchronously
```

**Worker thread:**
- Polls queue with 1s timeout
- Calls `assessor.assess_turn()` on each job
- Swallows all exceptions (never crashes)
- Thread is daemon, exits with app

### Output

**Table:** `turn_assessments` (audit trail, no filtering)
- `id, conversation_id, turn_position, assessment, memory_id, model_used, duration_ms, created_at`

**DataClass:** `TurnAssessment`
- `conversation_id, turn_position, assessment, what, memory_id, model_used, duration_ms`

---

## 2. CompressionPipeline (4-Stage Local Inference)

**File:** `src/cairn/services/compression_pipeline.py` (379 lines)

### What It Does
Transforms conversation transcript into structured memories through 4 stages of local Ollama inference. Each stage is independently callable for testing, but `compress()` runs full pipeline.

### Pipeline Stages

#### Stage 1: Entity Extraction

**LLM Call:** `chat_json(ENTITY_EXTRACTION_SYSTEM, ENTITY_EXTRACTION_USER, temp=0.1)`

**Output Structure:**
```json
{
  "people": [{"name": "", "context": "", "relation": ""}],
  "tasks": [{"description": "", "status": "decided|in_progress|blocked|completed", "priority": ""}],
  "decisions": [{"what": "", "why": ""}],
  "waiting_on": [{"who": "", "what": "", "since": ""}],
  "questions_resolved": [{"question": "", "answer": ""}],
  "questions_opened": [{"question": ""}],
  "blockers_cleared": [{"what": "", "unblocks": ""}],
  "insights": [{"insight": "", "context": ""}]
}
```

**Error Handling:** JSON parse failure → returns `{}`. Never raises.

#### Stage 2: Narrative Compression

**LLM Call:** `chat_text(NARRATIVE_SYSTEM, NARRATIVE_USER, temp=0.3)`

**Input:** Extracted entities from Stage 1

**Output:** 2-4 sentence narrative (meaning synthesis, not summary)

**Example:**
```
"Kel decided to prioritize Thunderbird recurring event support before 
building the Scene UI. This unblocks frontend work in the 'Building 
Talking Rock' Act. No external dependencies. Open question remains 
about which calendar format best handles recurrence."
```

**Error Handling:** LLM failure → returns `""`. Never raises.

#### Stage 3: State Delta Detection

**LLM Call:** `chat_json(STATE_DELTA_SYSTEM, STATE_DELTA_USER, temp=0.1)`

**Inputs:**
- Current open state (open threads, waiting-ons, priorities)
- Newly extracted entities

**Output Structure:**
```json
{
  "new_waiting_ons": [{"who": "", "what": ""}],
  "resolved_waiting_ons": [{"who": "", "what": ""}],
  "new_open_threads": [{"thread": "", "act": ""}],
  "resolved_threads": [{"thread": ""}],
  "priority_changes": [{"item": "", "old": "", "new": ""}]
}
```

**Error Handling:** JSON parse failure → returns `{}`. Conservative (only mark resolved if explicit).

#### Stage 4: Embedding Generation

**Method:** `generate_embedding(narrative)` — uses sentence-transformers (all-MiniLM-L6-v2)

**Optional:** If `sentence-transformers` not installed, skipped gracefully. MemoryService can generate later.

**Output:** `bytes | None`

### Data Class

```python
@dataclass
class ExtractionResult:
    entities: dict[str, Any]
    narrative: str
    state_deltas: dict[str, Any]
    embedding: bytes | None
    model_used: str
    duration_ms: int
    passes: int  # Number of stages completed
    confidence: float  # Heuristic: entity count + narrative length
```

### Confidence Estimation

```python
score = 0.5  # Base
if entity_count >= 3: score += 0.2
elif entity_count >= 1: score += 0.1
if len(narrative) > 50: score += 0.2
elif len(narrative) > 20: score += 0.1
confidence = min(score, 1.0)
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `compress()` | Run full 4-stage pipeline. Main entry point. |
| `extract_entities()` | Stage 1 only. |
| `compress_narrative()` | Stage 2 only. Requires entities. |
| `detect_state_deltas()` | Stage 3 only. Requires entities + current state. |
| `generate_embedding()` | Stage 4 only. Deferred optional. |

### Usage Example

```python
pipeline = CompressionPipeline()
result = pipeline.compress(
    transcript="[user]: ...\n\n[cairn]: ...",
    conversation_date="2026-02-20",
    message_count=5,
    current_open_state={...}
)
# result.narrative, result.entities, result.state_deltas, result.embedding
```

---

## 3. MemoryService (Storage, Deduplication, Review)

**File:** `src/cairn/services/memory_service.py` (650+ lines)

### What It Does
Manages full memory lifecycle:
1. **Store:** Deduplicate via embedding similarity + LLM judgment, reinforce or create
2. **Route:** Direct memories to destination Act (default: Your Story)
3. **Review:** Gate memories through user review before reasoning context injection
4. **Correct/Supersede:** Memory correction with signal_count inheritance

### Deduplication Flow

```
MemoryService.store(narrative, embedding, ...)
    ↓
_check_duplicate(narrative, embedding)
    ├─ If no embedding → is_duplicate=False, create new
    │
    └─ EmbeddingService.find_similar() over candidate memories
       ├─ Get all memories with status IN ('approved', 'pending_review')
       ├─ Find top-5 by cosine similarity (threshold=0.7)
       │
       └─ For each candidate:
          └─ _judge_duplicate(new_narrative, existing_narrative)
             └─ Ollama chat_json with DEDUP_JUDGMENT_SYSTEM/USER
                → Returns {"is_match": bool, "merged_narrative": str}
                   ├─ Match found → _reinforce()
                   │   ├─ signal_count++
                   │   ├─ last_reinforced_at = now
                   │   ├─ status = 'pending_review' (re-enter review)
                   │   ├─ user_reviewed = 0
                   │   └─ optionally update narrative with merged version
                   │
                   └─ No match → _create_memory()
```

### Data Classes

#### Memory
```python
@dataclass
class Memory:
    id: str
    block_id: str
    conversation_id: str
    narrative: str
    destination_act_id: str | None
    is_your_story: bool
    status: str  # 'pending_review'|'approved'|'rejected'|'superseded'
    signal_count: int  # Reinforcement count
    last_reinforced_at: str | None
    extraction_model: str | None
    extraction_confidence: float | None
    user_reviewed: bool
    user_edited: bool
    original_narrative: str | None  # Saved when narrative merged
    created_at: str
    source: str  # 'compression'|'turn_assessment'|'priority_signal'|'claudecode'
```

#### DeduplicationResult
```python
@dataclass
class DeduplicationResult:
    is_duplicate: bool
    matched_memory_id: str | None = None
    reason: str = ""
    merged_narrative: str = ""
```

### Prompts

**DEDUP_JUDGMENT_SYSTEM:**
> "You are a memory deduplication judge. Given a NEW memory and an EXISTING memory, determine if they represent the SAME insight, decision, or fact — not just semantically similar topics, but substantively identical conclusions."

**Example distinction:**
- "Alex prefers email" vs "Alex prefers Slack" → DIFFERENT (opposite conclusions)
- "We decided to use SQLite" vs "The team chose SQLite for storage" → SAME

**DEDUP_JUDGMENT_USER:**
```
NEW memory:
{new_narrative}

EXISTING memory (signal_count={signal_count}):
{existing_narrative}

Are these the SAME substantive insight/decision/fact?
{"is_match": true/false, "reason": "...", "merged_narrative": "..."}
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `store()` | Main entry. Dedup → reinforce or create. |
| `_check_duplicate()` | Embedding similarity filter + LLM judgment. |
| `_judge_duplicate()` | LLM substantive match arbiter. |
| `_reinforce()` | Increment signal_count, re-enter review. |
| `_create_memory()` | Create new memory block + row. |
| `get_by_id()` | Fetch memory by ID. |
| `get_pending_review()` | Fetch memories awaiting user approval. |
| `approve()` / `reject()` / `supersede()` | Review actions. |

### Storage

**Tables:**
- `memories` — Main memory records (status='pending_review'|'approved'|'rejected'|'superseded')
- `blocks` — Block storage (type='memory')
- `block_embeddings` — Vector embeddings (all-MiniLM-L6-v2)

**Indexes:**
```sql
idx_memories_conversation(conversation_id)
idx_memories_destination(destination_act_id)
idx_memories_your_story(is_your_story)
idx_memories_created(created_at)
idx_memories_status(status)
idx_memories_signal(signal_count)
```

---

## 4. MemoryRetriever (Semantic Search + Graph Expansion)

**File:** `src/cairn/memory/retriever.py` (697 lines)

### What It Does
Retrieves relevant memory for CAIRN reasoning context. Two flavors:
1. **Block retrieval:** General semantic + graph expansion (for Notion-style blocks)
2. **Conversation memory retrieval:** With signal weighting & recency decay (for conversation context)

### Three-Stage Retrieval Pipeline

```
retrieve(query, ...)
    ↓
Stage 1: Semantic Search
    └─ Embed query → find similar blocks via cosine similarity
       Returns: list[(block_id, similarity)]
       Filter: similarity >= threshold (default 0.5)
       Limit: top_k
    ↓
Stage 2: Graph Expansion
    └─ For each semantic match, traverse relationships up to depth=1
       Priority: LOGICAL_RELATIONSHIPS | SEMANTIC_RELATIONSHIPS
       Scoring: closer nodes score higher (depth 1→0.4, depth 2→0.2, depth 3+→0.1)
    ↓
Stage 3: Rank & Merge
    └─ Apply type weights (reasoning_chain=1.2, knowledge_fact=1.1, etc.)
       Apply source bonus (both=+0.15, semantic=0, graph=-0.05)
       Sort by final score, take max_results
```

### Conversation Memory Retrieval

**Special scoring for conversation memories:**

```
final_score = semantic_similarity × recency_decay × signal_weight

Where:
  semantic_similarity = cosine distance (0.0-1.0)
  recency_decay = 0.5 ^ (age_days / half_life_days)
    Default half_life = 30 days
    Age 0 days → 1.0
    Age 30 days → 0.5
    Age 60 days → 0.25
  signal_weight = log2(signal_count + 1)
    signal_count=0 → weight=1.0
    signal_count=1 → weight=1.0
    signal_count=3 → weight=2.0
    signal_count=7 → weight=3.0
```

### Data Classes

#### MemoryMatch (Block-level)
```python
@dataclass
class MemoryMatch:
    block_id: str
    block_type: str
    content: str
    score: float  # Combined relevance score (0.0-1.0)
    source: str  # 'semantic'|'graph'|'both'
    relationship_chain: list[str]  # e.g. ['references', 'elaborates']
    act_id: str
    page_id: str | None
    created_at: str
```

#### ConversationMemoryMatch (Memory-level)
```python
@dataclass
class ConversationMemoryMatch:
    memory_id: str
    block_id: str
    narrative: str
    score: float  # Final weighted score
    semantic_similarity: float
    signal_count: int
    signal_weight: float
    recency_weight: float
    created_at: str
    conversation_id: str

    def to_prompt_line(self) -> str:
        """Format for injection into LLM prompts."""
        # e.g. "[Memory from 2026-02-19 | signal: 3x]: We decided to use SQLite."
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `retrieve()` | Retrieve general blocks (3-stage pipeline). |
| `retrieve_conversation_memories()` | Retrieve conversation memories with signal/recency weighting. |
| `_semantic_search()` | Stage 1: Embed query, find similar. |
| `_expand_via_graph()` | Stage 2: Traverse relationships. |
| `_rank_and_merge()` | Stage 3: Score & sort. |
| `index_block()` | Index a block's embedding (call on creation). |
| `remove_block_index()` | Remove block from index (call on deletion). |

### Usage Example

```python
retriever = MemoryRetriever()

# Conversation memory retrieval
conv_ctx = retriever.retrieve_conversation_memories(
    query="What have I decided about calendar sync?",
    act_id="act-xyz",
    max_results=10,
    semantic_threshold=0.5,
    status='approved'
)
# conv_ctx.matches: list[ConversationMemoryMatch]
for match in conv_ctx.matches:
    print(match.to_prompt_line())
    # [Memory from 2026-02-19 | signal: 3x]: ...
```

---

## 5. MemoryGraphStore (Graph CRUD & Traversal)

**File:** `src/cairn/memory/graph_store.py` (200+ lines)

### What It Does
Provides CRUD operations and graph traversal for memory relationships.

### Data Classes

#### GraphEdge
```python
@dataclass
class GraphEdge:
    id: str
    source_block_id: str
    target_block_id: str
    relationship_type: RelationshipType
    confidence: float = 1.0
    weight: float = 1.0
    source: RelationshipSource = RelationshipSource.INFERRED
    created_at: str = ""
```

#### TraversalResult
```python
@dataclass
class TraversalResult:
    start_block_id: str
    visited_blocks: set[str]
    edges: list[GraphEdge]
    blocks_by_depth: dict[int, list[str]]  # {0: [...], 1: [...], ...}
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `create_relationship()` | Create edge between blocks. |
| `get_relationship()` | Fetch edge by ID. |
| `delete_relationship()` | Remove edge. |
| `list_relationships()` | List edges for a block (incoming/outgoing/both). |
| `traverse()` | BFS graph traversal from seed block. |
| `find_path()` | Find shortest path between two blocks. |
| `get_all_embeddings()` | Get all block embeddings for search. |
| `store_embedding()` | Store/update embedding for a block. |
| `delete_embedding()` | Remove embedding. |
| `is_embedding_stale()` | Check if content_hash changed. |

### Storage

**Tables:**
- `block_relationships` — Edges (source → target)
- `block_embeddings` — Vector embeddings

**Indexes:**
```sql
idx_block_rel_source(source_block_id)
idx_block_rel_target(target_block_id)
idx_block_rel_type(relationship_type)
idx_block_emb_hash(content_hash)
```

---

## 6. RelationshipExtractor (Auto Relationship Building)

**File:** `src/cairn/memory/extractor.py` (250+ lines)

### What It Does
Extracts relationships from:
- Reasoning chains (logical connectors, explicit block references)
- RLHF feedback (positive strengthens, negative creates corrections)
- Block content (semantic similarity)

### Relationship Types (from relationships.py)

**Logical:**
- `REFERENCES` — Source cites/mentions target
- `FOLLOWS_FROM` — Source is logical consequence of target
- `CONTRADICTS` — Source conflicts with target
- `SUPPORTS` — Source provides evidence for target
- `ELABORATES` — Source provides detail about target

**Semantic:**
- `SIMILAR_TO` — Semantically similar (auto-detected)
- `RELATED_TO` — Generic connection

**Causal:**
- `CAUSED_BY` — Source was caused by target
- `CAUSES` — Source causes target

**Feedback/Learning:**
- `CORRECTS` — Source is correction of target
- `SUPERSEDES` — Source replaces target
- `DERIVED_FROM` — Source based on target

**Temporal:**
- `PRECEDED_BY` — Source came after target
- `RESPONDS_TO` — Source responds to target

### Relationship Sources (provenance)

```python
class RelationshipSource(Enum):
    USER = "user"          # Explicitly created by user
    CAIRN = "cairn"        # Created by CAIRN during reasoning
    INFERRED = "inferred"  # Automatically inferred
    FEEDBACK = "feedback"  # From RLHF feedback
    EMBEDDING = "embedding"  # From embedding similarity
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `extract_from_chain()` | Extract relationships from reasoning chain. |
| `extract_from_feedback()` | Extract from RLHF feedback. |
| `_extract_block_references()` | Find explicit block refs (block-abc123 or [block:xyz]). |
| `_detect_logical_patterns()` | Match logical connectors. |
| `_find_similar()` | Semantic similarity via embeddings. |

---

## 7. RelationshipTypes & Sources

**File:** `src/cairn/memory/relationships.py`

**Logical Relationships (high priority for traversal):**
```python
LOGICAL_RELATIONSHIPS = {
    REFERENCES, FOLLOWS_FROM, CONTRADICTS, 
    SUPPORTS, ELABORATES, CAUSED_BY
}
```

**Semantic Relationships:**
```python
SEMANTIC_RELATIONSHIPS = {
    SIMILAR_TO, RELATED_TO
}
```

---

## 8. StateBriefingService (Situational Awareness)

**File:** `src/cairn/services/state_briefing_service.py` (250+ lines)

### What It Does
On new conversation start, generates compressed situational awareness document. Injected into first turn's context. Cached 24 hours.

### Purpose
Creates warm starts that make each conversation feel continuous. Instead of starting fresh, user sees:
- Top recent memories
- Active work items
- Attention priorities
- Open threads
- Last session summary

### Data Class

```python
@dataclass
class StateBriefing:
    id: str
    content: str  # Markdown, target < 300 tokens
    token_count: int | None
    trigger: str  # 'app_start'|'new_conversation'|'manual'
    generated_at: str
```

### Staleness

Briefing is stale if generated > 24 hours ago. On stale, regenerates.

### Prompts

**BRIEFING_SYSTEM:**
> "You are a situational awareness synthesizer. Given memory snippets, open tasks, and recent context, write a BRIEF orientation document for resuming work. Keep it under 250 words."

**BRIEFING_USER:**
```
Top memories:
{memories_block}

Active work items:
{active_scenes_block}

User's attention priorities:
{priorities_block}

Open threads:
{open_threads_block}

Last session summary:
{last_summary}

Write the orientation document now.
```

### Key Methods

| Method | Purpose |
|--------|---------|
| `get_current()` | Fetch most recent non-stale briefing. |
| `get_or_generate()` | Return current or generate new. |
| `generate()` | LLM generation from knowledge state. |
| `_is_stale()` | Check if > 24 hours old. |

---

## 9. Database Schema (Memory Tables)

**File:** `src/cairn/play_db.py` (Schema v13+)

### conversations
```sql
CREATE TABLE conversations (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id),
    status TEXT NOT NULL DEFAULT 'active',  -- active|ready_to_close|compressing|archived
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    closed_at TIMESTAMP,
    archived_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    compression_model TEXT,
    compression_duration_ms INTEGER,
    compression_passes INTEGER,
    is_paused BOOLEAN DEFAULT 0
);
```

**Indexes:** `idx_conversations_status`, `idx_conversations_last_message`

### messages
```sql
CREATE TABLE messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    block_id TEXT NOT NULL REFERENCES blocks(id),
    role TEXT NOT NULL,  -- user|cairn|reos|riva|system
    content TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active_act_id TEXT,
    active_scene_id TEXT
);
```

**Indexes:** `idx_messages_conversation`, `idx_messages_position`

### memories
```sql
CREATE TABLE memories (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id),
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    narrative TEXT NOT NULL,
    narrative_embedding BLOB,
    destination_act_id TEXT,
    destination_page_id TEXT,
    is_your_story BOOLEAN DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending_review',  -- pending_review|approved|rejected|superseded
    user_reviewed BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    original_narrative TEXT,
    extraction_model TEXT,
    extraction_confidence REAL,
    signal_count INTEGER NOT NULL DEFAULT 1,
    last_reinforced_at TEXT,
    source TEXT NOT NULL DEFAULT 'compression',  -- compression|turn_assessment|priority_signal|claudecode
    cc_agent_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:** `idx_memories_conversation`, `idx_memories_destination`, `idx_memories_your_story`, `idx_memories_created`, `idx_memories_status`, `idx_memories_signal`

### memory_entities
```sql
CREATE TABLE memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    entity_type TEXT NOT NULL,  -- person|task|decision|waiting_on|question_resolved|...
    entity_data JSON NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    resolved_by_memory_id TEXT REFERENCES memories(id),
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:** `idx_memory_entities_memory`, `idx_memory_entities_type`, `idx_memory_entities_active`

### memory_state_deltas
```sql
CREATE TABLE memory_state_deltas (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    delta_type TEXT NOT NULL,  -- new_waiting_on|resolved_waiting_on|new_thread|resolved_thread|priority_change
    delta_data JSON NOT NULL,
    applied BOOLEAN DEFAULT 0,
    applied_at TIMESTAMP
);
```

**Indexes:** `idx_state_deltas_memory`, `idx_state_deltas_applied`

### classification_memory_references
```sql
CREATE TABLE classification_memory_references (
    id TEXT PRIMARY KEY,
    classification_id TEXT NOT NULL,
    memory_id TEXT NOT NULL REFERENCES memories(id),
    influence_type TEXT NOT NULL,
    influence_score REAL,
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

**Indexes:** `idx_memory_refs_classification`, `idx_memory_refs_memory`

### FTS5 Tables (Full-Text Search)
```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
    content, content='messages', content_rowid='rowid'
);

CREATE VIRTUAL TABLE memories_fts USING fts5(
    narrative, content='memories', content_rowid='rowid'
);
```

### Conversation Summaries (v13)
```sql
CREATE TABLE conversation_summaries (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),
    summary TEXT NOT NULL,
    summary_model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

### State Briefings (v13)
```sql
CREATE TABLE state_briefings (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    trigger TEXT NOT NULL
);
```

### Turn Assessments (v13, Audit Trail)
```sql
CREATE TABLE turn_assessments (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    turn_position INTEGER NOT NULL,
    assessment TEXT NOT NULL,  -- NO_CHANGE|CREATE
    memory_id TEXT REFERENCES memories(id),
    raw_input TEXT,
    model_used TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);
```

**Indexes:** `idx_turn_assessments_conversation`

---

## 10. RPC Handlers (Memory.py)

**File:** `src/cairn/rpc_handlers/memory.py`

### Endpoints

**Relationship CRUD:**
- `handle_memory_relationships_create()` — Create edge between blocks
- `handle_memory_relationships_get()` — Fetch edge by ID
- `handle_memory_relationships_delete()` — Remove edge
- `handle_memory_relationships_list()` — List edges for block (direction filter)

**Graph Traversal:**
- `handle_memory_graph_traverse()` — BFS from seed block
- `handle_memory_graph_find_path()` — Shortest path between blocks

**Semantic Search:**
- `handle_memory_search()` — Retrieve related blocks
- `handle_memory_search_embeddings()` — Search with embedding

**Memory Management:**
- `handle_memory_get()` — Fetch memory by ID
- `handle_memory_list()` — List memories (status filter)
- `handle_memory_approve()` / `handle_memory_reject()` — Review actions
- `handle_memory_update()` — Edit narrative

---

## 11. Integration Points: Agent ↔ Memory

**File:** `src/cairn/agent.py` (1400+ lines)

### Where Memory Gets Injected

#### 1. First Turn Initialization
```python
# In Agent._inject_context(), line ~1378
if not conversation_history:  # First turn of conversation
    briefing = StateBriefingService().get_or_generate()
    if briefing.content:
        memory_context = f"## Situational Awareness\n{briefing.content}\n\n{memory_context}"
```

#### 2. Every Turn: Conversation Memory Retrieval
```python
# In Agent._build_reasoning_context(), line ~1283
if "memory" not in disabled_sources:
    conv_memories = self._memory_retriever.retrieve_conversation_memories(
        query=user_message,
        act_id=active_act_id,
        max_results=10,
        status='approved'
    )
    memory_context = conv_memories.to_prompt_block()
    # Injected into system prompt before reasoning
```

#### 3. Background: Turn Assessment (After Response)
```python
# In Agent.chat(), after generating response
queue = get_turn_assessment_queue()
queue.submit(
    conversation_id=conversation_id,
    turn_position=turn_num,
    user_message=user_text,
    cairn_response=response_text,
    relevant_memories=[m.narrative for m in retrieved_memories]
)
```

### Context Injection Order

```
1. Temporal context (time, calendar, session gap)
2. State briefing (only first turn of conversation)
3. Relevant memories (conversation-level, signal + recency weighted)
4. Conversation history (messages so far)
5. System prompt with reasoning instructions
```

---

## 12. Data Flow: Complete Picture

### Full Memory Lifecycle

```
┌─ User Message ─────────────────────────────────────────┐
│                                                         │
├─→ MemoryRetriever.retrieve_conversation_memories()     │
│   ├─ Embed query                                        │
│   ├─ Find similar approved memories (cosine sim)        │
│   ├─ Weight by recency & signal count                   │
│   └─ Return top-k ConversationMemoryMatch              │
│                                                         │
├─→ Agent builds reasoning context (memory injected)      │
│                                                         │
├─→ CAIRN generates response                              │
│                                                         │
└─→ TurnAssessmentQueue.submit()
    ↓ (background daemon thread)
    
TurnDeltaAssessor.assess_turn()
    ├─→ Classification LLM: "Is this new knowledge?"
    │   └─ Returns: NO_CHANGE | CREATE
    │
    ├─→ [if CREATE] Extract & Store:
    │   ├─→ CompressionPipeline.compress()
    │   │   ├─ Stage 1: extract_entities()
    │   │   ├─ Stage 2: compress_narrative()
    │   │   ├─ Stage 3: detect_state_deltas()
    │   │   └─ Stage 4: generate_embedding()
    │   │
    │   └─→ MemoryService.store()
    │       ├─→ Embedding similarity search
    │       ├─→ LLM deduplication judgment
    │       │   ├─ Match found → _reinforce()
    │       │   │   ├─ signal_count++
    │       │   │   ├─ Re-enter pending_review
    │       │   │   └─ Graph link to conversation
    │       │   │
    │       │   └─ No match → _create_memory()
    │       │       ├─ Create blocks row (type='memory')
    │       │       ├─ Create memories row
    │       │       ├─ Store embedding in block_embeddings
    │       │       ├─ Link conversation via graph edge
    │       │       └─ status='pending_review'
    │       │
    │       └─→ Returns Memory object
    │
    └─→ _persist_assessment() → turn_assessments audit row
        (never raises, errors are logged only)

User reviews pending memories
    ├─→ approve() → status='approved'
    │   ├─ Approved memories now in retrieval pool
    │   ├─ signal_count used in recency-decay scoring
    │   └─ block_embeddings indexed for semantic search
    │
    ├─→ reject() → status='rejected'
    │   └─ Hidden from reasoning context
    │
    └─→ supersede() → status='superseded'
        ├─ Old memory hidden
        └─ New memory created (chains signal_count)

[On next conversation start]
    ├─→ StateBriefingService.get_or_generate()
    │   ├─ Check if cached briefing is fresh (< 24h)
    │   ├─ If stale, LLM synthesis from:
    │   │   ├─ Top approved memories
    │   │   ├─ Active work items (scenes)
    │   │   ├─ Attention priorities
    │   │   ├─ Open threads
    │   │   └─ Last session summary
    │   └─ Injected into first-turn context
    │
    └─→ MemoryRetriever.retrieve_conversation_memories()
        ├─ Finds approved memories relevant to new query
        ├─ Scores by: similarity × recency × signal_weight
        └─ Injected as "Prior Memories" section in prompt
```

---

## 13. Key Design Decisions

### Why Asynchronous Turn Assessment?

**Zero latency impact:** User sees CAIRN response immediately. Assessment happens in background.

**Threading:** Daemon thread + Queue. Worker processes one job at a time, swallows exceptions.

**Tradeoff:** Memory creation is not atomic with response generation. But correctness >> speed here.

### Why Embedding-Based Deduplication?

**Precision:** Embedding similarity filters candidates. LLM judges substantive match.

**Cost-effective:** Local embeddings are free. Saves on LLM reasoning for obvious non-matches.

**No false positives:** Requires explicit LLM agreement. "Alex prefers email" and "Alex prefers Slack" won't merge.

### Why Signal Counting?

**Reinforcement signal:** Each time a concept is mentioned, signal_count++. High-signal memories are more relevant (weighted in scoring).

**Re-entry to review:** Reinforced memories go back to pending_review (user sees they're reinforced, can merge narratives).

### Why Recency Decay?

**Time-sensitive knowledge:** Recent decisions matter more. Half-life of 30 days means month-old memories are 50% weighted.

**Prevents stale context:** CAIRN won't over-emphasize 6-month-old decisions.

### Why Local Inference Only?

**Cost:** Cloud LLM API = thousands of tokens per conversation analysis. Local = free. Run pipeline 3 times if needed.

**Privacy:** Zero data exfiltration. Embeddings, reasoning, entities all stay local.

**Latency:** Ollama runs on local hardware. No network roundtrips for assessment.

---

## 14. Gaps & TODOs

### Current Limitations

1. **State deltas not applied:** Stage 3 of compression extracts `state_deltas` (new open threads, resolved waiting-ons, priority changes) but they're not automatically applied to CAIRN's open state. They're stored but marked `applied=0`.

2. **Graph traversal depth-limited:** Hardcoded to depth=1-3. No sophisticated relationship pathfinding.

3. **Embedding optional:** Stage 4 of compression is optional. If sentence-transformers unavailable, skipped. Later dedup works without embeddings but loses precision.

4. **No temporal reasoning:** Memories aren't indexed by time. Can't answer "What happened last week?" or "Show me decisions from this sprint."

5. **No entity linking:** Extracted entities (people, tasks) aren't linked across memories. No "show all tasks assigned to Alex" queries.

6. **Singular narrative:** Each memory is one narrative. No sub-components. Limits query expressiveness.

7. **No active/inactive entity tracking:** Memory entities can be marked `is_active` but nothing uses this for filtering.

8. **Turn assessment only CREATE:** No UPDATE path. Reinforced memories re-enter review rather than silently strengthening.

### TODOs (From Code)

**compression_pipeline.py:**
- [ ] Handle edge case: empty narrative after Stage 2

**memory_service.py:**
- [ ] Apply state_deltas automatically after memory approved
- [ ] Index active open threads for "show me what's open" queries

**memory/retriever.py:**
- [ ] Improve graph traversal: use semantic similarity for edge weighting

**agent.py:**
- [ ] Temporal context injection: calendar lookahead, session gap detection

---

## 15. Testing Coverage

**Test Files:**
- `tests/test_turn_delta_assessor.py` — Classification, extraction, dedup flow
- `tests/test_memory_service.py` — Store, dedup judgment, reinforce, create
- `tests/test_compression_pipeline.py` — All 4 stages, entity extraction, narrative
- `tests/test_memory_retriever.py` — Semantic search, graph expansion, ranking
- `tests/test_memory_graph_store.py` — CRUD, traversal, path finding
- `tests/test_memory_embeddings.py` — Embedding generation, similarity
- `tests/test_state_briefing_service.py` — Generation, caching, staleness
- `tests/test_memory_relationships.py` — Relationship types, extractor
- `tests/test_memory_rpc.py` — RPC handlers

**Coverage:** ~1996 tests total (9 memory-specific test files).

---

## 16. Key Files Summary

| File | LOC | Purpose |
|------|-----|---------|
| `services/turn_delta_assessor.py` | 495 | Per-turn memory assessment & background queue |
| `services/memory_service.py` | 650+ | Storage, dedup, review, routing |
| `services/compression_pipeline.py` | 379 | 4-stage compression (entity→narrative→delta→embedding) |
| `memory/retriever.py` | 697 | Semantic search + graph expansion + ranking |
| `memory/graph_store.py` | 200+ | Graph CRUD & traversal |
| `memory/extractor.py` | 250+ | Relationship extraction |
| `memory/relationships.py` | 100 | Relationship type & source enums |
| `services/state_briefing_service.py` | 250+ | Situational awareness synthesis |
| `rpc_handlers/memory.py` | 150+ | RPC endpoints for memory management |
| `play_db.py` | 1600+ | Schema v13 (memories, entities, deltas, etc.) |
| `agent.py` | 1400+ | Integration points (retrieval, injection, background) |

---

## 17. Execution Flow Diagram

```
    User Input
        ↓
    ┌─────────────────────────────────────────────┐
    │ Agent.chat(user_text)                       │
    │                                             │
    │ 1. Temporal context injected first          │
    │ 2. State briefing (if first turn)           │
    │ 3. Conversation memory retrieved (approved) │
    │    ├─ Query embedding via EmbeddingService  │
    │    ├─ Find similar narratives (cosine sim)  │
    │    ├─ Score = sim × recency × signal_w      │
    │    └─ Inject top-k into prompt              │
    │ 4. Conversation history appended            │
    │ 5. Intent classification & execution        │
    │ 6. Generate response                        │
    └─────────────────────────────────────────────┘
        ↓
    Response + Reasoning Trace
        ↓
    Store in messages table
        ↓
    ┌─────────────────────────────────────────────┐
    │ TurnAssessmentQueue.submit(job) [ASYNC]     │
    │                                             │
    │ Background worker thread:                   │
    │ 1. TurnDeltaAssessor.assess_turn()          │
    │    ├─ Ollama classification (temp=0.1)      │
    │    │  "Is this new knowledge?"              │
    │    ├─ → NO_CHANGE: done                     │
    │    └─ → CREATE: _extract_and_store()        │
    │       ├─ CompressionPipeline.compress()     │
    │       │  ├─ Stage 1: extract_entities()     │
    │       │  ├─ Stage 2: compress_narrative()   │
    │       │  ├─ Stage 3: detect_state_deltas()  │
    │       │  └─ Stage 4: generate_embedding()   │
    │       │                                     │
    │       └─ MemoryService.store()              │
    │          ├─ Find similar (embedding cosim)  │
    │          ├─ LLM dedup judgment              │
    │          ├─ Match: _reinforce()             │
    │          │  └─ signal_count++, pending_rev  │
    │          └─ No match: _create_memory()      │
    │             └─ status='pending_review'      │
    │                                             │
    │ 2. _persist_assessment() → audit trail      │
    └─────────────────────────────────────────────┘
        ↓
    User Reviews Pending Memories
        ├─→ approve()   → status='approved'
        │   └─ Now searchable + used in reasoning
        ├─→ reject()    → status='rejected'
        │   └─ Hidden
        └─→ supersede() → status='superseded'
            └─ Chain signal_count to replacement
```

---

## Conclusion

Cairn's memory system converts ephemeral conversations into durable, searchable, actionable knowledge. The 4-stage local compression pipeline + embedding-based deduplication + signal/recency weighting creates a personalized reasoning context that compounds in value as conversations accumulate.

**Key strengths:**
- Asynchronous, zero-latency assessment
- Conservative classification (precision over recall)
- LLM deduplication (substantive, not just semantic)
- Graph-based relationship tracking
- Local inference (no data exfiltration)
- Full audit trail (turn_assessments)

**Key limitations:**
- State deltas extracted but not applied
- No temporal indexing (can't query by time window)
- No entity linking (people, tasks not cross-referenced)
- Graph depth limited (1-3 hops)

