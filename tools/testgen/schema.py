"""Database schema for Talking Rock test profiles (v17)."""

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_version (version INTEGER NOT NULL);
INSERT INTO schema_version VALUES (17);

-- Core Play System
CREATE TABLE IF NOT EXISTS acts (
    act_id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    active INTEGER NOT NULL DEFAULT 0,
    notes TEXT NOT NULL DEFAULT '',
    color TEXT,
    repo_path TEXT,
    artifact_type TEXT,
    code_config TEXT,
    root_block_id TEXT,
    system_role TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scenes (
    scene_id TEXT PRIMARY KEY,
    act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    stage TEXT NOT NULL DEFAULT 'planning',
    notes TEXT NOT NULL DEFAULT '',
    link TEXT,
    calendar_event_id TEXT,
    recurrence_rule TEXT,
    thunderbird_event_id TEXT,
    calendar_event_start TEXT,
    calendar_event_end TEXT,
    calendar_event_title TEXT,
    next_occurrence TEXT,
    calendar_name TEXT,
    category TEXT,
    disable_auto_complete INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_scenes_act_id ON scenes(act_id);
CREATE INDEX IF NOT EXISTS idx_scenes_calendar_event ON scenes(calendar_event_id);
CREATE INDEX IF NOT EXISTS idx_scenes_thunderbird_event ON scenes(thunderbird_event_id);
CREATE INDEX IF NOT EXISTS idx_scenes_next_occurrence ON scenes(next_occurrence);

CREATE TABLE IF NOT EXISTS attachments (
    attachment_id TEXT PRIMARY KEY,
    act_id TEXT REFERENCES acts(act_id) ON DELETE CASCADE,
    scene_id TEXT REFERENCES scenes(scene_id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    file_name TEXT NOT NULL,
    file_type TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pages (
    page_id TEXT PRIMARY KEY,
    act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
    parent_page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    icon TEXT,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

-- Block System
CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    parent_id TEXT,
    act_id TEXT NOT NULL REFERENCES acts(act_id) ON DELETE CASCADE,
    page_id TEXT REFERENCES pages(page_id) ON DELETE CASCADE,
    scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_blocks_parent ON blocks(parent_id);
CREATE INDEX IF NOT EXISTS idx_blocks_act ON blocks(act_id);
CREATE INDEX IF NOT EXISTS idx_blocks_page ON blocks(page_id);

CREATE TABLE IF NOT EXISTS block_properties (
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    key TEXT NOT NULL,
    value TEXT,
    PRIMARY KEY (block_id, key)
);

CREATE TABLE IF NOT EXISTS rich_text (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    position INTEGER NOT NULL DEFAULT 0,
    content TEXT NOT NULL,
    bold INTEGER DEFAULT 0,
    italic INTEGER DEFAULT 0,
    strikethrough INTEGER DEFAULT 0,
    code INTEGER DEFAULT 0,
    underline INTEGER DEFAULT 0,
    color TEXT,
    background_color TEXT,
    link_url TEXT
);

-- Memory Graph
CREATE TABLE IF NOT EXISTS block_relationships (
    id TEXT PRIMARY KEY,
    source_block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    target_block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    relationship_type TEXT NOT NULL,
    confidence REAL DEFAULT 1.0,
    weight REAL DEFAULT 1.0,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(source_block_id, target_block_id, relationship_type),
    CHECK(source_block_id != target_block_id)
);

CREATE TABLE IF NOT EXISTS block_embeddings (
    block_id TEXT PRIMARY KEY REFERENCES blocks(id) ON DELETE CASCADE,
    embedding BLOB NOT NULL,
    embedding_model TEXT DEFAULT 'all-MiniLM-L6-v2',
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- Conversations
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'active',
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_message_at TIMESTAMP,
    closed_at TIMESTAMP,
    archived_at TIMESTAMP,
    message_count INTEGER DEFAULT 0,
    compression_model TEXT,
    compression_duration_ms INTEGER,
    compression_passes INTEGER,
    is_paused BOOLEAN DEFAULT 0,
    paused_at TIMESTAMP,
    CHECK (status IN ('active', 'ready_to_close', 'compressing', 'archived'))
);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON conversations(status);

CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    position INTEGER NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    active_act_id TEXT,
    active_scene_id TEXT,
    CHECK (role IN ('user', 'cairn', 'reos', 'riva', 'system'))
);
CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id);

-- Memories
CREATE TABLE IF NOT EXISTS memories (
    id TEXT PRIMARY KEY,
    block_id TEXT NOT NULL REFERENCES blocks(id) ON DELETE CASCADE,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    narrative TEXT NOT NULL,
    narrative_embedding BLOB,
    destination_act_id TEXT,
    destination_page_id TEXT,
    is_your_story BOOLEAN DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'pending_review',
    user_reviewed BOOLEAN DEFAULT 0,
    user_edited BOOLEAN DEFAULT 0,
    original_narrative TEXT,
    extraction_model TEXT,
    extraction_confidence REAL,
    signal_count INTEGER NOT NULL DEFAULT 1,
    last_reinforced_at TEXT,
    source TEXT NOT NULL DEFAULT 'compression'
        CHECK (source IN ('compression', 'turn_assessment', 'priority_signal', 'claudecode')),
    cc_agent_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (destination_act_id) REFERENCES acts(act_id) ON DELETE SET NULL,
    CHECK (status IN ('pending_review', 'approved', 'rejected', 'superseded'))
);
CREATE INDEX IF NOT EXISTS idx_memories_conversation ON memories(conversation_id);
CREATE INDEX IF NOT EXISTS idx_memories_your_story ON memories(is_your_story);
CREATE INDEX IF NOT EXISTS idx_memories_status ON memories(status);

CREATE TABLE IF NOT EXISTS memory_entities (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_type TEXT NOT NULL,
    entity_data JSON NOT NULL,
    is_active BOOLEAN DEFAULT 1,
    resolved_by_memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    resolved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CHECK (entity_type IN (
        'person', 'task', 'decision', 'waiting_on',
        'question_resolved', 'question_opened',
        'blocker_cleared', 'priority_change',
        'act_reference', 'insight'
    ))
);

CREATE TABLE IF NOT EXISTS memory_state_deltas (
    id TEXT PRIMARY KEY,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    delta_type TEXT NOT NULL,
    delta_data JSON NOT NULL,
    applied BOOLEAN DEFAULT 0,
    applied_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS classification_memory_references (
    id TEXT PRIMARY KEY,
    classification_id TEXT NOT NULL,
    memory_id TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    influence_type TEXT NOT NULL,
    influence_score REAL,
    reasoning TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Conversation analytics
CREATE TABLE IF NOT EXISTS conversation_summaries (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL UNIQUE REFERENCES conversations(id),
    summary TEXT NOT NULL,
    summary_model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS state_briefings (
    id TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    content TEXT NOT NULL,
    token_count INTEGER,
    trigger TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turn_assessments (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    turn_position INTEGER NOT NULL,
    assessment TEXT NOT NULL,
    memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    raw_input TEXT,
    model_used TEXT,
    duration_ms INTEGER,
    created_at TEXT NOT NULL
);

-- Attention & Priority
CREATE TABLE IF NOT EXISTS attention_priorities (
    scene_id TEXT PRIMARY KEY REFERENCES scenes(scene_id) ON DELETE CASCADE,
    user_priority INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reorder_history (
    id TEXT PRIMARY KEY,
    reorder_timestamp TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    old_position INTEGER,
    new_position INTEGER NOT NULL,
    total_items INTEGER NOT NULL,
    act_id TEXT,
    act_title TEXT,
    scene_stage TEXT,
    urgency_at_reorder TEXT,
    has_calendar_event INTEGER DEFAULT 0,
    is_email INTEGER DEFAULT 0,
    hour_of_day INTEGER,
    day_of_week INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS priority_boost_rules (
    id TEXT PRIMARY KEY,
    feature_type TEXT NOT NULL,
    feature_value TEXT NOT NULL,
    boost_score REAL NOT NULL,
    confidence REAL NOT NULL,
    sample_count INTEGER NOT NULL,
    description TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(feature_type, feature_value)
);

-- Claude Code integration
CREATE TABLE IF NOT EXISTS cc_agents (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    purpose TEXT DEFAULT '',
    cwd TEXT NOT NULL,
    session_id TEXT,
    linked_scene_id TEXT REFERENCES scenes(scene_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cc_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL REFERENCES cc_agents(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cc_insights (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL REFERENCES cc_agents(id) ON DELETE CASCADE,
    session_completed_at TEXT NOT NULL,
    session_duration_s INTEGER,
    user_messages INTEGER NOT NULL DEFAULT 0,
    files_touched TEXT,
    insight_type TEXT NOT NULL,
    insight_text TEXT NOT NULL,
    memory_id TEXT REFERENCES memories(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'pending_review',
    created_at TEXT NOT NULL,
    CHECK (insight_type IN ('tracking', 'lesson', 'pattern', 'decision')),
    CHECK (status IN ('pending_review', 'accepted', 'dismissed'))
);

-- CairnStore tables
CREATE TABLE IF NOT EXISTS cairn_metadata (
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    last_touched TEXT,
    touch_count INTEGER DEFAULT 0,
    created_at TEXT,
    kanban_state TEXT DEFAULT 'backlog',
    waiting_on TEXT,
    waiting_since TEXT,
    priority INTEGER,
    priority_set_at TEXT,
    priority_reason TEXT,
    due_date TEXT,
    start_date TEXT,
    defer_until TEXT,
    PRIMARY KEY (entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS contact_links (
    link_id TEXT PRIMARY KEY,
    contact_id TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    relationship TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(contact_id, entity_type, entity_id)
);

CREATE TABLE IF NOT EXISTS activity_log (
    log_id TEXT PRIMARY KEY,
    timestamp TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    activity_type TEXT NOT NULL,
    details TEXT
);

CREATE TABLE IF NOT EXISTS pending_confirmations (
    confirmation_id TEXT PRIMARY KEY,
    tool_name TEXT NOT NULL,
    tool_args_json TEXT NOT NULL,
    description TEXT NOT NULL,
    warning TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    confirmed INTEGER DEFAULT 0,
    executed INTEGER DEFAULT 0,
    cancelled INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_pending_confirmations_created
    ON pending_confirmations(created_at);
CREATE INDEX IF NOT EXISTS idx_pending_confirmations_status
    ON pending_confirmations(confirmed, executed, cancelled);

CREATE TABLE IF NOT EXISTS undo_stack (
    undo_id TEXT PRIMARY KEY,
    action_type TEXT NOT NULL,
    entity_type TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    previous_state TEXT,
    new_state TEXT,
    created_at TEXT NOT NULL,
    description TEXT
);

-- Mock data tables (emails/calendar normally from Thunderbird)
CREATE TABLE IF NOT EXISTS mock_emails (
    id TEXT PRIMARY KEY,
    message_id TEXT NOT NULL,
    subject TEXT NOT NULL,
    sender TEXT NOT NULL,
    recipients TEXT NOT NULL,
    date TEXT NOT NULL,
    body TEXT NOT NULL,
    is_read INTEGER DEFAULT 0,
    folder TEXT DEFAULT 'Inbox',
    has_attachment INTEGER DEFAULT 0,
    importance TEXT DEFAULT 'normal'
);

CREATE TABLE IF NOT EXISTS mock_calendar_events (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    location TEXT DEFAULT '',
    description TEXT DEFAULT '',
    calendar_name TEXT DEFAULT 'Personal',
    all_day INTEGER DEFAULT 0,
    recurrence_rule TEXT,
    attendees TEXT DEFAULT '[]'
);

-- Atomic ops tables
CREATE TABLE IF NOT EXISTS atomic_operations (
    id TEXT PRIMARY KEY,
    block_id TEXT,
    user_request TEXT,
    user_id TEXT,
    destination_type TEXT,
    consumer_type TEXT,
    execution_semantics TEXT,
    classification_confident INTEGER DEFAULT 0,
    classification_reasoning TEXT,
    classification_model TEXT,
    is_decomposed INTEGER DEFAULT 0,
    parent_id TEXT,
    child_ids TEXT,
    status TEXT DEFAULT 'pending',
    source_agent TEXT,
    created_at TEXT,
    completed_at TEXT
);
"""
