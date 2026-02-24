# Talking Rock: Conversation Lifecycle & Memory Architecture

**From Endless Threads to Deliberate Meaning**

Talking Rock Project  
February 2026  
Version 1.0

---

## The Problem

Every AI chat interface treats conversations as disposable infinities. Open a new one whenever you want. Leave old ones dangling forever. No closure, no extraction, no learning. When the conversation ends, you're a stranger again.

This is not a missing feature. It is a design choice that serves engagement metrics — more conversations means more usage means more data means more revenue. The user's cognitive fragmentation is someone else's growth number.

Talking Rock rejects this entirely.

## The Principle

A conversation is a unit of meaning with a beginning, a middle, and a deliberate end. When it ends, the meaning is extracted, compressed, and woven into the user's ongoing narrative. The raw conversation is archived with a permanent link. Nothing is hidden. Nothing is lost. The user sees exactly what the system learned and chooses where it lives.

**One conversation at a time.** You finish what you started, or you consciously set it aside. Depth over breadth. Attention as sacred labor applied to the system's own UX.

## Core Concepts

### Conversations

A conversation is a block of type `conversation` — the container for an interaction between the user and Talking Rock. It has a defined lifecycle and exactly one can be active at any time.

### Memories

A memory is the compressed meaning extracted from a completed conversation. Not a transcript summary. Not a log. A meaning extraction — what was decided, what changed, what's now open, what was resolved, who was mentioned, what matters. Memories are blocks of type `memory` that live inside Acts or Your Story as first-class knowledge.

### Your Story

Your Story is the permanent, un-archivable Act that represents *you* across all other Acts. It is the default destination for memories that don't belong to a specific project or life chapter. Over time, Your Story becomes the primary source Talking Rock uses to understand who you are — distinct from what you're doing.

Your Acts tell Talking Rock what you're working on. Your Story tells Talking Rock who you are.

### Memories as Reasoning Context

This is the architectural keystone: **memories are not passive records. They are the reference corpus for all reasoning.**

Every time Talking Rock processes a new request — classifying intent, decomposing into atomic operations, verifying understanding — it searches the memory database. Memories provide the context that turns a generic LLM into *your* assistant. Without them, every request starts from zero. With them, Talking Rock can disambiguate "fix the calendar thing" into a specific task because it remembers which calendar thing has been on your mind.

This is the feedback loop that makes the system compound in value:

```
Conversation → Memory → Reasoning Context → Better Understanding → Better Conversation → Richer Memory
```

Cloud providers cannot afford this loop. Retrieving and reasoning over personalized memory for every request multiplies inference cost. Locally, it's free — run as many retrieval passes as clarity requires.

---

## Conversation Lifecycle

### States

```
┌──────────┐    user closes     ┌────────────────┐    user confirms    ┌─────────────┐    auto    ┌──────────┐
│  active   │ ────────────────► │  ready-to-close │ ─────────────────► │ compressing  │ ────────► │ archived │
└──────────┘                    └────────────────┘                     └─────────────┘           └──────────┘
     ▲                                │                                      │
     │                                │ user resumes                         │
     │                                ▼                                      ▼
     │                          back to active                         memory created
     │                                                                 routed to Act/Story
     │
     │  on startup, if exists
     │
┌──────────┐
│  startup  │
└──────────┘
```

**active** — The conversation is in progress. This is a singleton state. If an active conversation exists, opening Talking Rock returns to it. There is no "new chat" button.

**ready-to-close** — The user has indicated they're done. Talking Rock shows a preview of what it will extract and where it will route the memory. The user can review, edit, redirect, or resume the conversation instead.

**compressing** — The user confirmed closure. Talking Rock runs local LLM inference to extract meaning, entities, state changes, and narrative summary. This is where cheap local inference is the competitive advantage — multiple passes, entity extraction, cross-referencing with existing Acts and open threads, all at zero marginal cost.

**archived** — The conversation is complete. The raw transcript is stored and permanently linkable. The extracted memory lives in its destination Act or Your Story.

### The Singleton Constraint

```sql
-- At most one active conversation at any time
-- Enforced at application level, verified by:
SELECT COUNT(*) FROM conversations WHERE status = 'active';
-- Must always return 0 or 1
```

When the user opens Talking Rock:
- If an active conversation exists → resume it
- If no active conversation → show CAIRN's startup greeting (open threads, waiting-ons, upcoming deadlines, stale items)
- Starting a new conversation is only possible when no conversation is active

This is philosophically bold. No other system does this. It embodies: finish what you started, or consciously decide to set it aside.

### Gentle Awareness, Never Nagging

Talking Rock may observe long silences within an active conversation — but only as an invitation, never a demand:

> "We've been quiet for a while. Is this thread resolved, or are you still sitting with it?"

The user can:
- Resume the conversation
- Close it (triggering compression)
- Explicitly mark it "paused" (a sub-state of active that suppresses the observation)

---

## The Compression Pipeline

When a conversation moves to `compressing`, Talking Rock runs a multi-stage local inference pipeline. This is where the economics of local inference create capabilities cloud providers cannot afford.

### Stage 1: Entity Extraction

A local LLM pass over the full conversation transcript, extracting structured entities:

```json
{
  "people": [
    {"name": "Alex", "context": "waiting on contract feedback", "relation": "colleague"}
  ],
  "tasks": [
    {"description": "Thunderbird recurring event support", "status": "decided", "priority": "next"}
  ],
  "decisions": [
    {"what": "Prioritize recurring events before Scene UI", "why": "unblocks Act progress"}
  ],
  "waiting_on": [
    {"who": "Alex", "what": "contract feedback", "since": "2026-02-19"}
  ],
  "questions_resolved": [
    {"question": "Should we build Scene UI first?", "answer": "No, recurring events first"}
  ],
  "questions_opened": [
    {"question": "What calendar format handles recurring events best?"}
  ],
  "blockers_cleared": [
    {"what": "Architecture decision for event storage", "unblocks": "frontend work"}
  ],
  "act_references": [
    {"act": "Building Talking Rock", "relevance": "direct work"}
  ]
}
```

**Cost on cloud:** Each extraction pass is thousands of tokens of input + structured output. At scale, prohibitive.  
**Cost locally:** Free. Run it twice if the first pass missed something. Run it three times. Patience is free.

### Stage 2: Narrative Compression

A second LLM pass that takes the raw entities and produces a human-readable narrative memory. This is not a transcript summary. It is a meaning synthesis:

**Transcript summary (what we don't do):**
> "User discussed calendar integration. Mentioned Thunderbird. Asked about recurring events. Decided to prioritize them."

**Narrative memory (what we do):**
> "Kel decided to prioritize Thunderbird recurring event support before building the Scene UI. This unblocks frontend work in the 'Building Talking Rock' Act. No external dependencies — this is self-directed work. Open question remains about which calendar format best handles recurrence."

The narrative memory reads like something a thoughtful colleague would remember about the conversation — the *significance*, not the transcript.

### Stage 3: State Delta Computation

A third pass (or rule-based post-processing) computes what changed in the knowledge graph:

```json
{
  "new_waiting_ons": [],
  "resolved_waiting_ons": [],
  "new_open_threads": [
    {"thread": "calendar format for recurrence", "act": "Building Talking Rock"}
  ],
  "resolved_threads": [
    {"thread": "architecture decision for event storage"}
  ],
  "priority_changes": [
    {"item": "recurring event support", "old": null, "new": "next"}
  ],
  "act_updates": [
    {"act": "Building Talking Rock", "update": "recurring events now priority"}
  ]
}
```

These deltas are applied to CAIRN's knowledge graph so the next startup greeting reflects the conversation's outcomes.

### Stage 4: Embedding Generation

Generate vector embeddings for the memory using local sentence transformers (all-MiniLM-L6-v2). These enable semantic search across all memories — "What did I decide about calendar stuff?" retrieves relevant memories even if the exact words differ.

---

## Memory Routing

### Default: Your Story

Every memory goes to Your Story unless the user redirects it. Your Story is the catch-all narrative — the record of you thinking, deciding, exploring, regardless of project context.

### Directed: Specific Act

The user can route a memory to a specific Act during the review step:

> **Talking Rock:** "Here's what I'm remembering from this conversation. By default this goes to Your Story. Want to direct it somewhere specific?"
>
> **User:** "Put it in Building Talking Rock."

### Split Routing

A single conversation may contain meaning relevant to multiple Acts. The user can split:

> **User:** "The technical decisions go to Building Talking Rock. The stuff about Alex goes to Work."

This creates two memory blocks from one conversation, each parented under the appropriate Act, each linking back to the same archived conversation.

### Automatic Suggestion

Talking Rock can suggest routing based on Act context. If the conversation heavily references entities from a specific Act, it suggests that Act as the destination. The user always confirms.

```
Suggested destination: "Building Talking Rock"
  (conversation references 4 entities from this Act)

[Accept] [Your Story instead] [Split across Acts] [Choose different Act]
```

### NOL Programs

> **NOL Programs (RIVA infrastructure — currently frozen):** When RIVA generates verified NoLang programs, the assembly text and verification status will be candidates for memory extraction. Verified programs with matching hashes can be recalled in future sessions to skip regeneration. The `nol_assembly` field on `Action` is persisted in conversation messages and available for compression. This infrastructure is implemented but not active while RIVA development is paused.

---

## The Review Step

After compression, before archival, Talking Rock presents the extracted memory for review. This is transparency made tangible.

```
┌─────────────────────────────────────────────────────────────┐
│ Memory from this conversation:                              │
│                                                             │
│ "Kel decided to prioritize Thunderbird recurring event      │
│  support before building the Scene UI. This unblocks        │
│  frontend work in 'Building Talking Rock'. No external      │
│  dependencies. Open question: which calendar format         │
│  best handles recurrence."                                  │
│                                                             │
│ Extracted:                                                  │
│   • Decision: recurring events before Scene UI              │
│   • Unblocks: frontend work                                 │
│   • Open question: calendar recurrence format               │
│   • No new waiting-ons                                      │
│                                                             │
│ Destination: Building Talking Rock (suggested)              │
│                                                             │
│ [✓ Confirm] [✎ Edit Memory] [↗ Redirect] [Split] [Resume] │
└─────────────────────────────────────────────────────────────┘
```

The user can:
- **Confirm** — Accept the memory as-is, archive the conversation
- **Edit** — Modify the narrative, add nuance, remove things the model over-extracted
- **Redirect** — Change the destination Act
- **Split** — Route different parts to different Acts
- **Resume** — Go back to the conversation (cancel closure)

**This is the trust contract made visible.** Not a privacy policy. Not a settings page. A direct, editable record of exactly what the system learned from talking to you.

---

## Database Schema

### Conversations Table

```sql
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,                    -- UUID
    block_id TEXT NOT NULL,                 -- Reference to block in blocks table
    status TEXT NOT NULL DEFAULT 'active',  -- active, ready_to_close, compressing, archived
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    closed_at TIMESTAMP,                    -- When user initiated close
    archived_at TIMESTAMP,                  -- When compression finished
    message_count INTEGER DEFAULT 0,
    
    -- Compression metadata
    compression_model TEXT,                 -- Which local model performed extraction
    compression_duration_ms INTEGER,        -- How long compression took
    compression_passes INTEGER,             -- How many inference passes
    
    -- Paused state
    is_paused BOOLEAN DEFAULT 0,            -- Suppresses idle observations
    paused_at TIMESTAMP,
    
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
    
    CHECK (status IN ('active', 'ready_to_close', 'compressing', 'archived'))
);

CREATE INDEX idx_conversations_status ON conversations(status);
CREATE INDEX idx_conversations_last_message ON conversations(last_message_at);
```

### Messages Table

```sql
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,                    -- UUID
    conversation_id TEXT NOT NULL,
    block_id TEXT NOT NULL,                 -- Reference to block in blocks table
    role TEXT NOT NULL,                     -- 'user', 'cairn', 'reos', 'riva', 'system'
    content TEXT NOT NULL,                  -- Raw message content
    position INTEGER NOT NULL,             -- Order within conversation
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Agent routing context
    active_act_id TEXT,                     -- Which Act was contextually active
    active_scene_id TEXT,                   -- Which Scene was contextually active
    
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
    
    CHECK (role IN ('user', 'cairn', 'reos', 'riva', 'system'))
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_messages_position ON messages(conversation_id, position);
```

### Memories Table

```sql
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,                    -- UUID
    block_id TEXT NOT NULL,                 -- Reference to block in blocks table
    conversation_id TEXT NOT NULL,          -- Source conversation
    
    -- Narrative
    narrative TEXT NOT NULL,                -- Human-readable meaning summary
    narrative_embedding BLOB,              -- Vector embedding for semantic search
    
    -- Destination
    destination_act_id TEXT,               -- Which Act this memory lives in (NULL = Your Story)
    destination_page_id TEXT,              -- Specific page within Act (optional)
    is_your_story BOOLEAN DEFAULT 1,       -- TRUE if routed to Your Story
    
    -- User review
    user_reviewed BOOLEAN DEFAULT 0,       -- Did user review before archival
    user_edited BOOLEAN DEFAULT 0,         -- Did user modify the extraction
    original_narrative TEXT,               -- Pre-edit narrative (if edited)
    
    -- Extraction metadata
    extraction_model TEXT,                 -- Which model performed extraction
    extraction_confidence REAL,            -- Model's confidence in extraction quality
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
    FOREIGN KEY (conversation_id) REFERENCES conversations(id) ON DELETE CASCADE,
    FOREIGN KEY (destination_act_id) REFERENCES blocks(id) ON DELETE SET NULL
);

CREATE INDEX idx_memories_conversation ON memories(conversation_id);
CREATE INDEX idx_memories_destination ON memories(destination_act_id);
CREATE INDEX idx_memories_your_story ON memories(is_your_story);
CREATE INDEX idx_memories_created ON memories(created_at);
```

### Extracted Entities Table

```sql
CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,                    -- UUID
    memory_id TEXT NOT NULL,
    
    entity_type TEXT NOT NULL,             -- 'person', 'task', 'decision', 'waiting_on',
                                           -- 'question_resolved', 'question_opened',
                                           -- 'blocker_cleared', 'priority_change'
    
    entity_data JSON NOT NULL,             -- Structured entity data
    
    -- State tracking
    is_active BOOLEAN DEFAULT 1,           -- Still relevant? (resolved items become inactive)
    resolved_by_memory_id TEXT,            -- Which later memory resolved this entity
    resolved_at TIMESTAMP,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE,
    FOREIGN KEY (resolved_by_memory_id) REFERENCES memories(id) ON DELETE SET NULL,
    
    CHECK (entity_type IN (
        'person', 'task', 'decision', 'waiting_on',
        'question_resolved', 'question_opened',
        'blocker_cleared', 'priority_change',
        'act_reference', 'insight'
    ))
);

CREATE INDEX idx_memory_entities_memory ON memory_entities(memory_id);
CREATE INDEX idx_memory_entities_type ON memory_entities(entity_type);
CREATE INDEX idx_memory_entities_active ON memory_entities(is_active);
```

### State Deltas Table

```sql
CREATE TABLE IF NOT EXISTS memory_state_deltas (
    id TEXT PRIMARY KEY,                    -- UUID
    memory_id TEXT NOT NULL,
    
    delta_type TEXT NOT NULL,              -- 'new_waiting_on', 'resolved_waiting_on',
                                           -- 'new_thread', 'resolved_thread',
                                           -- 'priority_change', 'act_update'
    
    delta_data JSON NOT NULL,              -- What changed
    applied BOOLEAN DEFAULT 0,             -- Has this delta been applied to knowledge graph
    applied_at TIMESTAMP,
    
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX idx_state_deltas_memory ON memory_state_deltas(memory_id);
CREATE INDEX idx_state_deltas_applied ON memory_state_deltas(applied);
```

---

## Block Integration

Conversations, messages, and memories all exist as blocks in the existing block-based architecture:

### Block Types

```
conversation          — Container for an interaction session
message               — Individual message within a conversation
memory                — Compressed meaning extracted from a conversation
```

> **Note on memory_entity:** Extracted entities (people, tasks, decisions, waiting-ons) are stored in the `memory_entities` **relational table**, not as blocks in the block hierarchy. Each entity row references a parent memory via `memory_id`. The hierarchy diagram below shows entities nested under memories for conceptual clarity — they are logically children of memories, but physically stored as table rows, not blocks. This keeps the block tree clean (Acts → memories) while allowing structured querying of entities across memories.

### Hierarchy

```
Your Story (Act, permanent, type: act)
  ├── memory: "Decided on Thunderbird priority" (type: memory, block)
  │     ├── entity: task "recurring event support" (memory_entities table)
  │     ├── entity: decision "events before Scene UI" (memory_entities table)
  │     └── [link → archived conversation #47]
  ├── memory: "Explored patience as architecture" (type: memory, block)
  │     └── [link → archived conversation #46]
  └── ...

Building Talking Rock (Act)
  ├── Architecture Notes (page)
  ├── memory: "Designed conversation lifecycle" (type: memory, block)
  │     ├── entity: decision "one conversation at a time" (memory_entities table)
  │     ├── entity: decision "memories not summaries" (memory_entities table)
  │     └── [link → archived conversation #48]
  └── ...

Archived Conversations (system container, not user-facing Act)
  ├── conversation #46 (type: conversation, status: archived)
  │     ├── message: user "Let the game choose us" (type: message)
  │     ├── message: cairn "A rock sits by a river..." (type: message)
  │     └── ...
  ├── conversation #47 (type: conversation, status: archived)
  └── conversation #48 (type: conversation, status: archived)
```

A single conversation can produce memories in multiple destinations. Each memory links back to the source conversation. The conversation archive is browsable but separate from the active knowledge graph.

---

## LLM Prompt Templates

Local inference is the engine for every stage. These prompts are designed for 1-3B parameter models running on Ollama.

### Entity Extraction Prompt

```
<system>
You are an entity extractor for a personal knowledge system. Given a conversation
transcript, extract structured entities. Be precise. Only extract what is explicitly
stated or strongly implied. Do not invent or assume.

Output valid JSON only. No preamble. No explanation.
</system>

<user>
Extract entities from this conversation:

---
{conversation_transcript}
---

Extract into this structure:
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

Only include categories that have entities. Empty categories should be omitted.
</user>
```

### Narrative Memory Prompt

```
<system>
You are a memory synthesizer. Given extracted entities from a conversation, write
a brief narrative that captures the MEANING of the conversation — not what was said,
but what it signified. Write as if you're a thoughtful colleague remembering what
mattered about a discussion.

Keep it to 2-4 sentences. Focus on decisions, shifts in understanding, and what
changed. Do not summarize the transcript. Synthesize the significance.
</system>

<user>
Conversation entities:
{extracted_entities_json}

Conversation context:
- Active Act: {active_act_name}
- Active Scene: {active_scene_name}  
- Date: {conversation_date}
- Duration: {conversation_duration}

Write the memory narrative.
</user>
```

### State Delta Prompt

```
<system>
You are a state change detector. Given the entities extracted from a conversation
and the current state of open threads, waiting-ons, and priorities, determine what
changed.

Output valid JSON only.
</system>

<user>
Current open state:
{current_open_threads_json}

Newly extracted entities:
{extracted_entities_json}

Determine state changes:
{
  "new_waiting_ons": [{"who": "", "what": ""}],
  "resolved_waiting_ons": [{"who": "", "what": ""}],
  "new_open_threads": [{"thread": "", "act": ""}],
  "resolved_threads": [{"thread": ""}],
  "priority_changes": [{"item": "", "old": "", "new": ""}]
}

Only include categories with actual changes. Be conservative — only mark something
resolved if the conversation explicitly resolves it.
</user>
```

### Act Routing Suggestion Prompt

```
<system>
You are a routing advisor. Given a memory and the user's active Acts, suggest which
Act this memory belongs to. If it doesn't clearly belong to any Act, suggest "Your Story."

Output JSON only.
</system>

<user>
Memory narrative:
{memory_narrative}

Memory entities:
{extracted_entities_summary}

Active Acts:
{active_acts_list}

Suggest routing:
{
  "suggested_destination": "act_name or Your Story",
  "confidence": 0.0-1.0,
  "reasoning": "brief explanation"
}
</user>
```

---

## CAIRN Integration

### Startup Greeting Enhancement

Memories feed directly into CAIRN's startup greeting. The existing design surfaces open threads, waiting-ons, upcoming deadlines, and stale items. Memories are the source of truth for all of these:

```python
def build_startup_greeting(user_id: str) -> str:
    """
    Build CAIRN's startup greeting from accumulated memories.
    """
    # Active entities from memories
    open_threads = query_active_entities(user_id, entity_type='question_opened')
    waiting_ons = query_active_entities(user_id, entity_type='waiting_on')
    recent_decisions = query_recent_entities(user_id, entity_type='decision', days=7)
    
    # Calendar integration (existing)
    upcoming_scenes = get_upcoming_scenes(user_id, horizon_days=7)
    
    # Staleness detection
    stale_tasks = query_stale_entities(user_id, entity_type='task', stale_days=5)
    
    # Active conversation check
    active_conversation = get_active_conversation(user_id)
    
    if active_conversation:
        return build_resume_greeting(active_conversation)
    else:
        return build_fresh_greeting(
            open_threads, waiting_ons, recent_decisions,
            upcoming_scenes, stale_tasks
        )
```

### Memory-Aware Conversation Context

When the user starts a new conversation, CAIRN retrieves relevant memories via semantic search to inform the interaction:

```python
def get_conversation_context(user_message: str, user_id: str) -> str:
    """
    Retrieve relevant memories to inform the current conversation.
    """
    # Semantic search across memory embeddings
    relevant_memories = semantic_search_memories(
        query=user_message,
        user_id=user_id,
        top_k=5
    )
    
    # Also get recent memories regardless of semantic match
    recent_memories = get_recent_memories(user_id, count=3)
    
    # Combine and deduplicate
    context_memories = deduplicate(relevant_memories + recent_memories)
    
    return format_memory_context(context_memories)
```

### Cross-Conversation Thread Resolution

When entities from a new conversation match open entities from previous memories, Talking Rock can detect resolution:

```python
def check_thread_resolution(new_entities: list, user_id: str) -> list:
    """
    Check if newly extracted entities resolve open threads from previous memories.
    """
    resolutions = []
    open_entities = query_active_entities(user_id)
    
    for new_entity in new_entities:
        for open_entity in open_entities:
            # Use local LLM to assess if new entity resolves open one
            resolution_check = llm_check_resolution(new_entity, open_entity)
            if resolution_check['resolves'] and resolution_check['confidence'] > 0.7:
                resolutions.append({
                    'resolved': open_entity,
                    'resolved_by': new_entity,
                    'confidence': resolution_check['confidence']
                })
    
    return resolutions
```

---

## Memories as Active Reasoning Context

### The Core Insight

Every other AI system treats memory as a nice-to-have — a way to recall your name or preferences. Talking Rock treats memory as the **primary substrate for reasoning**. When a request arrives, before classification, before decomposition, before verification, memories are searched. They inform every stage of the pipeline.

This is what transforms a 1-3B parameter model from a generic assistant into an assistant that *knows you*. The model's weights encode general capability. The memories encode *your* patterns, *your* context, *your* open threads, *your* vocabulary.

### Integration with the Atomic Operations Pipeline

The existing atomic operations pipeline (from CLAUDE_CODE_IMPLEMENTATION_GUIDE_V2.md) processes every request through: classify → verify → execute → learn. Memories participate in all four stages.

#### Stage 1: Intent Classification with Memory

When a new request arrives, CAIRN retrieves relevant memories *before* classifying intent.

```python
def classify_with_memory(user_request: str, user_id: str) -> dict:
    """
    Classify user intent using memory-augmented context.
    
    Without memory: "fix the calendar thing" → ambiguous, needs clarification
    With memory: "fix the calendar thing" → recalls memory about Thunderbird 
                  recurring events being broken → classifies as specific task
    """
    # Step 1: Semantic search across memory embeddings
    relevant_memories = semantic_search_memories(
        query=user_request,
        user_id=user_id,
        top_k=5
    )
    
    # Step 2: Also retrieve active entities (open threads, waiting-ons)
    active_context = get_active_entities(user_id)
    
    # Step 3: Build memory-augmented prompt for classification
    classification_prompt = build_classification_prompt(
        request=user_request,
        memories=relevant_memories,
        active_context=active_context
    )
    
    # Step 4: Local LLM classifies with full context
    # This is where cheap inference matters — we're adding a retrieval step
    # AND a richer prompt, both of which cost nothing locally
    classification = ollama_classify(classification_prompt)
    
    # Step 5: Store which memories influenced classification (transparency)
    store_classification_memory_references(
        classification_id=classification['id'],
        memory_ids=[m['id'] for m in relevant_memories],
        influence_scores=classification.get('memory_relevance_scores', [])
    )
    
    return classification
```

**Memory-Augmented Classification Prompt:**

```
<s>
You are classifying a user request into an atomic operation. You have access to 
the user's relevant memories from past conversations. Use these memories to 
disambiguate intent, resolve references, and understand context.

If a memory directly relates to the request, reference it in your reasoning.
If the request is ambiguous even with memory context, flag it for clarification.
</s>

<user>
User request: "{user_request}"

Relevant memories:
{formatted_memories}

Active open threads:
{active_threads}

Classify this request:
- destination_type: stream (realtime output) | file (persistent storage) | process (system execution)
- consumer_type: human (user will read) | machine (system will process)  
- execution_semantics: read (retrieve info) | interpret (analyze/synthesize) | execute (take action)
- confidence: 0.0-1.0
- memory_used: which memories informed this classification and how
- needs_clarification: true/false
- clarification_question: if ambiguous, what to ask

Output valid JSON only.
</user>
```

#### Stage 2: Decomposition with Memory

When a complex request is decomposed into atomic operations, memories inform what sub-tasks are needed and what order makes sense — because Talking Rock remembers how similar requests were handled before.

```python
def decompose_with_memory(
    user_request: str,
    classification: dict,
    user_id: str
) -> list:
    """
    Decompose complex request into atomic operations, informed by memory.
    
    Without memory: Generic decomposition based on request text alone
    With memory: Recalls past similar tasks, user preferences for ordering,
                 known blockers, and established patterns
    """
    # Search for memories of similar past tasks
    similar_task_memories = semantic_search_memories(
        query=f"task decomposition {user_request}",
        user_id=user_id,
        top_k=3,
        entity_type_filter='task'
    )
    
    # Search for relevant decisions that might constrain decomposition
    relevant_decisions = semantic_search_memories(
        query=user_request,
        user_id=user_id,
        top_k=3,
        entity_type_filter='decision'
    )
    
    # Search for known blockers
    active_blockers = query_active_entities(
        user_id=user_id,
        entity_type='blocker_cleared',  # inverted — find UN-cleared blockers
        is_active=True
    )
    
    decomposition_prompt = build_decomposition_prompt(
        request=user_request,
        classification=classification,
        similar_tasks=similar_task_memories,
        decisions=relevant_decisions,
        blockers=active_blockers
    )
    
    return ollama_decompose(decomposition_prompt)
```

#### Stage 3: Verification with Memory

During verification, memories serve as ground truth for intent verification — the system checks whether its understanding matches the user's established patterns and stated preferences.

```python
def verify_intent_with_memory(
    operation: dict,
    user_id: str
) -> dict:
    """
    Verify that the proposed operation matches user intent,
    using memories as reference for the user's established patterns.
    
    Example: User says "clean up the project"
    - Without memory: Could mean delete files, reorganize, refactor
    - With memory: Recalls user previously meant "archive completed Acts 
      and update stale todos" when they said "clean up"
    """
    # Find memories where similar language was used
    language_pattern_memories = semantic_search_memories(
        query=operation['user_request'],
        user_id=user_id,
        top_k=5
    )
    
    # Find memories where the same entities are referenced
    entity_memories = search_memories_by_entity(
        entities=operation.get('referenced_entities', []),
        user_id=user_id
    )
    
    verification_prompt = build_intent_verification_prompt(
        operation=operation,
        language_memories=language_pattern_memories,
        entity_memories=entity_memories
    )
    
    result = ollama_verify(verification_prompt)
    
    # If verification confidence is low, suggest clarification
    # informed by what memories *almost* matched
    if result['confidence'] < 0.7:
        result['suggested_clarification'] = generate_clarification_from_memories(
            operation, language_pattern_memories, entity_memories
        )
    
    return result
```

**Memory-Augmented Intent Verification Prompt:**

```
<s>
You are verifying that a proposed operation matches the user's actual intent.
You have access to memories from past conversations where the user expressed
similar requests or referenced similar entities. Use these to assess whether
the proposed operation is what the user likely means.

If memories suggest a different interpretation, flag the discrepancy.
If memories confirm the interpretation, note which ones and why.
</s>

<user>
Proposed operation:
  Request: "{user_request}"
  Classification: {destination} × {consumer} × {semantics}
  Proposed action: "{proposed_action_description}"

Relevant memories (past conversations where user expressed similar intent):
{formatted_memories}

Related entity memories (past conversations referencing same people/tasks/projects):
{entity_memories}

Verify intent:
{
  "matches_intent": true/false,
  "confidence": 0.0-1.0,
  "supporting_memories": ["memory_ids that confirm this interpretation"],
  "conflicting_memories": ["memory_ids that suggest different interpretation"],
  "reasoning": "explanation of verification logic",
  "alternative_interpretation": "if confidence < 0.7, what else might user mean"
}
</user>
```

#### Stage 4: Learning with Memory

After execution, the outcome becomes material for the next memory. The feedback loop closes:

```python
def learn_from_outcome(
    operation: dict,
    outcome: dict,
    user_feedback: dict,
    user_id: str
) -> None:
    """
    Outcome becomes part of the conversation's eventual memory.
    
    If user corrected the classification → future memories include that correction
    If user approved without changes → pattern confidence increases
    If user rejected → memories record what went wrong and why
    
    This all happens within the active conversation. When the conversation
    closes, the compression pipeline extracts these patterns as memory entities.
    """
    # Record outcome in conversation messages (will be compressed later)
    add_system_message(
        conversation_id=get_active_conversation(user_id),
        content=format_outcome_record(operation, outcome, user_feedback),
        message_type='system_learning'
    )
    
    # If user corrected classification, immediately update active context
    # (don't wait for conversation closure — this is actionable now)
    if user_feedback.get('corrected_classification'):
        store_immediate_correction(
            operation_id=operation['id'],
            original=operation['classification'],
            corrected=user_feedback['corrected_classification'],
            user_id=user_id
        )
```

### Memory Search Architecture

All memory search uses a hybrid approach — vector similarity for semantic matching, plus structured queries for entity-level precision:

```python
def semantic_search_memories(
    query: str,
    user_id: str,
    top_k: int = 5,
    entity_type_filter: str = None,
    act_filter: str = None,
    recency_weight: float = 0.3
) -> list:
    """
    Hybrid search: vector similarity + structured filtering + recency weighting.
    
    1. Generate query embedding (local sentence transformer, ~5ms)
    2. Vector similarity search across memory embeddings
    3. Filter by entity type, act, etc.
    4. Weight by recency (recent memories slightly preferred)
    5. Return ranked results with relevance scores
    """
    # Generate embedding for query
    query_embedding = embed_text(query)  # all-MiniLM-L6-v2, local
    
    # Vector search with optional filters
    results = vector_search(
        embedding=query_embedding,
        table='memories',
        user_id=user_id,
        top_k=top_k * 2,  # Over-fetch, then re-rank
        filters={
            'entity_type': entity_type_filter,
            'act_id': act_filter
        }
    )
    
    # Recency re-ranking
    for result in results:
        age_days = (now() - result['created_at']).days
        recency_score = 1.0 / (1.0 + age_days * 0.1)  # Decay function
        result['final_score'] = (
            (1 - recency_weight) * result['similarity_score'] +
            recency_weight * recency_score
        )
    
    # Sort by final score, return top_k
    results.sort(key=lambda r: r['final_score'], reverse=True)
    return results[:top_k]


def search_memories_by_entity(
    entities: list,
    user_id: str,
    top_k: int = 5
) -> list:
    """
    Search memories by referenced entities — find memories that mention
    the same people, tasks, or projects as the current request.
    """
    entity_memories = []
    
    for entity in entities:
        matches = query_memory_entities(
            user_id=user_id,
            entity_type=entity.get('type'),
            entity_name=entity.get('name'),
            is_active=None  # Include both active and resolved
        )
        entity_memories.extend(matches)
    
    # Deduplicate by memory_id, keep highest relevance
    seen = {}
    for mem in entity_memories:
        mid = mem['memory_id']
        if mid not in seen or mem['relevance'] > seen[mid]['relevance']:
            seen[mid] = mem
    
    return sorted(seen.values(), key=lambda m: m['relevance'], reverse=True)[:top_k]
```

### The Compounding Effect

This is where Talking Rock diverges from every other assistant fundamentally. Each conversation makes the next one better:

**Week 1:** User says "check the calendar." Talking Rock asks: "Which calendar integration? What are you looking for?"

**Month 1:** User says "check the calendar." Talking Rock recalls 15 memories referencing Thunderbird and knows the user always means "what's coming up this week that I should prepare for." Classifies directly, no clarification needed.

**Month 6:** User says "check the calendar." Talking Rock retrieves memories, notices the user has a pattern of checking the calendar on Monday mornings before their 1:1, and proactively includes: "Your 1:1 is at 10am. Based on last week's conversation, you wanted to raise the deployment timeline."

This progression — from generic tool to contextual assistant to proactive partner — is only possible because memories are indexed, embedded, and queried at every reasoning step. And it's only economically viable because every one of those retrieval and inference passes costs nothing locally.

### Memory Transparency in Reasoning

When memories influence a classification or verification, the user can see which ones and why. This is stored in the `classification_memory_references` table:

```sql
CREATE TABLE IF NOT EXISTS classification_memory_references (
    id TEXT PRIMARY KEY,
    classification_id TEXT NOT NULL,      -- Which classification used this memory
    memory_id TEXT NOT NULL,              -- Which memory was referenced
    influence_type TEXT NOT NULL,         -- 'disambiguation', 'pattern_match', 
                                          -- 'entity_reference', 'intent_verification'
    influence_score REAL,                 -- How much this memory influenced the decision
    reasoning TEXT,                       -- Why this memory was relevant
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

CREATE INDEX idx_memory_refs_classification ON classification_memory_references(classification_id);
CREATE INDEX idx_memory_refs_memory ON classification_memory_references(memory_id);
```

When the user asks "why did you interpret it that way?", Talking Rock can trace back through classification_memory_references to show exactly which past conversations informed the current interpretation. Full transparency. No hidden reasoning.

---

## MCP Tool Definitions

```python
MCP_TOOLS = {
    'get_active_conversation': {
        'description': 'Get the currently active conversation, if any',
        'parameters': {}
    },
    'close_conversation': {
        'description': 'Initiate conversation closure and compression',
        'parameters': {
            'conversation_id': 'UUID of the active conversation'
        }
    },
    'get_memory_preview': {
        'description': 'Get the compression preview before user confirms archival',
        'parameters': {
            'conversation_id': 'UUID of the conversation being closed'
        }
    },
    'confirm_memory': {
        'description': 'Confirm memory extraction and archive conversation',
        'parameters': {
            'memory_id': 'UUID of the memory to confirm',
            'destination_act_id': 'UUID of destination Act (NULL for Your Story)',
            'edited_narrative': 'Optional edited narrative text'
        }
    },
    'resume_conversation': {
        'description': 'Cancel closure and resume the conversation',
        'parameters': {
            'conversation_id': 'UUID of the conversation to resume'
        }
    },
    'search_memories': {
        'description': 'Semantic search across all memories',
        'parameters': {
            'query': 'Search query',
            'act_id': 'Optional: limit to specific Act',
            'your_story_only': 'Optional: limit to Your Story',
            'limit': 'Max results (default 10)'
        }
    },
    'get_open_threads': {
        'description': 'Get all active/unresolved entities across memories',
        'parameters': {
            'entity_type': 'Optional: filter by type',
            'act_id': 'Optional: filter by Act'
        }
    },
    'get_your_story': {
        'description': 'Get recent memories from Your Story',
        'parameters': {
            'limit': 'Max memories to return (default 20)',
            'offset': 'Pagination offset'
        }
    },
    'get_conversation_archive': {
        'description': 'Retrieve archived conversation transcript',
        'parameters': {
            'conversation_id': 'UUID of the archived conversation'
        }
    },
    'edit_memory': {
        'description': 'Edit a memory narrative or entities after archival',
        'parameters': {
            'memory_id': 'UUID of the memory',
            'narrative': 'Optional: updated narrative',
            'entities_to_remove': 'Optional: entity IDs to remove',
            'entities_to_add': 'Optional: new entities to add'
        }
    },
    'get_reasoning_context': {
        'description': 'Retrieve memory-augmented reasoning context for a request',
        'parameters': {
            'query': 'The user request or intent to contextualize',
            'context_type': 'classification | decomposition | verification',
            'include_active_entities': 'Boolean: include open threads/waiting-ons',
            'top_k': 'Number of memories to retrieve (default 5)'
        }
    },
    'explain_classification': {
        'description': 'Show which memories influenced a classification decision',
        'parameters': {
            'classification_id': 'UUID of the classification to explain'
        }
    },
    'get_memory_influence_chain': {
        'description': 'Trace how a specific memory has influenced subsequent reasoning',
        'parameters': {
            'memory_id': 'UUID of the memory to trace',
            'limit': 'Max influence events to return'
        }
    }
}
```

---

## Your Story: The Permanent Act

### Schema

Your Story is created automatically on first use and cannot be deleted or archived:

```sql
-- Created during initial setup
INSERT INTO blocks (id, type, parent_id, position) 
VALUES ('your-story-root', 'act', NULL, 0);

INSERT INTO block_properties (block_id, key, value) VALUES
    ('your-story-root', 'title', '"Your Story"'),
    ('your-story-root', 'status', '"permanent"'),
    ('your-story-root', 'is_your_story', '"true"'),
    ('your-story-root', 'description', '"The ongoing narrative of who you are, across all Acts and all time."');
```

### What Accumulates in Your Story

Over time, Your Story contains:
- Memories from conversations that aren't project-specific
- Personal insights and reflections
- Cross-cutting decisions that affect multiple Acts
- Patterns that CAIRN notices across your behavior
- The user's evolving priorities and values

### Your Story as Identity Context

When CAIRN needs to understand *who you are* (not just what you're working on), it queries Your Story:

```python
def get_identity_context(user_id: str) -> str:
    """
    Build identity context from Your Story for prompts that need
    to understand the user as a person, not just a task-doer.
    """
    recent_story = get_your_story_memories(user_id, limit=10)
    
    # Extract recurring themes via local LLM
    themes = extract_themes(recent_story)
    
    return format_identity_context(themes, recent_story)
```

---

## Implementation Phases

### Phase 1: Conversation Singleton & Messages (Priority)

**Database:**
- Create `conversations` table
- Create `messages` table  
- Add block types: `conversation`, `message`
- Enforce singleton constraint at application level

**Backend:**
- `start_conversation()` — creates conversation, fails if one is active
- `add_message()` — appends message to active conversation
- `get_active_conversation()` — returns current conversation or None

**Frontend:**
- On startup: check for active conversation
- If active: resume it, show conversation history
- If none: show CAIRN startup greeting with "start conversation" implicit in first message

**Tests:**
- Cannot create two active conversations
- Messages ordered correctly
- Resuming conversation loads full history

### Phase 2: Conversation Closure & Compression

**Backend:**
- `close_conversation()` — transitions to ready_to_close
- Entity extraction pipeline (Ollama inference)
- Narrative memory generation (Ollama inference)
- State delta computation
- Embedding generation (sentence transformers)

**Frontend:**
- Close button / "I'm done" interaction
- Memory preview screen
- Edit/redirect/split controls
- Confirm/resume buttons

**Tests:**
- Compression produces valid entities
- Narrative is meaning-level, not transcript-level
- State deltas correctly identify changes
- Round-trip: close → preview → resume returns to active state

### Phase 3: Memory Storage & Routing

**Database:**
- Create `memories` table
- Create `memory_entities` table
- Create `memory_state_deltas` table
- Your Story auto-creation on first run

**Backend:**
- `confirm_memory()` — stores memory, applies deltas, archives conversation
- `route_memory()` — parents memory block under destination Act/Story
- `split_memory()` — creates multiple memories from one conversation
- State delta application to knowledge graph

**Frontend:**
- Memory routing UI (Your Story / Act selection)
- Split routing interface
- Automatic Act suggestion

### Phase 4: Memory as Reasoning Context

**Database:**
- Create `classification_memory_references` table
- Indexes for fast memory retrieval during classification

**Backend:**
- `semantic_search_memories()` — hybrid vector + structured search
- `search_memories_by_entity()` — entity-level memory lookup
- `classify_with_memory()` — memory-augmented classification
- `decompose_with_memory()` — memory-informed task decomposition
- `verify_intent_with_memory()` — memory-backed intent verification
- `store_classification_memory_references()` — transparency audit trail
- `explain_classification()` — trace which memories influenced a decision

**Integration:**
- Hook memory retrieval into existing atomic operations classifier
- Hook memory retrieval into existing verification engine
- Add memory context to all LLM prompt templates
- Ensure memory references are stored with every classification

**Prompts:**
- Memory-augmented classification prompt (for Ollama)
- Memory-augmented decomposition prompt
- Memory-augmented intent verification prompt
- Clarification generation prompt (when memories conflict or are insufficient)

**Tests:**
- Classification improves with relevant memories present
- Ambiguous requests resolved by memory context
- Memory references correctly stored and traceable
- `explain_classification` returns coherent reasoning chain
- Performance: memory retrieval adds < 100ms to classification pipeline

### Phase 5: The Compounding Loop

**Backend:**
- `learn_from_outcome()` — record corrections and approvals in conversation
- `store_immediate_correction()` — real-time pattern updates for corrections
- `check_thread_resolution()` — cross-conversation thread resolution
- Recency-weighted memory scoring (recent memories slightly preferred)
- Stale entity detection (entities that should have resolved but haven't)

**Frontend:**
- "Why did you interpret it that way?" — reasoning transparency view
- Memory influence visualization (which memories informed current response)
- Your Story browser — chronological and semantic views of accumulated memories
- Act memory browser — memories organized by Act with conversation links
- Memory edit/delete from browser views

**Tests:**
- Classification accuracy improves over 10+ conversations (integration test)
- Corrections propagate to future classifications
- Stale entities detected after configurable threshold
- Thread resolution correctly links across conversations
- Memory browser displays correctly with 100+ memories

---

## Philosophy Alignment

This architecture embodies Talking Rock's core principles:

**Local-first:** All memory storage is SQLite. All inference is Ollama. All embeddings are local sentence transformers. Nothing leaves the machine.

**Transparency:** Every memory is user-reviewed. Every classification is traceable to the memories that influenced it. "Why did you think I meant X?" is always answerable.

**User sovereignty:** The user can edit, delete, or redirect any memory. The user reviews what the system learned before it's stored. The user can export all memories as markdown.

**Attention as sacred labor:** One conversation at a time. Deliberate closure. The system honors the depth of each interaction rather than encouraging breadth.

**Patience as competitive advantage:** Multiple inference passes per conversation closure. Memory retrieval at every reasoning step. Re-ranking and re-scoring at each stage. All free locally. All prohibitively expensive for cloud providers at scale.

**Progressive trust:** Early conversations produce thin memories. As the memory database grows, Talking Rock's understanding deepens. The user can watch this progression — see the system getting better, memory by memory, in a way that's visible and verifiable.

---

## Cost Comparison: Why This Only Works Locally

| Operation | Cloud Cost (per request) | Local Cost |
|-----------|------------------------|------------|
| Memory embedding generation | $0.0001 per embedding | Free (sentence transformer, ~5ms) |
| Memory retrieval (5 memories) | $0.002 (API call + embedding search) | Free (SQLite + vector search, ~10ms) |
| Memory-augmented classification | $0.01-0.03 (larger prompt) | Free (Ollama, ~500ms) |
| Entity extraction (conversation close) | $0.05-0.15 (full transcript input) | Free (Ollama, ~2-5s) |
| Narrative compression | $0.02-0.05 | Free (Ollama, ~1-2s) |
| State delta computation | $0.01-0.03 | Free (Ollama, ~500ms) |
| Intent verification with memory | $0.02-0.05 | Free (Ollama, ~500ms) |
| **Total per conversation lifecycle** | **$0.13-0.34** | **Free** |
| **Total per classification (with memory)** | **$0.03-0.08** | **Free** |

At 20 conversations per day with 10 classifications each, cloud cost is $8-20/day. Locally: electricity.

This is why memories as active reasoning context — not just passive storage — is a capability that only a local-first architecture can afford to run for every single interaction.