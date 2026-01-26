# Talking Rock: Atomic Operations Implementation Guide for Claude Code

> **Note:** This guide has been split into focused documentation. For the conceptual foundation, see the new docs:
>
> - **[Foundation](docs/FOUNDATION.md)** — Core philosophy and architecture overview
> - **[Atomic Operations](docs/atomic-operations.md)** — 3x2x3 classification taxonomy
> - **[Verification Layers](docs/verification-layers.md)** — 5-layer verification system
> - **[RLHF Learning](docs/rlhf-learning.md)** — Feedback and learning loop
> - **[ML Features](docs/ml-features.md)** — Feature extraction and embeddings
> - **[Execution Engine](docs/execution-engine.md)** — Safe execution with undo
>
> This document remains as the detailed implementation reference with code samples.

**Complete Rebuild with ML-Ready Architecture and Rich RLHF**

For: Claude Code (Agentic Coding Assistant)
Project: Talking Rock
Version: 3.0 - Production Implementation
Date: January 2026

---

## Mission Statement

You are rebuilding Talking Rock from the ground up with three non-negotiable foundations:

1. **Atomic Operations** - Every user request decomposed into stream/file/process × human/machine × read/interpret/execute, stored as blocks
2. **ML-Ready from Day One** - Every classification, verification, execution tracked with features for supervised learning
3. **Rich RLHF** - Learn from user feedback at multiple levels: explicit ratings, corrections, behavioral signals, and temporal patterns

**This is not a spec. These are instructions. Execute them.**

---

## Phase 0: Architecture Foundation (Week 1)

### Step 0.1: Database Schema - Complete Rebuild

**Task:** Create new SQLite schema that integrates atomic operations, ML features, and RLHF from ground up.

**File:** `src/database/schema_v3.sql`

```sql
-- ============================================================================
-- TALKING ROCK v3.0 SCHEMA: ATOMIC OPERATIONS + ML + RLHF
-- ============================================================================

-- Enable foreign keys
PRAGMA foreign_keys = ON;

-- ============================================================================
-- CORE BLOCKS SYSTEM (from PLAY_KNOWLEDGEBASE_SPEC.md)
-- ============================================================================

CREATE TABLE IF NOT EXISTS blocks (
    id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    parent_id TEXT,
    position INTEGER,
    scene_id TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (parent_id) REFERENCES blocks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS block_properties (
    block_id TEXT,
    key TEXT,
    value TEXT,
    PRIMARY KEY (block_id, key),
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS rich_text (
    id TEXT PRIMARY KEY,
    block_id TEXT,
    position INTEGER,
    content TEXT,
    bold BOOLEAN DEFAULT 0,
    italic BOOLEAN DEFAULT 0,
    strikethrough BOOLEAN DEFAULT 0,
    code BOOLEAN DEFAULT 0,
    underline BOOLEAN DEFAULT 0,
    color TEXT,
    background_color TEXT,
    link_url TEXT,
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE
);

-- ============================================================================
-- ATOMIC OPERATIONS - CLASSIFICATION
-- ============================================================================

CREATE TABLE atomic_operations (
    block_id TEXT PRIMARY KEY,
    
    -- User input
    user_request TEXT NOT NULL,
    user_id TEXT NOT NULL,
    
    -- Classification result
    destination_type TEXT,              -- 'stream', 'file', 'process'
    consumer_type TEXT,                 -- 'human', 'machine'
    execution_semantics TEXT,           -- 'read', 'interpret', 'execute'
    
    -- Classification metadata
    classification_confidence REAL,
    classification_pass_number INTEGER DEFAULT 1,
    requires_decomposition BOOLEAN DEFAULT 0,
    
    -- Decomposition
    is_decomposed BOOLEAN DEFAULT 0,
    decomposed_from TEXT,               -- Parent operation if this is child
    decomposed_into JSON,               -- Array of child operation IDs
    
    -- Execution state
    status TEXT NOT NULL,               -- 'classifying', 'awaiting_approval', 'executing', 'complete', 'failed'
    
    -- Timestamps
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMP,
    
    FOREIGN KEY (block_id) REFERENCES blocks(id) ON DELETE CASCADE,
    FOREIGN KEY (decomposed_from) REFERENCES atomic_operations(block_id) ON DELETE CASCADE,
    
    CHECK (destination_type IN ('stream', 'file', 'process') OR destination_type IS NULL),
    CHECK (consumer_type IN ('human', 'machine') OR consumer_type IS NULL),
    CHECK (execution_semantics IN ('read', 'interpret', 'execute') OR execution_semantics IS NULL),
    CHECK (status IN ('classifying', 'awaiting_approval', 'executing', 'complete', 'failed', 'cancelled'))
);

CREATE INDEX idx_atomic_operations_user ON atomic_operations(user_id);
CREATE INDEX idx_atomic_operations_status ON atomic_operations(status);
CREATE INDEX idx_atomic_operations_created ON atomic_operations(created_at);

-- ============================================================================
-- CLASSIFICATION REASONING (for transparency and learning)
-- ============================================================================

CREATE TABLE classification_reasoning (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,
    pass_number INTEGER NOT NULL,
    
    -- Indicators detected
    persistence_indicators JSON NOT NULL,
    execution_indicators JSON NOT NULL,
    immediacy_indicators JSON NOT NULL,
    code_indicators JSON NOT NULL,
    
    -- Reasoning
    persistence_required BOOLEAN,
    persistence_reasoning TEXT,
    execution_required BOOLEAN,
    execution_reasoning TEXT,
    immediate_execution BOOLEAN,
    immediacy_reasoning TEXT,
    code_detected BOOLEAN,
    code_reasoning TEXT,
    
    -- Classification decision
    destination_type TEXT,
    consumer_type TEXT,
    execution_semantics TEXT,
    confidence REAL NOT NULL,
    
    -- Alternatives considered (for ML training)
    alternatives_considered JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id) ON DELETE CASCADE
);

CREATE INDEX idx_classification_reasoning_operation ON classification_reasoning(operation_block_id);
CREATE INDEX idx_classification_reasoning_confidence ON classification_reasoning(confidence);

-- ============================================================================
-- ML FEATURES - EXTRACTED AT CLASSIFICATION TIME
-- ============================================================================

CREATE TABLE ml_features (
    operation_block_id TEXT PRIMARY KEY,
    
    -- Raw features (JSON for flexibility during iteration)
    features_json JSON NOT NULL,
    
    -- Embeddings (binary blobs, float32 arrays)
    request_embedding BLOB NOT NULL,
    verb_embeddings BLOB,
    object_embeddings BLOB,
    
    -- Scalar features (for fast querying)
    token_count INTEGER,
    verb_count INTEGER,
    noun_count INTEGER,
    has_file_extension BOOLEAN,
    file_extension_type TEXT,
    mentions_code BOOLEAN,
    mentions_system_resource BOOLEAN,
    has_imperative_verb BOOLEAN,
    has_interrogative BOOLEAN,
    ambiguity_score REAL,
    
    -- Context at time of operation
    system_context JSON,
    user_context JSON,
    temporal_context JSON,
    
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id) ON DELETE CASCADE
);

-- ============================================================================
-- RLHF: USER FEEDBACK - MULTI-DIMENSIONAL
-- ============================================================================

CREATE TABLE user_feedback (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,
    user_id TEXT NOT NULL,
    
    -- Feedback type
    feedback_type TEXT NOT NULL,        -- 'explicit_rating', 'correction', 'approval', 'behavioral'
    
    -- Explicit feedback
    rating INTEGER,                     -- 1-5 if explicit rating given
    rating_dimensions JSON,             -- {accuracy: 4, speed: 5, helpfulness: 3}
    comment TEXT,
    
    -- Correction feedback (classification was wrong)
    system_classification JSON,
    user_corrected_classification JSON,
    correction_reasoning TEXT,
    
    -- Approval feedback
    approved BOOLEAN,
    modified BOOLEAN,
    modification_extent REAL,           -- 0.0-1.0, how much was changed
    modification_details JSON,
    
    -- Behavioral feedback (implicit)
    time_to_decision_ms INTEGER,
    retried BOOLEAN DEFAULT 0,
    time_to_retry_ms INTEGER,
    undid BOOLEAN DEFAULT 0,
    time_to_undo_ms INTEGER,
    abandoned BOOLEAN DEFAULT 0,
    
    -- Long-term outcome
    operation_persisted BOOLEAN,
    days_persisted INTEGER,
    reused_pattern BOOLEAN DEFAULT 0,
    referenced_later BOOLEAN DEFAULT 0,
    
    -- Meta-feedback (feedback about feedback quality)
    feedback_confidence REAL,           -- How confident is user in this feedback?
    feedback_context TEXT,              -- Why did user provide this feedback?
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id) ON DELETE CASCADE,
    
    CHECK (feedback_type IN ('explicit_rating', 'correction', 'approval', 'behavioral', 'long_term')),
    CHECK (rating IS NULL OR (rating >= 1 AND rating <= 5))
);

CREATE INDEX idx_user_feedback_operation ON user_feedback(operation_block_id);
CREATE INDEX idx_user_feedback_user ON user_feedback(user_id);
CREATE INDEX idx_user_feedback_type ON user_feedback(feedback_type);
CREATE INDEX idx_user_feedback_created ON user_feedback(created_at);

-- ============================================================================
-- RLHF: LEARNING PROGRESS - TRACK IMPROVEMENT OVER TIME
-- ============================================================================

CREATE TABLE rlhf_learning_metrics (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    metric_type TEXT NOT NULL,          -- 'classification_accuracy', 'user_satisfaction', 'correction_rate'
    
    -- Time window
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,
    window_size_days INTEGER NOT NULL,
    
    -- Metric value
    metric_value REAL NOT NULL,
    sample_size INTEGER NOT NULL,
    
    -- Breakdown by category
    by_destination_type JSON,
    by_consumer_type JSON,
    by_execution_semantics JSON,
    
    -- Comparison to previous window
    previous_value REAL,
    improvement REAL,                   -- positive = better, negative = worse
    
    -- Statistical significance
    confidence_interval JSON,           -- {lower: X, upper: Y}
    p_value REAL,
    
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    CHECK (metric_type IN ('classification_accuracy', 'user_satisfaction', 'correction_rate', 
                          'approval_rate', 'retry_rate', 'undo_rate', 'time_to_decision'))
);

CREATE INDEX idx_rlhf_metrics_user ON rlhf_learning_metrics(user_id);
CREATE INDEX idx_rlhf_metrics_type ON rlhf_learning_metrics(metric_type);
CREATE INDEX idx_rlhf_metrics_window ON rlhf_learning_metrics(window_end);

-- ============================================================================
-- RLHF: FEEDBACK QUALITY - META-EVALUATION
-- ============================================================================

CREATE TABLE feedback_quality_metrics (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    
    -- Feedback consistency (does user feedback align over time?)
    consistency_score REAL,             -- 0.0-1.0
    consistency_sample_size INTEGER,
    
    -- Feedback informativeness (does feedback help learning?)
    informativeness_score REAL,         -- 0.0-1.0
    labeled_examples_count INTEGER,
    correction_details_provided INTEGER,
    
    -- Feedback reliability (can we trust this user's feedback?)
    reliability_score REAL,             -- 0.0-1.0
    reliability_basis TEXT,             -- 'outcomes', 'consensus', 'temporal_consistency'
    
    -- Feedback engagement
    explicit_feedback_rate REAL,        -- % operations with explicit feedback
    implicit_signals_available REAL,    -- % operations with behavioral signals
    
    -- Feedback latency
    avg_feedback_latency_ms INTEGER,
    feedback_recency_score REAL,        -- Recent feedback weighted higher
    
    -- Feedback breadth
    operation_types_covered JSON,       -- Which operation types does user provide feedback on?
    feedback_distribution JSON,         -- Distribution across rating dimensions
    
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL
);

CREATE INDEX idx_feedback_quality_user ON feedback_quality_metrics(user_id);
CREATE INDEX idx_feedback_quality_window ON feedback_quality_metrics(window_end);

-- ============================================================================
-- VERIFICATION & EXECUTION (simplified for now)
-- ============================================================================

CREATE TABLE operation_verification (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,
    
    verification_layer TEXT NOT NULL,   -- 'syntax', 'semantic', 'safety', 'intent'
    required BOOLEAN NOT NULL,
    
    passed BOOLEAN,
    confidence REAL,
    issues_found JSON,
    execution_time_ms INTEGER,
    
    verified_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id) ON DELETE CASCADE,
    
    CHECK (verification_layer IN ('syntax', 'semantic', 'behavioral', 'safety', 'intent'))
);

CREATE TABLE operation_execution (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,
    
    executor TEXT NOT NULL,             -- 'shell', 'python', 'system'
    
    success BOOLEAN NOT NULL,
    exit_code INTEGER,
    stdout TEXT,
    stderr TEXT,
    duration_ms INTEGER,
    
    files_affected JSON,
    processes_spawned JSON,
    
    state_before JSON,
    state_after JSON,
    
    reversible BOOLEAN,
    undo_commands JSON,
    
    executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id) ON DELETE CASCADE
);

-- ============================================================================
-- TRAINING DATASETS - VERSIONED SNAPSHOTS
-- ============================================================================

CREATE TABLE ml_datasets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    
    dataset_name TEXT NOT NULL,
    description TEXT,
    
    -- Date range
    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,
    
    -- Data splits
    train_operation_ids JSON NOT NULL,
    val_operation_ids JSON NOT NULL,
    test_operation_ids JSON NOT NULL,
    
    -- Dataset statistics
    total_operations INTEGER NOT NULL,
    labeled_operations INTEGER NOT NULL,
    label_quality_score REAL,
    
    -- Class distribution
    destination_distribution JSON,
    consumer_distribution JSON,
    semantics_distribution JSON,
    
    -- Quality metrics
    classification_accuracy REAL,
    inter_rater_reliability REAL,       -- If multiple feedback sources
    
    -- Model trained on this dataset
    model_version TEXT,
    model_performance JSON,
    
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================================
-- INDEXES FOR ML QUERIES
-- ============================================================================

-- Fast feature retrieval
CREATE INDEX idx_ml_features_request_hash ON ml_features((json_extract(features_json, '$.request_hash')));

-- Fast feedback queries
CREATE INDEX idx_user_feedback_rating ON user_feedback(rating) WHERE rating IS NOT NULL;
CREATE INDEX idx_user_feedback_corrected ON user_feedback(user_corrected_classification) WHERE user_corrected_classification IS NOT NULL;

-- Fast learning metric queries
CREATE INDEX idx_rlhf_metrics_improvement ON rlhf_learning_metrics(improvement);

-- ============================================================================
-- VIEWS FOR TRAINING DATA
-- ============================================================================

CREATE VIEW training_data AS
SELECT 
    ao.block_id,
    ao.user_request,
    ao.user_id,
    ao.destination_type AS system_destination,
    ao.consumer_type AS system_consumer,
    ao.execution_semantics AS system_semantics,
    ao.classification_confidence,
    
    mlf.request_embedding,
    mlf.features_json,
    mlf.token_count,
    mlf.verb_count,
    mlf.mentions_code,
    mlf.system_context,
    mlf.user_context,
    
    uf.approved,
    uf.user_corrected_classification,
    uf.rating,
    uf.rating_dimensions,
    uf.time_to_decision_ms,
    uf.retried,
    uf.modified,
    uf.operation_persisted,
    
    CASE 
        WHEN uf.approved = 1 THEN ao.destination_type
        WHEN uf.user_corrected_classification IS NOT NULL THEN json_extract(uf.user_corrected_classification, '$.destination_type')
        ELSE NULL
    END AS true_destination,
    
    CASE 
        WHEN uf.approved = 1 THEN ao.consumer_type
        WHEN uf.user_corrected_classification IS NOT NULL THEN json_extract(uf.user_corrected_classification, '$.consumer_type')
        ELSE NULL
    END AS true_consumer,
    
    CASE 
        WHEN uf.approved = 1 THEN ao.execution_semantics
        WHEN uf.user_corrected_classification IS NOT NULL THEN json_extract(uf.user_corrected_classification, '$.execution_semantics')
        ELSE NULL
    END AS true_semantics,
    
    ao.created_at,
    uf.created_at AS feedback_at

FROM atomic_operations ao
JOIN ml_features mlf ON ao.block_id = mlf.operation_block_id
LEFT JOIN user_feedback uf ON ao.block_id = uf.operation_block_id
WHERE uf.feedback_type IN ('correction', 'approval')
  AND (uf.approved = 1 OR uf.user_corrected_classification IS NOT NULL);

-- ============================================================================
-- TRIGGERS FOR AUTOMATIC METRIC COMPUTATION
-- ============================================================================

CREATE TRIGGER update_operation_timestamp
AFTER UPDATE ON atomic_operations
BEGIN
    UPDATE atomic_operations 
    SET updated_at = CURRENT_TIMESTAMP 
    WHERE block_id = NEW.block_id;
END;

-- ============================================================================
-- INITIALIZATION
-- ============================================================================

-- Insert system user for automated operations
INSERT OR IGNORE INTO blocks (id, type, parent_id, position) 
VALUES ('system-root', 'system', NULL, 0);
```

**Execution:**
```bash
# Create migration
sqlite3 talking_rock.db < src/database/schema_v3.sql

# Verify tables created
sqlite3 talking_rock.db ".tables"

# Should see: atomic_operations, ml_features, user_feedback, 
#             rlhf_learning_metrics, feedback_quality_metrics, etc.
```

**Acceptance Criteria:**
- [ ] All tables created without errors
- [ ] Foreign key constraints enabled
- [ ] Indexes created (verify with `.indexes`)
- [ ] Views created (verify with `.schema training_data`)
- [ ] Can insert test operation and retrieve it

---

### Step 0.2: Feature Extraction Library

**Task:** Build feature extraction pipeline that runs at classification time.

**File:** `src/ml/feature_extraction.py`

```python
"""
Feature extraction for atomic operations.
Runs locally, no API calls.
"""

import re
import json
import numpy as np
import nltk
from sentence_transformers import SentenceTransformer
from typing import Dict, List, Any
import hashlib

# Download NLTK data once
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt')
    nltk.download('averaged_perceptron_tagger')

class FeatureExtractor:
    """
    Extract ML features from user requests.
    """
    
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2'):
        """
        Initialize with local sentence transformer.
        Model is 22MB, runs on CPU.
        """
        self.embedder = SentenceTransformer(model_name)
        self.embedder.eval()  # Inference mode
    
    def extract_all_features(self, request: str, context: Dict = None) -> Dict[str, Any]:
        """
        Extract complete feature set for operation.
        
        Args:
            request: User's text request
            context: Optional system/user context
        
        Returns:
            Dictionary of all features
        """
        
        # Tokenization
        tokens = nltk.word_tokenize(request.lower())
        pos_tags = nltk.pos_tag(tokens)
        
        # Lexical features
        lexical = self._extract_lexical_features(request, tokens, pos_tags)
        
        # Semantic features (embeddings)
        semantic = self._extract_semantic_features(request, tokens, pos_tags)
        
        # Syntactic features
        syntactic = self._extract_syntactic_features(request, tokens, pos_tags)
        
        # Domain features
        domain = self._extract_domain_features(request, tokens)
        
        # Context features
        context_features = self._extract_context_features(context or {})
        
        return {
            'lexical': lexical,
            'semantic': semantic,
            'syntactic': syntactic,
            'domain': domain,
            'context': context_features,
            'request_hash': self._hash_request(request)
        }
    
    def _extract_lexical_features(self, request: str, tokens: List[str], pos_tags: List) -> Dict:
        """Extract token-level features."""
        
        verbs = [token for token, tag in pos_tags if tag.startswith('VB')]
        nouns = [token for token, tag in pos_tags if tag.startswith('NN')]
        
        # File extension detection
        file_ext_match = re.search(r'\.([a-zA-Z0-9]+)\b', request)
        has_extension = file_ext_match is not None
        extension_type = file_ext_match.group(1).lower() if has_extension else None
        
        return {
            'token_count': len(tokens),
            'char_count': len(request),
            'verb_count': len(verbs),
            'noun_count': len(nouns),
            'verbs': verbs,
            'nouns': nouns,
            'has_file_extension': has_extension,
            'file_extension_type': extension_type,
            'avg_word_length': np.mean([len(t) for t in tokens]) if tokens else 0
        }
    
    def _extract_semantic_features(self, request: str, tokens: List[str], pos_tags: List) -> Dict:
        """Extract embeddings for semantic similarity."""
        
        # Full request embedding
        request_emb = self.embedder.encode(request, convert_to_numpy=True)
        
        # Verb embeddings (for action classification)
        verbs = [token for token, tag in pos_tags if tag.startswith('VB')]
        verb_embs = [self.embedder.encode(v, convert_to_numpy=True) for v in verbs] if verbs else []
        
        # Object embeddings (for destination classification)
        nouns = [token for token, tag in pos_tags if tag.startswith('NN')]
        object_embs = [self.embedder.encode(n, convert_to_numpy=True) for n in nouns] if nouns else []
        
        return {
            'request_embedding': request_emb,  # ndarray, will be stored as BLOB
            'verb_embeddings': np.array(verb_embs) if verb_embs else None,
            'object_embeddings': np.array(object_embs) if object_embs else None,
            'verb_tokens': verbs,
            'object_tokens': nouns
        }
    
    def _extract_syntactic_features(self, request: str, tokens: List[str], pos_tags: List) -> Dict:
        """Extract syntax-level features."""
        
        return {
            'has_imperative_verb': any(tag == 'VB' for _, tag in pos_tags),
            'has_interrogative': request.strip().endswith('?'),
            'has_conditional': any(word in tokens for word in ['if', 'when', 'should', 'would']),
            'has_negation': any(word in tokens for word in ['not', 'no', "don't", "won't", "can't"]),
            'sentence_count': len(re.split(r'[.!?]', request))
        }
    
    def _extract_domain_features(self, request: str, tokens: List[str]) -> Dict:
        """Extract domain-specific indicators."""
        
        # Code-related patterns
        code_patterns = {
            'python': r'\.(py|pyx|pyd)\b',
            'javascript': r'\.(js|jsx|ts|tsx)\b',
            'java': r'\.(java|class|jar)\b',
            'cpp': r'\.(cpp|cc|cxx|h|hpp)\b',
            'rust': r'\.(rs)\b',
            'shell': r'\.(sh|bash|zsh)\b'
        }
        
        detected_languages = [lang for lang, pattern in code_patterns.items() 
                             if re.search(pattern, request, re.IGNORECASE)]
        
        # System resource mentions
        system_resources = ['memory', 'cpu', 'disk', 'network', 'process', 'service', 'port']
        mentions_system = any(res in tokens for res in system_resources)
        
        # File operation verbs
        file_operations = ['create', 'write', 'read', 'delete', 'modify', 'edit', 'update', 'save']
        has_file_operation = any(op in tokens for op in file_operations)
        
        # Immediate action verbs
        immediate_verbs = ['check', 'show', 'list', 'get', 'display', 'print', 'find']
        has_immediate_verb = any(verb in tokens for verb in immediate_verbs)
        
        return {
            'mentions_code': len(detected_languages) > 0,
            'detected_languages': detected_languages,
            'mentions_system_resource': mentions_system,
            'has_file_operation': has_file_operation,
            'has_immediate_verb': has_immediate_verb,
            'mentions_testing': any(word in tokens for word in ['test', 'tests', 'testing', 'pytest', 'jest']),
            'mentions_git': any(word in tokens for word in ['git', 'commit', 'branch', 'merge', 'push', 'pull'])
        }
    
    def _extract_context_features(self, context: Dict) -> Dict:
        """Extract features from system/user context."""
        
        return {
            'time_of_day': context.get('time_of_day', 0),  # hour
            'day_of_week': context.get('day_of_week', 0),
            'recent_operation_count': context.get('recent_operation_count', 0),
            'recent_success_rate': context.get('recent_success_rate', 0.0),
            'user_skill_estimate': context.get('user_skill_estimate', 0.5)
        }
    
    def _hash_request(self, request: str) -> str:
        """Create hash of request for deduplication."""
        return hashlib.sha256(request.encode()).hexdigest()[:16]
    
    def features_to_db_format(self, features: Dict) -> tuple:
        """
        Convert features to database storage format.
        
        Returns:
            (features_json, request_embedding_blob, verb_embeddings_blob, object_embeddings_blob, scalars)
        """
        
        # Convert embeddings to bytes
        request_emb = features['semantic']['request_embedding'].astype(np.float32).tobytes()
        
        verb_emb = None
        if features['semantic']['verb_embeddings'] is not None:
            verb_emb = features['semantic']['verb_embeddings'].astype(np.float32).tobytes()
        
        obj_emb = None
        if features['semantic']['object_embeddings'] is not None:
            obj_emb = features['semantic']['object_embeddings'].astype(np.float32).tobytes()
        
        # Store all features as JSON (for flexibility during iteration)
        features_json = json.dumps({
            'lexical': {k: v for k, v in features['lexical'].items() if not isinstance(v, np.ndarray)},
            'syntactic': features['syntactic'],
            'domain': features['domain'],
            'context': features['context'],
            'request_hash': features['request_hash']
        })
        
        # Extract scalar features for fast querying
        scalars = {
            'token_count': features['lexical']['token_count'],
            'verb_count': features['lexical']['verb_count'],
            'noun_count': features['lexical']['noun_count'],
            'has_file_extension': features['lexical']['has_file_extension'],
            'file_extension_type': features['lexical']['file_extension_type'],
            'mentions_code': features['domain']['mentions_code'],
            'mentions_system_resource': features['domain']['mentions_system_resource'],
            'has_imperative_verb': features['syntactic']['has_imperative_verb'],
            'has_interrogative': features['syntactic']['has_interrogative']
        }
        
        return features_json, request_emb, verb_emb, obj_emb, scalars
```

**Execution:**
```bash
# Install dependencies
pip install sentence-transformers nltk numpy --break-system-packages

# Test feature extraction
python3 << EOF
from src.ml.feature_extraction import FeatureExtractor

extractor = FeatureExtractor()
features = extractor.extract_all_features("Check memory usage and optimize auth.py")

print(f"Token count: {features['lexical']['token_count']}")
print(f"Verbs: {features['lexical']['verbs']}")
print(f"Mentions code: {features['domain']['mentions_code']}")
print(f"Embedding shape: {features['semantic']['request_embedding'].shape}")
EOF
```

**Acceptance Criteria:**
- [ ] Feature extraction runs in <500ms on average request
- [ ] Embeddings are 384-dimensional float32 arrays
- [ ] All feature categories present (lexical, semantic, syntactic, domain, context)
- [ ] Can convert features to database format
- [ ] No errors on edge cases (empty string, very long string, special chars)

---

### Step 0.3: RLHF Feedback Collector

**Task:** Build system to capture multi-dimensional user feedback.

**File:** `src/rlhf/feedback_collector.py`

```python
"""
Rich RLHF feedback collection.
Captures explicit ratings, corrections, and behavioral signals.
"""

import time
import json
import uuid
from datetime import datetime, timedelta
from typing import Dict, Optional, List
import sqlite3

class FeedbackCollector:
    """
    Collect and store user feedback at multiple levels.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def collect_explicit_rating(
        self,
        operation_id: str,
        user_id: str,
        rating: int,
        dimensions: Dict[str, int] = None,
        comment: str = None
    ) -> str:
        """
        Collect explicit user rating (1-5 scale).
        
        Args:
            operation_id: Operation being rated
            user_id: User providing rating
            rating: Overall rating 1-5
            dimensions: Optional dimensional ratings {accuracy: 4, speed: 5, helpfulness: 3}
            comment: Optional text feedback
        
        Returns:
            Feedback ID
        """
        
        feedback_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_feedback (
                    id, operation_block_id, user_id, feedback_type,
                    rating, rating_dimensions, comment,
                    feedback_confidence
                ) VALUES (?, ?, ?, 'explicit_rating', ?, ?, ?, 1.0)
            """, (
                feedback_id,
                operation_id,
                user_id,
                rating,
                json.dumps(dimensions) if dimensions else None,
                comment
            ))
        
        return feedback_id
    
    def collect_correction(
        self,
        operation_id: str,
        user_id: str,
        system_classification: Dict[str, str],
        user_corrected_classification: Dict[str, str],
        reasoning: str = None
    ) -> str:
        """
        Collect user correction (system was wrong).
        
        This is the MOST valuable feedback for learning.
        
        Args:
            operation_id: Operation that was misclassified
            user_id: User providing correction
            system_classification: What system classified it as
            user_corrected_classification: What it should have been
            reasoning: Why user made this correction
        
        Returns:
            Feedback ID
        """
        
        feedback_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_feedback (
                    id, operation_block_id, user_id, feedback_type,
                    system_classification, user_corrected_classification,
                    correction_reasoning, approved, modified,
                    feedback_confidence
                ) VALUES (?, ?, ?, 'correction', ?, ?, ?, 0, 1, 0.9)
            """, (
                feedback_id,
                operation_id,
                user_id,
                json.dumps(system_classification),
                json.dumps(user_corrected_classification),
                reasoning
            ))
        
        return feedback_id
    
    def collect_approval(
        self,
        operation_id: str,
        user_id: str,
        approved: bool,
        time_to_decision_ms: int,
        modified: bool = False,
        modification_extent: float = 0.0,
        modification_details: Dict = None
    ) -> str:
        """
        Collect approval/rejection decision.
        
        Args:
            operation_id: Operation being approved/rejected
            user_id: User making decision
            approved: True if approved, False if rejected
            time_to_decision_ms: How long user took to decide
            modified: Whether user modified before approving
            modification_extent: 0.0-1.0, how much was changed
            modification_details: What was changed
        
        Returns:
            Feedback ID
        """
        
        feedback_id = str(uuid.uuid4())
        
        # Infer confidence from time to decision
        # Fast decisions = high confidence
        # Slow decisions = uncertainty
        if time_to_decision_ms < 2000:
            confidence = 0.9
        elif time_to_decision_ms < 5000:
            confidence = 0.7
        elif time_to_decision_ms < 10000:
            confidence = 0.5
        else:
            confidence = 0.3
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_feedback (
                    id, operation_block_id, user_id, feedback_type,
                    approved, modified, modification_extent, modification_details,
                    time_to_decision_ms, feedback_confidence
                ) VALUES (?, ?, ?, 'approval', ?, ?, ?, ?, ?, ?)
            """, (
                feedback_id,
                operation_id,
                user_id,
                approved,
                modified,
                modification_extent,
                json.dumps(modification_details) if modification_details else None,
                time_to_decision_ms,
                confidence
            ))
        
        return feedback_id
    
    def collect_behavioral_signals(
        self,
        operation_id: str,
        user_id: str,
        retried: bool = False,
        time_to_retry_ms: int = None,
        undid: bool = False,
        time_to_undo_ms: int = None,
        abandoned: bool = False
    ) -> str:
        """
        Collect implicit behavioral feedback.
        
        These signals are often MORE reliable than explicit ratings.
        
        Args:
            operation_id: Operation user interacted with
            user_id: User ID
            retried: Did user retry operation?
            time_to_retry_ms: How long until retry?
            undid: Did user undo operation?
            time_to_undo_ms: How long until undo?
            abandoned: Did user abandon operation mid-way?
        
        Returns:
            Feedback ID
        """
        
        feedback_id = str(uuid.uuid4())
        
        # If user retried or undid quickly, system was likely wrong
        # If waited long time, might have been user error
        confidence = 0.8
        if retried and time_to_retry_ms and time_to_retry_ms < 5000:
            confidence = 0.9
        if undid and time_to_undo_ms and time_to_undo_ms < 10000:
            confidence = 0.95
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_feedback (
                    id, operation_block_id, user_id, feedback_type,
                    retried, time_to_retry_ms,
                    undid, time_to_undo_ms,
                    abandoned,
                    feedback_confidence
                ) VALUES (?, ?, ?, 'behavioral', ?, ?, ?, ?, ?, ?)
            """, (
                feedback_id,
                operation_id,
                user_id,
                retried,
                time_to_retry_ms,
                undid,
                time_to_undo_ms,
                abandoned,
                confidence
            ))
        
        return feedback_id
    
    def collect_long_term_outcome(
        self,
        operation_id: str,
        user_id: str,
        operation_persisted: bool,
        days_persisted: int,
        reused_pattern: bool = False,
        referenced_later: bool = False
    ) -> str:
        """
        Collect long-term outcome signals (strongest feedback).
        
        If user kept the result and reused the pattern, system was RIGHT.
        If user reverted it days later, system was WRONG.
        
        Args:
            operation_id: Operation to evaluate
            user_id: User ID
            operation_persisted: Did operation stay in place?
            days_persisted: How many days before reversion (if any)
            reused_pattern: Did user reuse this pattern?
            referenced_later: Did user reference this work later?
        
        Returns:
            Feedback ID
        """
        
        feedback_id = str(uuid.uuid4())
        
        # Long-term persistence = very high confidence feedback
        confidence = 0.95 if operation_persisted else 0.9
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO user_feedback (
                    id, operation_block_id, user_id, feedback_type,
                    operation_persisted, days_persisted,
                    reused_pattern, referenced_later,
                    feedback_confidence
                ) VALUES (?, ?, ?, 'long_term', ?, ?, ?, ?, ?)
            """, (
                feedback_id,
                operation_id,
                user_id,
                operation_persisted,
                days_persisted,
                reused_pattern,
                referenced_later,
                confidence
            ))
        
        return feedback_id
    
    def get_aggregate_feedback(
        self,
        operation_id: str
    ) -> Dict[str, any]:
        """
        Aggregate all feedback for an operation.
        
        Returns:
            Combined feedback signal
        """
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    feedback_type,
                    rating,
                    approved,
                    retried,
                    undid,
                    operation_persisted,
                    feedback_confidence
                FROM user_feedback
                WHERE operation_block_id = ?
                ORDER BY created_at DESC
            """, (operation_id,))
            
            feedbacks = cursor.fetchall()
        
        if not feedbacks:
            return {'has_feedback': False}
        
        # Aggregate different feedback types
        ratings = [f[1] for f in feedbacks if f[1] is not None]
        approvals = [f[2] for f in feedbacks if f[2] is not None]
        retries = [f[3] for f in feedbacks if f[3]]
        undos = [f[4] for f in feedbacks if f[4]]
        persistence = [f[5] for f in feedbacks if f[5] is not None]
        confidences = [f[6] for f in feedbacks]
        
        return {
            'has_feedback': True,
            'avg_rating': sum(ratings) / len(ratings) if ratings else None,
            'approval_rate': sum(approvals) / len(approvals) if approvals else None,
            'retry_count': len(retries),
            'undo_count': len(undos),
            'persisted': persistence[0] if persistence else None,
            'avg_confidence': sum(confidences) / len(confidences),
            'feedback_count': len(feedbacks)
        }
```

**Execution:**
```bash
# Test feedback collection
python3 << EOF
from src.rlhf.feedback_collector import FeedbackCollector

collector = FeedbackCollector('talking_rock.db')

# Simulate user correcting classification
feedback_id = collector.collect_correction(
    operation_id='test-op-1',
    user_id='user-1',
    system_classification={'destination': 'file', 'consumer': 'human', 'semantics': 'read'},
    user_corrected_classification={'destination': 'process', 'consumer': 'machine', 'semantics': 'execute'},
    reasoning='This was checking memory, not reading a file'
)

print(f"Feedback collected: {feedback_id}")

# Get aggregate feedback
agg = collector.get_aggregate_feedback('test-op-1')
print(f"Aggregate: {agg}")
EOF
```

**Acceptance Criteria:**
- [ ] Can collect all 5 feedback types
- [ ] Feedback stored with confidence scores
- [ ] Can aggregate multiple feedback signals
- [ ] Time-based confidence inference works
- [ ] No data loss on edge cases

---

## Phase 1: Classification Pipeline (Week 2)

### Step 1.1: Atomic Operation Classifier

**Task:** Build classifier that uses ML features to classify operations.

**File:** `src/classification/atomic_classifier.py`

```python
"""
Atomic operation classifier.
Integrates rule-based logic with ML features for classification.
"""

import json
import sqlite3
import uuid
from typing import Dict, Tuple, Optional
from datetime import datetime

from src.ml.feature_extraction import FeatureExtractor

class AtomicOperationClassifier:
    """
    Classify user requests into atomic operations.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.feature_extractor = FeatureExtractor()
    
    def classify_request(
        self,
        user_request: str,
        user_id: str,
        context: Dict = None
    ) -> str:
        """
        Classify user request and store as atomic operation.
        
        Args:
            user_request: User's text request
            user_id: User ID
            context: Optional system/user context
        
        Returns:
            Operation block ID
        """
        
        # Step 1: Extract ML features
        features = self.feature_extractor.extract_all_features(user_request, context)
        
        # Step 2: Run classification logic (rule-based for now, ML later)
        classification = self._classify_with_rules(user_request, features)
        
        # Step 3: Create operation block
        operation_id = self._create_operation_block(
            user_request,
            user_id,
            classification,
            features
        )
        
        # Step 4: Store classification reasoning
        self._store_classification_reasoning(
            operation_id,
            classification,
            features
        )
        
        # Step 5: Store ML features
        self._store_ml_features(operation_id, features)
        
        return operation_id
    
    def _classify_with_rules(
        self,
        request: str,
        features: Dict
    ) -> Dict[str, any]:
        """
        Rule-based classification (will be replaced by ML model).
        
        Returns:
            Classification result with confidence
        """
        
        # Initialize classification
        destination = None
        consumer = None
        semantics = None
        confidence = 0.5
        reasoning = {}
        
        # Rule 1: Detect persistence requirement
        has_file_ext = features['lexical']['has_file_extension']
        has_file_op = features['domain']['has_file_operation']
        
        if has_file_ext or has_file_op:
            destination = 'file'
            confidence += 0.2
            reasoning['persistence'] = 'File extension or file operation detected'
        elif features['domain']['mentions_system_resource']:
            destination = 'process'
            confidence += 0.2
            reasoning['persistence'] = 'System resource mentioned'
        else:
            destination = 'stream'
            confidence += 0.1
            reasoning['persistence'] = 'No persistence indicators, defaulting to stream'
        
        # Rule 2: Detect consumer
        mentions_code = features['domain']['mentions_code']
        has_immediate_verb = features['domain']['has_immediate_verb']
        
        if has_immediate_verb and not mentions_code:
            consumer = 'human'
            confidence += 0.2
            reasoning['consumer'] = 'Immediate verb suggests human consumption'
        elif mentions_code:
            consumer = 'machine'
            confidence += 0.2
            reasoning['consumer'] = 'Code detected, likely machine execution'
        else:
            consumer = 'human'
            confidence += 0.1
            reasoning['consumer'] = 'Default to human consumption'
        
        # Rule 3: Detect semantics
        verbs = features['lexical']['verbs']
        execution_verbs = ['run', 'execute', 'start', 'launch', 'install', 'deploy']
        interpretation_verbs = ['analyze', 'check', 'test', 'validate', 'verify']
        read_verbs = ['show', 'list', 'get', 'display', 'print', 'find']
        
        if any(v in execution_verbs for v in verbs):
            semantics = 'execute'
            confidence += 0.2
            reasoning['semantics'] = 'Execution verb detected'
        elif any(v in interpretation_verbs for v in verbs):
            semantics = 'interpret'
            confidence += 0.2
            reasoning['semantics'] = 'Interpretation verb detected'
        elif any(v in read_verbs for v in verbs):
            semantics = 'read'
            confidence += 0.2
            reasoning['semantics'] = 'Read verb detected'
        else:
            semantics = 'interpret'
            confidence += 0.1
            reasoning['semantics'] = 'Default to interpret'
        
        # Normalize confidence to 0-1
        confidence = min(1.0, confidence)
        
        return {
            'destination': destination,
            'consumer': consumer,
            'semantics': semantics,
            'confidence': confidence,
            'reasoning': reasoning,
            'alternatives_considered': self._generate_alternatives(
                destination, consumer, semantics, confidence
            )
        }
    
    def _generate_alternatives(
        self,
        chosen_dest: str,
        chosen_cons: str,
        chosen_sem: str,
        chosen_confidence: float
    ) -> list:
        """
        Generate alternative classifications considered.
        Useful for ML training later.
        """
        
        alternatives = []
        
        # For each dimension, list alternatives with lower confidence
        for dest in ['stream', 'file', 'process']:
            if dest != chosen_dest:
                alternatives.append({
                    'destination': dest,
                    'consumer': chosen_cons,
                    'semantics': chosen_sem,
                    'confidence': chosen_confidence * 0.6,
                    'rejected_reason': f'Chose {chosen_dest} instead'
                })
        
        return alternatives
    
    def _create_operation_block(
        self,
        user_request: str,
        user_id: str,
        classification: Dict,
        features: Dict
    ) -> str:
        """
        Create operation block in database.
        """
        
        operation_id = str(uuid.uuid4())
        block_id = f"op-{operation_id}"
        
        with sqlite3.connect(self.db_path) as conn:
            # Create block
            conn.execute("""
                INSERT INTO blocks (id, type, parent_id, position)
                VALUES (?, 'atomic_operation', NULL, 0)
            """, (block_id,))
            
            # Create operation
            conn.execute("""
                INSERT INTO atomic_operations (
                    block_id, user_request, user_id,
                    destination_type, consumer_type, execution_semantics,
                    classification_confidence, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'classifying')
            """, (
                block_id,
                user_request,
                user_id,
                classification['destination'],
                classification['consumer'],
                classification['semantics'],
                classification['confidence']
            ))
        
        return block_id
    
    def _store_classification_reasoning(
        self,
        operation_id: str,
        classification: Dict,
        features: Dict
    ) -> None:
        """
        Store classification reasoning for transparency.
        """
        
        reasoning_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO classification_reasoning (
                    id, operation_block_id, pass_number,
                    persistence_indicators, execution_indicators,
                    immediacy_indicators, code_indicators,
                    persistence_required, persistence_reasoning,
                    execution_required, execution_reasoning,
                    immediate_execution, immediacy_reasoning,
                    code_detected, code_reasoning,
                    destination_type, consumer_type, execution_semantics,
                    confidence, alternatives_considered
                ) VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                reasoning_id,
                operation_id,
                json.dumps({}),  # Will fill with actual indicators
                json.dumps({}),
                json.dumps({}),
                json.dumps({}),
                classification['destination'] == 'file',
                classification['reasoning'].get('persistence', ''),
                classification['semantics'] == 'execute',
                classification['reasoning'].get('semantics', ''),
                classification['consumer'] == 'human',
                classification['reasoning'].get('consumer', ''),
                features['domain']['mentions_code'],
                classification['reasoning'].get('code', ''),
                classification['destination'],
                classification['consumer'],
                classification['semantics'],
                classification['confidence'],
                json.dumps(classification['alternatives_considered'])
            ))
    
    def _store_ml_features(
        self,
        operation_id: str,
        features: Dict
    ) -> None:
        """
        Store ML features for training.
        """
        
        # Convert features to database format
        features_json, request_emb, verb_emb, obj_emb, scalars = \
            self.feature_extractor.features_to_db_format(features)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO ml_features (
                    operation_block_id,
                    features_json,
                    request_embedding,
                    verb_embeddings,
                    object_embeddings,
                    token_count,
                    verb_count,
                    noun_count,
                    has_file_extension,
                    file_extension_type,
                    mentions_code,
                    mentions_system_resource,
                    has_imperative_verb,
                    has_interrogative
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                operation_id,
                features_json,
                request_emb,
                verb_emb,
                obj_emb,
                scalars['token_count'],
                scalars['verb_count'],
                scalars['noun_count'],
                scalars['has_file_extension'],
                scalars['file_extension_type'],
                scalars['mentions_code'],
                scalars['mentions_system_resource'],
                scalars['has_imperative_verb'],
                scalars['has_interrogative']
            ))
```

**Execution:**
```bash
# Test classifier
python3 << EOF
from src.classification.atomic_classifier import AtomicOperationClassifier

classifier = AtomicOperationClassifier('talking_rock.db')

# Test classification
op_id = classifier.classify_request(
    user_request="Check memory usage and optimize auth.py",
    user_id="test-user",
    context={'time_of_day': 14, 'recent_success_rate': 0.85}
)

print(f"Operation classified: {op_id}")

# Verify in database
import sqlite3
conn = sqlite3.connect('talking_rock.db')
result = conn.execute("""
    SELECT destination_type, consumer_type, execution_semantics, classification_confidence
    FROM atomic_operations WHERE block_id = ?
""", (op_id,)).fetchone()

print(f"Classification: {result}")
EOF
```

**Acceptance Criteria:**
- [ ] Can classify request and create operation
- [ ] Features extracted and stored
- [ ] Classification reasoning stored
- [ ] Confidence score calculated
- [ ] Alternatives tracked
- [ ] Can retrieve operation from database

---

### Step 1.2: RLHF Learning Loop

**Task:** Build learning system that improves classification from user feedback.

**File:** `src/rlhf/learning_loop.py`

```python
"""
RLHF learning loop.
Continuously improves classification from user feedback.
"""

import json
import sqlite3
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import defaultdict

class RLHFLearningLoop:
    """
    Learn from user feedback to improve classification.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def compute_learning_metrics(
        self,
        user_id: str,
        window_days: int = 7
    ) -> Dict[str, float]:
        """
        Compute learning metrics for user over time window.
        
        Args:
            user_id: User to compute metrics for
            window_days: Days to look back
        
        Returns:
            Dictionary of metrics
        """
        
        window_start = datetime.now() - timedelta(days=window_days)
        
        with sqlite3.connect(self.db_path) as conn:
            # Get all operations with feedback in window
            cursor = conn.execute("""
                SELECT 
                    ao.destination_type,
                    ao.consumer_type,
                    ao.execution_semantics,
                    ao.classification_confidence,
                    uf.approved,
                    uf.user_corrected_classification,
                    uf.rating
                FROM atomic_operations ao
                JOIN user_feedback uf ON ao.block_id = uf.operation_block_id
                WHERE ao.user_id = ?
                  AND ao.created_at >= ?
                  AND uf.feedback_type IN ('approval', 'correction', 'explicit_rating')
            """, (user_id, window_start))
            
            operations = cursor.fetchall()
        
        if not operations:
            return {'error': 'No operations with feedback in window'}
        
        # Calculate metrics
        total = len(operations)
        
        # Classification accuracy (approved or no correction)
        correct = sum(1 for op in operations if op[4] == 1 or op[5] is None)
        classification_accuracy = correct / total
        
        # User satisfaction (average rating)
        ratings = [op[6] for op in operations if op[6] is not None]
        user_satisfaction = sum(ratings) / len(ratings) if ratings else None
        
        # Correction rate
        corrections = [op for op in operations if op[5] is not None]
        correction_rate = len(corrections) / total
        
        # Breakdown by category
        by_destination = self._breakdown_by_field(operations, 0, 4, 5)
        by_consumer = self._breakdown_by_field(operations, 1, 4, 5)
        by_semantics = self._breakdown_by_field(operations, 2, 4, 5)
        
        return {
            'classification_accuracy': classification_accuracy,
            'user_satisfaction': user_satisfaction,
            'correction_rate': correction_rate,
            'sample_size': total,
            'by_destination_type': by_destination,
            'by_consumer_type': by_consumer,
            'by_execution_semantics': by_semantics
        }
    
    def _breakdown_by_field(
        self,
        operations: List[tuple],
        field_idx: int,
        approved_idx: int,
        correction_idx: int
    ) -> Dict[str, float]:
        """
        Break down accuracy by classification field.
        """
        
        by_field = defaultdict(lambda: {'total': 0, 'correct': 0})
        
        for op in operations:
            field_value = op[field_idx]
            by_field[field_value]['total'] += 1
            if op[approved_idx] == 1 or op[correction_idx] is None:
                by_field[field_value]['correct'] += 1
        
        return {
            field: stats['correct'] / stats['total']
            for field, stats in by_field.items()
        }
    
    def store_learning_metrics(
        self,
        user_id: str,
        metrics: Dict[str, any],
        window_days: int
    ) -> str:
        """
        Store computed metrics in database.
        """
        
        metric_id = str(uuid.uuid4())
        
        window_end = datetime.now()
        window_start = window_end - timedelta(days=window_days)
        
        # Get previous window metrics for comparison
        previous_metrics = self.get_previous_window_metrics(
            user_id, 
            window_start,
            window_days
        )
        
        improvement = None
        if previous_metrics and 'classification_accuracy' in previous_metrics:
            improvement = metrics['classification_accuracy'] - previous_metrics['classification_accuracy']
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO rlhf_learning_metrics (
                    id, user_id, metric_type,
                    window_start, window_end, window_size_days,
                    metric_value, sample_size,
                    by_destination_type, by_consumer_type, by_execution_semantics,
                    previous_value, improvement
                ) VALUES (?, ?, 'classification_accuracy', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric_id,
                user_id,
                window_start,
                window_end,
                window_days,
                metrics['classification_accuracy'],
                metrics['sample_size'],
                json.dumps(metrics['by_destination_type']),
                json.dumps(metrics['by_consumer_type']),
                json.dumps(metrics['by_execution_semantics']),
                previous_metrics.get('classification_accuracy') if previous_metrics else None,
                improvement
            ))
        
        return metric_id
    
    def get_previous_window_metrics(
        self,
        user_id: str,
        current_window_start: datetime,
        window_days: int
    ) -> Dict:
        """
        Get metrics from previous time window for comparison.
        """
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    metric_value,
                    by_destination_type,
                    by_consumer_type,
                    by_execution_semantics
                FROM rlhf_learning_metrics
                WHERE user_id = ?
                  AND metric_type = 'classification_accuracy'
                  AND window_end < ?
                ORDER BY window_end DESC
                LIMIT 1
            """, (user_id, current_window_start))
            
            result = cursor.fetchone()
        
        if not result:
            return None
        
        return {
            'classification_accuracy': result[0],
            'by_destination_type': json.loads(result[1]) if result[1] else {},
            'by_consumer_type': json.loads(result[2]) if result[2] else {},
            'by_execution_semantics': json.loads(result[3]) if result[3] else {}
        }
    
    def compute_feedback_quality(
        self,
        user_id: str,
        window_days: int = 30
    ) -> Dict[str, float]:
        """
        Evaluate quality of user's feedback.
        
        High-quality feedback:
        - Consistent over time
        - Provides corrections with reasoning
        - Behavioral signals align with explicit ratings
        
        Returns:
            Quality metrics
        """
        
        window_start = datetime.now() - timedelta(days=window_days)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT 
                    feedback_type,
                    rating,
                    approved,
                    correction_reasoning,
                    retried,
                    undid,
                    created_at
                FROM user_feedback
                WHERE user_id = ?
                  AND created_at >= ?
                ORDER BY created_at
            """, (user_id, window_start))
            
            feedbacks = cursor.fetchall()
        
        if not feedbacks:
            return {'error': 'No feedback in window'}
        
        # Consistency: Do ratings correlate with approvals?
        ratings = []
        approvals = []
        for fb in feedbacks:
            if fb[1] is not None and fb[2] is not None:
                ratings.append(fb[1])
                approvals.append(1 if fb[2] else 0)
        
        consistency_score = np.corrcoef(ratings, approvals)[0, 1] if len(ratings) > 5 else 0.5
        consistency_score = (consistency_score + 1) / 2  # Normalize to 0-1
        
        # Informativeness: How many corrections with reasoning?
        corrections = [fb for fb in feedbacks if fb[0] == 'correction']
        corrections_with_reasoning = [fb for fb in corrections if fb[3]]
        informativeness_score = len(corrections_with_reasoning) / len(corrections) if corrections else 0.5
        
        # Engagement: What % of operations have explicit feedback?
        explicit_feedbacks = [fb for fb in feedbacks if fb[0] in ('explicit_rating', 'correction')]
        explicit_feedback_rate = len(explicit_feedbacks) / len(feedbacks)
        
        # Behavioral signals available
        behavioral_feedbacks = [fb for fb in feedbacks if fb[4] or fb[5]]  # retried or undid
        implicit_signals_available = len(behavioral_feedbacks) / len(feedbacks)
        
        return {
            'consistency_score': consistency_score,
            'consistency_sample_size': len(ratings),
            'informativeness_score': informativeness_score,
            'labeled_examples_count': len(corrections),
            'correction_details_provided': len(corrections_with_reasoning),
            'explicit_feedback_rate': explicit_feedback_rate,
            'implicit_signals_available': implicit_signals_available,
            'total_feedbacks': len(feedbacks)
        }
    
    def store_feedback_quality_metrics(
        self,
        user_id: str,
        quality_metrics: Dict,
        window_days: int
    ) -> str:
        """
        Store feedback quality metrics.
        """
        
        metric_id = str(uuid.uuid4())
        
        window_end = datetime.now()
        window_start = window_end - timedelta(days=window_days)
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO feedback_quality_metrics (
                    id, user_id,
                    consistency_score, consistency_sample_size,
                    informativeness_score, labeled_examples_count, correction_details_provided,
                    explicit_feedback_rate, implicit_signals_available,
                    window_start, window_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                metric_id,
                user_id,
                quality_metrics['consistency_score'],
                quality_metrics['consistency_sample_size'],
                quality_metrics['informativeness_score'],
                quality_metrics['labeled_examples_count'],
                quality_metrics['correction_details_provided'],
                quality_metrics['explicit_feedback_rate'],
                quality_metrics['implicit_signals_available'],
                window_start,
                window_end
            ))
        
        return metric_id
```

**Acceptance Criteria:**
- [ ] Can compute classification accuracy over time window
- [ ] Can detect improvement vs previous window
- [ ] Can evaluate feedback quality (consistency, informativeness)
- [ ] Metrics stored for trend analysis
- [ ] Works with sparse feedback (few examples)

---

---

## Phase 2: Verification System (Week 3)

### Overview: Five-Layer Verification

Every atomic operation must pass through verification layers before execution:
1. **Syntax** - Is the command/code structurally valid?
2. **Semantic** - Does it make logical sense in context?
3. **Behavioral** - Will it produce expected side effects?
4. **Safety** - Is it safe to execute?
5. **Intent** - Does it match what the user actually wanted?

### Step 3.1: Verification Framework

**Task:** Create multi-layer verification system that checks operations before execution.

**File:** `src/verification/verification_engine.py`

```python
import uuid
import sqlite3
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

@dataclass
class VerificationResult:
    layer: str
    passed: bool
    confidence: float
    issues_found: List[str]
    details: str
    execution_time_ms: int

class VerificationEngine:
    """Multi-layer verification for atomic operations."""
    
    def __init__(self, db_path: str):
        self.db_path = db_path
    
    def verify_operation(
        self,
        operation_id: str,
        operation_type: Tuple[str, str, str],  # (destination, consumer, semantics)
        content: str,
        context: Dict
    ) -> Dict[str, VerificationResult]:
        """
        Run all verification layers for an operation.
        
        Args:
            operation_id: Atomic operation ID
            operation_type: (destination_type, consumer_type, execution_semantics)
            content: The command/code/request to verify
            context: System context (files, permissions, state, etc.)
        
        Returns:
            Dict mapping layer name to VerificationResult
        """
        destination, consumer, semantics = operation_type
        
        results = {}
        
        # Layer 1: Syntax verification
        results['syntax'] = self._verify_syntax(content, destination, consumer)
        if not results['syntax'].passed:
            # Early exit if syntax invalid
            self._store_verification_results(operation_id, results)
            return results
        
        # Layer 2: Semantic verification
        results['semantic'] = self._verify_semantic(content, destination, consumer, context)
        
        # Layer 3: Behavioral verification (if appropriate)
        if semantics in ['interpret', 'execute']:
            results['behavioral'] = self._verify_behavioral(content, destination, consumer, context)
        
        # Layer 4: Safety verification
        results['safety'] = self._verify_safety(content, destination, consumer, semantics, context)
        
        # Layer 5: Intent verification (requires ML features)
        results['intent'] = self._verify_intent(operation_id, content, context)
        
        # Store all results
        self._store_verification_results(operation_id, results)
        
        return results
    
    def _verify_syntax(
        self,
        content: str,
        destination: str,
        consumer: str
    ) -> VerificationResult:
        """
        Layer 1: Syntax verification.
        
        Checks:
        - Shell: Valid bash/sh syntax
        - Python: Valid Python syntax
        - File: Valid file path
        """
        start_time = datetime.now()
        issues = []
        
        # Detect type and verify
        if destination == 'process' or consumer == 'machine':
            # Try shell syntax
            if self._looks_like_shell(content):
                shell_valid, shell_issues = self._verify_shell_syntax(content)
                if not shell_valid:
                    issues.extend(shell_issues)
            
            # Try Python syntax
            if self._looks_like_python(content):
                python_valid, python_issues = self._verify_python_syntax(content)
                if not python_valid:
                    issues.extend(python_issues)
        
        elif destination == 'file':
            # Verify file path
            path_valid, path_issues = self._verify_file_path(content)
            if not path_valid:
                issues.extend(path_issues)
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return VerificationResult(
            layer='syntax',
            passed=len(issues) == 0,
            confidence=1.0 if len(issues) == 0 else 0.0,
            issues_found=issues,
            details=f"Syntax check: {len(issues)} issues found" if issues else "Syntax valid",
            execution_time_ms=execution_time
        )
    
    def _verify_shell_syntax(self, content: str) -> Tuple[bool, List[str]]:
        """Verify shell command syntax using bash -n."""
        import subprocess
        
        try:
            result = subprocess.run(
                ['bash', '-n'],
                input=content,
                capture_output=True,
                text=True,
                timeout=1
            )
            
            if result.returncode != 0:
                return False, [f"Shell syntax error: {result.stderr}"]
            return True, []
        
        except subprocess.TimeoutExpired:
            return False, ["Shell syntax check timed out"]
        except Exception as e:
            return False, [f"Shell syntax check failed: {str(e)}"]
    
    def _verify_python_syntax(self, content: str) -> Tuple[bool, List[str]]:
        """Verify Python syntax using ast.parse."""
        import ast
        
        try:
            ast.parse(content)
            return True, []
        except SyntaxError as e:
            return False, [f"Python syntax error at line {e.lineno}: {e.msg}"]
        except Exception as e:
            return False, [f"Python syntax check failed: {str(e)}"]
    
    def _verify_file_path(self, path: str) -> Tuple[bool, List[str]]:
        """Verify file path is valid (not necessarily exists, just valid format)."""
        import os
        
        issues = []
        
        # Check for null bytes
        if '\x00' in path:
            issues.append("File path contains null bytes")
        
        # Check length (most systems)
        if len(path) > 4096:
            issues.append("File path too long (>4096 chars)")
        
        # Check for invalid characters on current OS
        if os.name == 'nt':  # Windows
            invalid_chars = '<>:"|?*'
            if any(c in path for c in invalid_chars):
                issues.append(f"File path contains invalid characters: {invalid_chars}")
        
        return len(issues) == 0, issues
    
    def _verify_semantic(
        self,
        content: str,
        destination: str,
        consumer: str,
        context: Dict
    ) -> VerificationResult:
        """
        Layer 2: Semantic verification.
        
        Checks:
        - Does command reference existing files/processes?
        - Are arguments appropriate for the command?
        - Is context sufficient to execute?
        """
        start_time = datetime.now()
        issues = []
        
        # Check file references exist (if read operation)
        file_refs = self._extract_file_references(content)
        for file_ref in file_refs:
            if not self._file_exists_in_context(file_ref, context):
                issues.append(f"Referenced file not found: {file_ref}")
        
        # Check environment variables exist
        env_vars = self._extract_env_variables(content)
        for var in env_vars:
            if not self._env_var_exists_in_context(var, context):
                issues.append(f"Environment variable not set: {var}")
        
        # Check command exists in PATH (for shell commands)
        if destination == 'process':
            command = self._extract_primary_command(content)
            if command and not self._command_exists_in_context(command, context):
                issues.append(f"Command not found in PATH: {command}")
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Confidence based on how many checks we could perform
        checks_performed = len(file_refs) + len(env_vars) + (1 if destination == 'process' else 0)
        confidence = 1.0 if checks_performed > 0 else 0.5  # Lower if we couldn't check anything
        
        return VerificationResult(
            layer='semantic',
            passed=len(issues) == 0,
            confidence=confidence if len(issues) == 0 else 0.3,
            issues_found=issues,
            details=f"Semantic check: {len(issues)} issues, {checks_performed} checks performed",
            execution_time_ms=execution_time
        )
    
    def _verify_behavioral(
        self,
        content: str,
        destination: str,
        consumer: str,
        context: Dict
    ) -> VerificationResult:
        """
        Layer 3: Behavioral verification.
        
        For operations that modify state, predict side effects:
        - Files created/modified/deleted
        - Processes spawned
        - Network connections
        - System resource usage
        """
        start_time = datetime.now()
        issues = []
        predictions = []
        
        # Analyze destructive operations
        if self._is_destructive(content):
            predictions.append("DESTRUCTIVE: May delete/modify data")
            
            # Check if backup exists
            if not context.get('has_backup', False):
                issues.append("Destructive operation without backup")
        
        # Analyze resource usage
        resource_estimate = self._estimate_resource_usage(content)
        if resource_estimate['memory_mb'] > 1000:
            predictions.append(f"HIGH MEMORY: Estimated {resource_estimate['memory_mb']}MB")
        
        if resource_estimate['disk_mb'] > 1000:
            predictions.append(f"HIGH DISK: Estimated {resource_estimate['disk_mb']}MB")
        
        # Check for network operations
        if self._has_network_access(content):
            predictions.append("NETWORK: May access external resources")
            
            if not context.get('network_allowed', True):
                issues.append("Network operation but network not allowed")
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return VerificationResult(
            layer='behavioral',
            passed=len(issues) == 0,
            confidence=0.7,  # Behavioral prediction is inherently less certain
            issues_found=issues,
            details=f"Behavioral analysis: {', '.join(predictions) if predictions else 'No concerning behavior'}",
            execution_time_ms=execution_time
        )
    
    def _verify_safety(
        self,
        content: str,
        destination: str,
        consumer: str,
        semantics: str,
        context: Dict
    ) -> VerificationResult:
        """
        Layer 4: Safety verification.
        
        Checks:
        - No arbitrary code execution vulnerabilities
        - No privilege escalation attempts
        - Rate limiting not exceeded
        - Within safety bounds
        """
        start_time = datetime.now()
        issues = []
        risk_level = "low"
        
        # Check for sudo/privilege escalation
        if 'sudo' in content.lower() or 'su ' in content:
            issues.append("Privilege escalation detected (sudo/su)")
            risk_level = "critical"
        
        # Check for command injection patterns
        injection_patterns = ['; ', '| ', '`', '$(', '&&', '||']
        if any(pattern in content for pattern in injection_patterns):
            # Only flag if looks suspicious (not all pipes are bad)
            if not self._is_safe_pipe(content):
                issues.append("Potential command injection pattern")
                risk_level = "high"
        
        # Check rate limits
        user_id = context.get('user_id')
        if user_id and semantics == 'execute':
            recent_executions = self._count_recent_executions(user_id, minutes=5)
            if recent_executions > 10:
                issues.append(f"Rate limit exceeded: {recent_executions} executions in 5 minutes")
                risk_level = "high"
        
        # Check destructive patterns
        destructive_commands = ['rm -rf', 'dd if=', ':(){:|:&};:', 'mkfs', '>(', 'format']
        if any(cmd in content for cmd in destructive_commands):
            issues.append("Highly destructive command detected")
            risk_level = "critical"
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        return VerificationResult(
            layer='safety',
            passed=len(issues) == 0,
            confidence=0.9 if len(issues) == 0 else 0.1,
            issues_found=issues,
            details=f"Safety check: Risk level {risk_level}",
            execution_time_ms=execution_time
        )
    
    def _verify_intent(
        self,
        operation_id: str,
        content: str,
        context: Dict
    ) -> VerificationResult:
        """
        Layer 5: Intent verification.
        
        Uses ML features to check if operation matches user intent:
        - Loads ML features for this operation
        - Compares to similar past operations
        - Checks if classification confidence was high
        - Flags if intent seems misaligned
        """
        start_time = datetime.now()
        issues = []
        
        # Load operation's classification
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT classification_confidence, destination_type, consumer_type, execution_semantics
                FROM atomic_operations
                WHERE block_id = ?
            """, (operation_id,))
            
            row = cursor.fetchone()
            if not row:
                return VerificationResult(
                    layer='intent',
                    passed=False,
                    confidence=0.0,
                    issues_found=["Operation not found in database"],
                    details="Intent verification failed: operation not found",
                    execution_time_ms=0
                )
            
            classification_confidence, dest, cons, sem = row
        
        # If classification confidence was low, flag intent uncertainty
        if classification_confidence < 0.7:
            issues.append(f"Low classification confidence: {classification_confidence:.2f}")
        
        # Check for ambiguous requests (via ML features)
        # This would use the ML model in production, for now use heuristics
        if self._request_is_ambiguous(content):
            issues.append("Request is ambiguous, intent unclear")
        
        execution_time = int((datetime.now() - start_time).total_seconds() * 1000)
        
        # Intent verification confidence is based on classification confidence
        intent_confidence = classification_confidence if len(issues) == 0 else classification_confidence * 0.5
        
        return VerificationResult(
            layer='intent',
            passed=len(issues) == 0,
            confidence=intent_confidence,
            issues_found=issues,
            details=f"Intent check: Classification confidence {classification_confidence:.2f}",
            execution_time_ms=execution_time
        )
    
    def _store_verification_results(
        self,
        operation_id: str,
        results: Dict[str, VerificationResult]
    ):
        """Store verification results in database."""
        with sqlite3.connect(self.db_path) as conn:
            for layer_name, result in results.items():
                verification_id = str(uuid.uuid4())
                
                conn.execute("""
                    INSERT INTO operation_verification (
                        id, operation_block_id, verification_layer,
                        passed, confidence, issues_found, details, execution_time_ms,
                        timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    verification_id,
                    operation_id,
                    layer_name,
                    result.passed,
                    result.confidence,
                    '\n'.join(result.issues_found),
                    result.details,
                    result.execution_time_ms,
                    datetime.now()
                ))
    
    # Helper methods (stub implementations - expand as needed)
    
    def _looks_like_shell(self, content: str) -> bool:
        shell_keywords = ['echo', 'cd', 'ls', 'grep', 'awk', 'sed', 'cat', 'chmod', 'mkdir']
        return any(kw in content for kw in shell_keywords)
    
    def _looks_like_python(self, content: str) -> bool:
        python_keywords = ['def ', 'class ', 'import ', 'from ', 'print(', 'if __name__']
        return any(kw in content for kw in python_keywords)
    
    def _extract_file_references(self, content: str) -> List[str]:
        # Simple extraction - expand with regex
        import re
        # Match paths like /path/to/file or ./relative/path
        return re.findall(r'[\'"]?([/~.][\w/.-]+)[\'"]?', content)
    
    def _extract_env_variables(self, content: str) -> List[str]:
        import re
        return re.findall(r'\$([A-Z_][A-Z0-9_]*)', content)
    
    def _extract_primary_command(self, content: str) -> Optional[str]:
        # Extract first word (the command)
        parts = content.strip().split()
        return parts[0] if parts else None
    
    def _file_exists_in_context(self, file_ref: str, context: Dict) -> bool:
        import os
        return os.path.exists(file_ref)
    
    def _env_var_exists_in_context(self, var: str, context: Dict) -> bool:
        import os
        return var in os.environ
    
    def _command_exists_in_context(self, command: str, context: Dict) -> bool:
        import shutil
        return shutil.which(command) is not None
    
    def _is_destructive(self, content: str) -> bool:
        destructive_verbs = ['rm', 'delete', 'drop', 'truncate', 'destroy', 'kill']
        return any(verb in content.lower() for verb in destructive_verbs)
    
    def _estimate_resource_usage(self, content: str) -> Dict[str, int]:
        # Stub - would use heuristics or ML
        return {'memory_mb': 100, 'disk_mb': 10}
    
    def _has_network_access(self, content: str) -> bool:
        network_keywords = ['curl', 'wget', 'http://', 'https://', 'ftp://', 'ssh', 'scp']
        return any(kw in content.lower() for kw in network_keywords)
    
    def _is_safe_pipe(self, content: str) -> bool:
        # Check if pipe is part of normal command chaining
        # vs potential injection
        # Stub - would need more sophisticated analysis
        return '|' in content and not ('; ' in content or '&&' in content)
    
    def _count_recent_executions(self, user_id: str, minutes: int) -> int:
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(minutes=minutes)
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*) FROM atomic_operations
                WHERE user_id = ? AND created_at > ? AND execution_semantics = 'execute'
            """, (user_id, cutoff))
            
            return cursor.fetchone()[0]
    
    def _request_is_ambiguous(self, content: str) -> bool:
        # Check for vague language
        ambiguous_words = ['thing', 'stuff', 'something', 'it', 'that', 'this']
        word_count = len(content.split())
        ambiguous_count = sum(1 for word in ambiguous_words if word in content.lower())
        
        # If >20% of words are ambiguous, flag it
        return word_count > 0 and (ambiguous_count / word_count) > 0.2
```

**Acceptance Criteria:**
- [ ] All 5 verification layers implemented
- [ ] Each layer returns structured VerificationResult
- [ ] Results stored in database with timing
- [ ] Syntax layer catches invalid shell/Python
- [ ] Semantic layer checks file/command existence
- [ ] Behavioral layer predicts side effects
- [ ] Safety layer blocks dangerous operations
- [ ] Intent layer uses classification confidence
- [ ] Tests for each layer pass

---

## Phase 3: Execution System (Week 4)

### Overview: Safe, Auditable Execution

Operations that pass verification can be executed. The execution system:
- Captures full state before/after
- Provides undo capability
- Limits resource usage
- Logs everything for RLHF

### Step 4.1: Execution Engine

**Task:** Create execution engine that runs verified operations safely.

**File:** `src/execution/execution_engine.py`

```python
import uuid
import sqlite3
import subprocess
import os
import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import shutil

@dataclass
class ExecutionResult:
    operation_id: str
    executor: str
    success: bool
    exit_code: Optional[int]
    stdout: str
    stderr: str
    duration_ms: int
    files_affected: List[str]
    processes_spawned: List[int]
    state_before: Dict[str, Any]
    state_after: Dict[str, Any]
    reversible: bool
    undo_commands: List[str]

class ExecutionEngine:
    """Execute verified atomic operations safely."""
    
    def __init__(self, db_path: str, backup_dir: str = '/tmp/talking_rock_backups'):
        self.db_path = db_path
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
    
    def execute_operation(
        self,
        operation_id: str,
        verification_results: Dict,
        user_id: str,
        dry_run: bool = False
    ) -> ExecutionResult:
        """
        Execute a verified atomic operation.
        
        Args:
            operation_id: Atomic operation block ID
            verification_results: Results from VerificationEngine
            user_id: User executing the operation
            dry_run: If True, simulate execution without changes
        
        Returns:
            ExecutionResult with execution details
        """
        # Check all verifications passed
        if not all(result.passed for result in verification_results.values()):
            failed_layers = [k for k, v in verification_results.items() if not v.passed]
            return ExecutionResult(
                operation_id=operation_id,
                executor='none',
                success=False,
                exit_code=-1,
                stdout='',
                stderr=f"Verification failed: {', '.join(failed_layers)}",
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
        
        # Load operation details
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT user_request, destination_type, consumer_type, execution_semantics
                FROM atomic_operations
                WHERE block_id = ?
            """, (operation_id,))
            
            row = cursor.fetchone()
            if not row:
                raise ValueError(f"Operation {operation_id} not found")
            
            request, destination, consumer, semantics = row
        
        # Capture state before execution
        state_before = self._capture_state(request, destination)
        
        # Choose executor based on operation type
        if destination == 'process' and consumer == 'machine':
            result = self._execute_shell(operation_id, request, dry_run)
        elif destination == 'file' and semantics == 'execute':
            result = self._execute_file_operation(operation_id, request, dry_run)
        elif consumer == 'machine' and semantics == 'interpret':
            result = self._execute_python(operation_id, request, dry_run)
        else:
            # For human consumer or read operations, no actual execution
            result = ExecutionResult(
                operation_id=operation_id,
                executor='none',
                success=True,
                exit_code=0,
                stdout=request,  # Just return the content
                stderr='',
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before=state_before,
                state_after=state_before,  # No change
                reversible=True,
                undo_commands=[]
            )
        
        # Capture state after execution
        result.state_before = state_before
        result.state_after = self._capture_state(request, destination)
        
        # Store execution results
        self._store_execution_result(result)
        
        return result
    
    def _execute_shell(
        self,
        operation_id: str,
        command: str,
        dry_run: bool
    ) -> ExecutionResult:
        """Execute shell command."""
        start_time = time.time()
        files_affected = []
        processes_spawned = []
        undo_commands = []
        
        if dry_run:
            # Simulate execution
            return ExecutionResult(
                operation_id=operation_id,
                executor='shell_dry_run',
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would execute: {command}",
                stderr='',
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=True,
                undo_commands=[]
            )
        
        # Backup files that might be affected
        potential_files = self._extract_file_targets(command)
        for filepath in potential_files:
            if os.path.exists(filepath):
                backup_path = self._backup_file(filepath)
                if backup_path:
                    undo_commands.append(f"cp {backup_path} {filepath}")
                    files_affected.append(filepath)
        
        # Execute with timeout and resource limits
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,  # 30 second timeout
                cwd=os.getcwd()
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                operation_id=operation_id,
                executor='shell',
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                files_affected=files_affected,
                processes_spawned=processes_spawned,
                state_before={},
                state_after={},
                reversible=len(undo_commands) > 0,
                undo_commands=undo_commands
            )
        
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                operation_id=operation_id,
                executor='shell',
                success=False,
                exit_code=-1,
                stdout='',
                stderr='Command timed out after 30 seconds',
                duration_ms=duration_ms,
                files_affected=files_affected,
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=len(undo_commands) > 0,
                undo_commands=undo_commands
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                operation_id=operation_id,
                executor='shell',
                success=False,
                exit_code=-1,
                stdout='',
                stderr=f'Execution error: {str(e)}',
                duration_ms=duration_ms,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
    
    def _execute_file_operation(
        self,
        operation_id: str,
        request: str,
        dry_run: bool
    ) -> ExecutionResult:
        """Execute file operation (create, modify, delete)."""
        start_time = time.time()
        
        # Parse file operation from request
        # Format: "operation filepath [content]"
        # e.g., "create /tmp/test.txt Hello World"
        parts = request.split(None, 2)
        
        if len(parts) < 2:
            return ExecutionResult(
                operation_id=operation_id,
                executor='file',
                success=False,
                exit_code=-1,
                stdout='',
                stderr='Invalid file operation format',
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
        
        operation = parts[0].lower()
        filepath = parts[1]
        content = parts[2] if len(parts) > 2 else ''
        
        if dry_run:
            return ExecutionResult(
                operation_id=operation_id,
                executor='file_dry_run',
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would {operation} file: {filepath}",
                stderr='',
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=True,
                undo_commands=[]
            )
        
        undo_commands = []
        
        try:
            if operation == 'create' or operation == 'write':
                # Backup if exists
                if os.path.exists(filepath):
                    backup_path = self._backup_file(filepath)
                    if backup_path:
                        undo_commands.append(f"cp {backup_path} {filepath}")
                else:
                    undo_commands.append(f"rm {filepath}")
                
                # Write file
                with open(filepath, 'w') as f:
                    f.write(content)
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                return ExecutionResult(
                    operation_id=operation_id,
                    executor='file',
                    success=True,
                    exit_code=0,
                    stdout=f"File created: {filepath}",
                    stderr='',
                    duration_ms=duration_ms,
                    files_affected=[filepath],
                    processes_spawned=[],
                    state_before={},
                    state_after={},
                    reversible=True,
                    undo_commands=undo_commands
                )
            
            elif operation == 'delete' or operation == 'remove':
                # Backup before delete
                if os.path.exists(filepath):
                    backup_path = self._backup_file(filepath)
                    if backup_path:
                        undo_commands.append(f"cp {backup_path} {filepath}")
                    
                    os.remove(filepath)
                    
                    duration_ms = int((time.time() - start_time) * 1000)
                    
                    return ExecutionResult(
                        operation_id=operation_id,
                        executor='file',
                        success=True,
                        exit_code=0,
                        stdout=f"File deleted: {filepath}",
                        stderr='',
                        duration_ms=duration_ms,
                        files_affected=[filepath],
                        processes_spawned=[],
                        state_before={},
                        state_after={},
                        reversible=True,
                        undo_commands=undo_commands
                    )
                else:
                    return ExecutionResult(
                        operation_id=operation_id,
                        executor='file',
                        success=False,
                        exit_code=-1,
                        stdout='',
                        stderr=f"File not found: {filepath}",
                        duration_ms=0,
                        files_affected=[],
                        processes_spawned=[],
                        state_before={},
                        state_after={},
                        reversible=False,
                        undo_commands=[]
                    )
            
            else:
                return ExecutionResult(
                    operation_id=operation_id,
                    executor='file',
                    success=False,
                    exit_code=-1,
                    stdout='',
                    stderr=f"Unknown file operation: {operation}",
                    duration_ms=0,
                    files_affected=[],
                    processes_spawned=[],
                    state_before={},
                    state_after={},
                    reversible=False,
                    undo_commands=[]
                )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                operation_id=operation_id,
                executor='file',
                success=False,
                exit_code=-1,
                stdout='',
                stderr=f'File operation error: {str(e)}',
                duration_ms=duration_ms,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
    
    def _execute_python(
        self,
        operation_id: str,
        code: str,
        dry_run: bool
    ) -> ExecutionResult:
        """Execute Python code (limited to safe subset)."""
        start_time = time.time()
        
        if dry_run:
            return ExecutionResult(
                operation_id=operation_id,
                executor='python_dry_run',
                success=True,
                exit_code=0,
                stdout=f"[DRY RUN] Would execute Python:\n{code[:100]}...",
                stderr='',
                duration_ms=0,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=True,
                undo_commands=[]
            )
        
        # Write code to temp file and execute
        import tempfile
        
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
                f.write(code)
                temp_path = f.name
            
            result = subprocess.run(
                ['python3', temp_path],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            os.unlink(temp_path)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            return ExecutionResult(
                operation_id=operation_id,
                executor='python',
                success=result.returncode == 0,
                exit_code=result.returncode,
                stdout=result.stdout,
                stderr=result.stderr,
                duration_ms=duration_ms,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,  # Python execution not easily reversible
                undo_commands=[]
            )
        
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                operation_id=operation_id,
                executor='python',
                success=False,
                exit_code=-1,
                stdout='',
                stderr='Python execution timed out after 30 seconds',
                duration_ms=duration_ms,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
        
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                operation_id=operation_id,
                executor='python',
                success=False,
                exit_code=-1,
                stdout='',
                stderr=f'Python execution error: {str(e)}',
                duration_ms=duration_ms,
                files_affected=[],
                processes_spawned=[],
                state_before={},
                state_after={},
                reversible=False,
                undo_commands=[]
            )
    
    def undo_operation(self, operation_id: str) -> bool:
        """Undo an executed operation if possible."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT reversible, undo_commands
                FROM operation_execution
                WHERE operation_block_id = ?
                ORDER BY timestamp DESC
                LIMIT 1
            """, (operation_id,))
            
            row = cursor.fetchone()
            if not row:
                return False
            
            reversible, undo_commands_str = row
            
            if not reversible or not undo_commands_str:
                return False
            
            undo_commands = undo_commands_str.split('\n')
            
            # Execute undo commands
            for cmd in undo_commands:
                try:
                    subprocess.run(cmd, shell=True, check=True, timeout=10)
                except Exception as e:
                    print(f"Undo failed: {e}")
                    return False
            
            return True
    
    def _capture_state(self, request: str, destination: str) -> Dict[str, Any]:
        """Capture system state before/after execution."""
        state = {
            'timestamp': datetime.now().isoformat(),
            'cwd': os.getcwd()
        }
        
        if destination == 'file':
            # Capture file states
            files = self._extract_file_targets(request)
            state['files'] = {}
            for filepath in files:
                if os.path.exists(filepath):
                    stat = os.stat(filepath)
                    state['files'][filepath] = {
                        'exists': True,
                        'size': stat.st_size,
                        'mtime': stat.st_mtime
                    }
                else:
                    state['files'][filepath] = {'exists': False}
        
        elif destination == 'process':
            # Capture process list
            try:
                result = subprocess.run(['ps', 'aux'], capture_output=True, text=True, timeout=1)
                state['processes'] = len(result.stdout.split('\n'))
            except:
                state['processes'] = 0
        
        return state
    
    def _backup_file(self, filepath: str) -> Optional[str]:
        """Create backup of file before modification."""
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_name = f"{os.path.basename(filepath)}.{timestamp}.backup"
            backup_path = os.path.join(self.backup_dir, backup_name)
            
            shutil.copy2(filepath, backup_path)
            return backup_path
        except Exception as e:
            print(f"Backup failed: {e}")
            return None
    
    def _extract_file_targets(self, text: str) -> List[str]:
        """Extract file paths that might be affected."""
        import re
        # Match paths
        paths = re.findall(r'[\'"]?([/~.][\w/.-]+)[\'"]?', text)
        return [p for p in paths if '/' in p or p.startswith('.') or p.startswith('~')]
    
    def _store_execution_result(self, result: ExecutionResult):
        """Store execution results in database."""
        execution_id = str(uuid.uuid4())
        
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT INTO operation_execution (
                    id, operation_block_id, executor, success, exit_code,
                    stdout, stderr, duration_ms,
                    files_affected, processes_spawned,
                    state_before, state_after,
                    reversible, undo_commands,
                    timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                execution_id,
                result.operation_id,
                result.executor,
                result.success,
                result.exit_code,
                result.stdout,
                result.stderr,
                result.duration_ms,
                json.dumps(result.files_affected),
                json.dumps(result.processes_spawned),
                json.dumps(result.state_before),
                json.dumps(result.state_after),
                result.reversible,
                '\n'.join(result.undo_commands),
                datetime.now()
            ))
```

**Acceptance Criteria:**
- [ ] Shell command execution with timeout
- [ ] File operations with automatic backup
- [ ] Python code execution in sandbox
- [ ] State capture before/after
- [ ] Undo capability for reversible operations
- [ ] All results logged to database
- [ ] Dry-run mode works
- [ ] Resource limits enforced
- [ ] Tests pass for all executors

---

## Phase 4: Agent Integration (Week 5)

### Overview: RIVA, ReOS, CAIRN as Atomic Operation Generators

The three agents (RIVA, ReOS, CAIRN) don't replace atomic operations—they **generate** them. Each agent:
1. Takes user request
2. Decomposes into atomic operations
3. Each atomic operation gets classified, verified, executed, learned from
4. Agent synthesizes results back to user

### Step 5.1: Agent Operation Generator Interface

**Task:** Create interface that agents use to generate atomic operations.

**File:** `src/agents/operation_generator.py`

```python
import sqlite3
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from src.classification.atomic_classifier import AtomicOperationClassifier
from src.verification.verification_engine import VerificationEngine
from src.execution.execution_engine import ExecutionEngine
from src.rlhf.feedback_collector import FeedbackCollector

@dataclass
class AtomicOperationRequest:
    """Single atomic operation request."""
    content: str
    expected_type: Optional[Tuple[str, str, str]] = None  # (destination, consumer, semantics)
    requires_approval: bool = True
    parent_task_id: Optional[str] = None

@dataclass
class OperationResult:
    """Result of atomic operation execution."""
    operation_id: str
    classification: Tuple[str, str, str]
    verification_passed: bool
    execution_result: Optional[Dict]
    requires_user_action: bool
    error_message: Optional[str] = None

class AtomicOperationGenerator:
    """
    Interface for agents (RIVA, ReOS, CAIRN) to generate atomic operations.
    
    Agents decompose complex tasks into atomic operations, which are then:
    1. Classified into 3×2×3 taxonomy
    2. Verified through 5 layers
    3. Executed if safe
    4. Learned from via RLHF
    """
    
    def __init__(
        self,
        db_path: str,
        classifier: AtomicOperationClassifier,
        verifier: VerificationEngine,
        executor: ExecutionEngine,
        feedback_collector: FeedbackCollector
    ):
        self.db_path = db_path
        self.classifier = classifier
        self.verifier = verifier
        self.executor = executor
        self.feedback_collector = feedback_collector
    
    def generate_operation(
        self,
        request: AtomicOperationRequest,
        user_id: str,
        context: Dict,
        auto_execute: bool = False
    ) -> OperationResult:
        """
        Generate and process a single atomic operation.
        
        Args:
            request: Atomic operation request
            user_id: User making the request
            context: System context
            auto_execute: If True, execute without user approval (if safe)
        
        Returns:
            OperationResult with execution status
        """
        # Step 1: Classify
        operation_id = self.classifier.classify_request(
            user_request=request.content,
            user_id=user_id,
            context=context
        )
        
        # Get classification
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT destination_type, consumer_type, execution_semantics, classification_confidence
                FROM atomic_operations
                WHERE block_id = ?
            """, (operation_id,))
            
            row = cursor.fetchone()
            if not row:
                return OperationResult(
                    operation_id=operation_id,
                    classification=('unknown', 'unknown', 'unknown'),
                    verification_passed=False,
                    execution_result=None,
                    requires_user_action=True,
                    error_message="Classification failed"
                )
            
            dest, cons, sem, confidence = row
            classification = (dest, cons, sem)
        
        # Check if classification matches expected (if provided)
        if request.expected_type and classification != request.expected_type:
            # Log mismatch for learning
            self.feedback_collector.collect_correction(
                operation_id=operation_id,
                user_id=user_id,
                system_classification={'destination': dest, 'consumer': cons, 'semantics': sem},
                user_corrected_classification={
                    'destination': request.expected_type[0],
                    'consumer': request.expected_type[1],
                    'semantics': request.expected_type[2]
                },
                reasoning=f"Agent expected {request.expected_type} but system classified as {classification}"
            )
        
        # Step 2: Verify
        verification_results = self.verifier.verify_operation(
            operation_id=operation_id,
            operation_type=classification,
            content=request.content,
            context=context
        )
        
        verification_passed = all(r.passed for r in verification_results.values())
        
        if not verification_passed:
            failed_layers = [k for k, v in verification_results.items() if not v.passed]
            return OperationResult(
                operation_id=operation_id,
                classification=classification,
                verification_passed=False,
                execution_result=None,
                requires_user_action=True,
                error_message=f"Verification failed: {', '.join(failed_layers)}"
            )
        
        # Step 3: Execute (if approved or auto_execute enabled)
        if auto_execute or not request.requires_approval:
            execution_result = self.executor.execute_operation(
                operation_id=operation_id,
                verification_results=verification_results,
                user_id=user_id,
                dry_run=False
            )
            
            # Collect behavioral feedback (immediate)
            self.feedback_collector.collect_behavioral_signals(
                operation_id=operation_id,
                user_id=user_id,
                retried=False,
                time_to_retry_ms=None,
                undid=False,
                time_to_undo_ms=None,
                abandoned=not execution_result.success
            )
            
            return OperationResult(
                operation_id=operation_id,
                classification=classification,
                verification_passed=True,
                execution_result={
                    'success': execution_result.success,
                    'stdout': execution_result.stdout,
                    'stderr': execution_result.stderr,
                    'duration_ms': execution_result.duration_ms,
                    'files_affected': execution_result.files_affected,
                    'reversible': execution_result.reversible
                },
                requires_user_action=not execution_result.success
            )
        else:
            # Requires user approval
            return OperationResult(
                operation_id=operation_id,
                classification=classification,
                verification_passed=True,
                execution_result=None,
                requires_user_action=True
            )
    
    def generate_batch(
        self,
        requests: List[AtomicOperationRequest],
        user_id: str,
        context: Dict,
        stop_on_error: bool = True
    ) -> List[OperationResult]:
        """
        Generate and process multiple atomic operations.
        
        Args:
            requests: List of atomic operation requests
            user_id: User making requests
            context: System context
            stop_on_error: If True, stop processing if any operation fails
        
        Returns:
            List of OperationResults
        """
        results = []
        
        for request in requests:
            result = self.generate_operation(
                request=request,
                user_id=user_id,
                context=context,
                auto_execute=False  # Batch operations require approval
            )
            
            results.append(result)
            
            if stop_on_error and (not result.verification_passed or result.error_message):
                break
        
        return results
```

### Step 5.2: RIVA Integration

**Task:** Integrate RIVA code generation as atomic operation generator.

**File:** `src/agents/riva_integration.py`

```python
from typing import List, Dict
from src.agents.operation_generator import AtomicOperationGenerator, AtomicOperationRequest, OperationResult

class RIVACodeGenerator:
    """
    RIVA generates atomic operations for code generation tasks.
    
    Example decomposition:
    User: "Add OAuth2 authentication"
    RIVA generates:
    1. Read current user model (file, machine, read)
    2. Interpret requirements (stream, human, interpret)
    3. Execute code generation (file, machine, execute)
    4. Execute tests (process, machine, execute)
    """
    
    def __init__(self, operation_generator: AtomicOperationGenerator):
        self.op_gen = operation_generator
    
    def handle_code_request(
        self,
        user_request: str,
        user_id: str,
        context: Dict
    ) -> List[OperationResult]:
        """
        Decompose code generation request into atomic operations.
        
        Returns list of operation results for transparency.
        """
        # RIVA's planning phase generates atomic operations
        atomic_ops = self._decompose_to_atomic(user_request, context)
        
        # Process each atomic operation
        results = []
        for op_request in atomic_ops:
            result = self.op_gen.generate_operation(
                request=op_request,
                user_id=user_id,
                context=context,
                auto_execute=False  # RIVA requires approval
            )
            results.append(result)
            
            # If verification failed, stop
            if not result.verification_passed:
                break
        
        return results
    
    def _decompose_to_atomic(
        self,
        request: str,
        context: Dict
    ) -> List[AtomicOperationRequest]:
        """
        Decompose code request into atomic operations.
        
        This is where RIVA's planning logic goes.
        Each step in RIVA's plan becomes atomic operation(s).
        """
        # Example decomposition (simplified)
        operations = []
        
        # Step 1: Analyze repository
        operations.append(AtomicOperationRequest(
            content=f"analyze repository structure for {request}",
            expected_type=('file', 'machine', 'read'),
            requires_approval=False,  # Safe read operation
            parent_task_id=None
        ))
        
        # Step 2: Generate code
        operations.append(AtomicOperationRequest(
            content=f"generate code for {request}",
            expected_type=('file', 'machine', 'execute'),
            requires_approval=True,  # Requires approval
            parent_task_id=None
        ))
        
        # Step 3: Run tests
        operations.append(AtomicOperationRequest(
            content=f"pytest tests/ -v",
            expected_type=('process', 'machine', 'execute'),
            requires_approval=False,  # Auto-run tests
            parent_task_id=None
        ))
        
        return operations
```

### Step 5.3: ReOS Integration

**Task:** Integrate ReOS system control as atomic operation generator.

**File:** `src/agents/reos_integration.py`

```python
from typing import List, Dict
from src.agents.operation_generator import AtomicOperationGenerator, AtomicOperationRequest, OperationResult

class ReOSSystemController:
    """
    ReOS generates atomic operations for system control tasks.
    
    Example:
    User: "What's using my memory?"
    ReOS generates:
    1. Execute ps command (process, machine, execute)
    2. Interpret results (stream, human, interpret)
    """
    
    def __init__(self, operation_generator: AtomicOperationGenerator):
        self.op_gen = operation_generator
    
    def handle_system_request(
        self,
        user_request: str,
        user_id: str,
        context: Dict
    ) -> List[OperationResult]:
        """Decompose system request into atomic operations."""
        atomic_ops = self._decompose_to_atomic(user_request, context)
        
        results = []
        for op_request in atomic_ops:
            result = self.op_gen.generate_operation(
                request=op_request,
                user_id=user_id,
                context=context,
                auto_execute=True  # ReOS can auto-execute read operations
            )
            results.append(result)
        
        return results
    
    def _decompose_to_atomic(
        self,
        request: str,
        context: Dict
    ) -> List[AtomicOperationRequest]:
        """Decompose system request into atomic operations."""
        # ReOS Parse Gate analyzes request
        # Generates appropriate system commands
        
        operations = []
        
        # Example: memory query
        if 'memory' in request.lower():
            operations.append(AtomicOperationRequest(
                content="ps aux --sort=-%mem | head -20",
                expected_type=('process', 'machine', 'execute'),
                requires_approval=False,  # Safe read
                parent_task_id=None
            ))
        
        return operations
```

### Step 5.4: CAIRN Integration

**Task:** Integrate CAIRN attention management as atomic operation generator.

**File:** `src/agents/cairn_integration.py`

```python
from typing import List, Dict
from src.agents.operation_generator import AtomicOperationGenerator, AtomicOperationRequest, OperationResult

class CAIRNAttentionManager:
    """
    CAIRN generates atomic operations for attention management.
    
    Example:
    User: "What should I work on?"
    CAIRN generates:
    1. Read calendar (file, machine, read)
    2. Read todo list (file, machine, read)
    3. Interpret priorities (stream, human, interpret)
    """
    
    def __init__(self, operation_generator: AtomicOperationGenerator):
        self.op_gen = operation_generator
    
    def handle_attention_request(
        self,
        user_request: str,
        user_id: str,
        context: Dict
    ) -> List[OperationResult]:
        """Decompose attention request into atomic operations."""
        atomic_ops = self._decompose_to_atomic(user_request, context)
        
        results = []
        for op_request in atomic_ops:
            result = self.op_gen.generate_operation(
                request=op_request,
                user_id=user_id,
                context=context,
                auto_execute=True  # CAIRN auto-executes read operations
            )
            results.append(result)
        
        return results
    
    def _decompose_to_atomic(
        self,
        request: str,
        context: Dict
    ) -> List[AtomicOperationRequest]:
        """Decompose attention request into atomic operations."""
        operations = []
        
        # Read calendar
        operations.append(AtomicOperationRequest(
            content="read calendar events for today",
            expected_type=('file', 'machine', 'read'),
            requires_approval=False,
            parent_task_id=None
        ))
        
        # Read todos
        operations.append(AtomicOperationRequest(
            content="read uncompleted todos",
            expected_type=('file', 'machine', 'read'),
            requires_approval=False,
            parent_task_id=None
        ))
        
        # Synthesize priorities
        operations.append(AtomicOperationRequest(
            content="synthesize priorities based on deadlines and blocks",
            expected_type=('stream', 'human', 'interpret'),
            requires_approval=False,
            parent_task_id=None
        ))
        
        return operations
```

**Acceptance Criteria:**
- [ ] AtomicOperationGenerator interface implemented
- [ ] RIVA generates atomic operations for code tasks
- [ ] ReOS generates atomic operations for system tasks
- [ ] CAIRN generates atomic operations for attention tasks
- [ ] All agent operations flow through classification → verification → execution
- [ ] RLHF feedback collected for all agent-generated operations
- [ ] Agents can batch operations with dependencies
- [ ] Tests for each agent integration pass

---

## Summary: Complete Implementation

### What You've Built (Weeks 1-5)

**Week 1: Database Foundation**
- 15+ tables for atomic operations, ML features, RLHF feedback
- Block-based storage for transparency
- Views and indexes for fast queries

**Week 2: Classification & Learning**
- Feature extraction with embeddings (SentenceTransformer)
- Atomic operation classifier (3×2×3 taxonomy)
- RLHF feedback collection (5 types)
- Learning loop with quality evaluation

**Week 3: Verification**
- 5-layer verification system (syntax, semantic, behavioral, safety, intent)
- Each layer returns structured results
- All results stored for learning

**Week 4: Execution**
- Shell, file, Python executors
- State capture and undo capability
- Resource limits and timeouts
- All execution logged

**Week 5: Agent Integration**
- RIVA, ReOS, CAIRN as atomic operation generators
- Agents decompose tasks → atomic operations → verify → execute → learn
- Complete transparency through blocks

### What Happens When You Give This to Claude Code

Claude Code will build a complete system where:

1. **Every request** (from user or agent) gets decomposed into atomic operations
2. **Every operation** gets classified, verified (5 layers), and executed safely
3. **Every interaction** generates ML features and RLHF feedback
4. **Every outcome** teaches the system to improve

The database will be **ML-ready from day one**. No retrofitting. No "we'll add ML later."

### What's Still Missing (Optional Future Work)

- ❌ ML training pipeline (XGBoost classifier, online learning)
- ❌ Dashboard for real-time metrics
- ❌ Performance optimization (caching, batch processing)
- ❌ Full RIVA planning system
- ❌ Full ReOS Parse Gate
- ❌ Full CAIRN coherence kernel

But the **foundation is complete**. You can add ML training when ready. The data is already being collected in the right format.

---

## Next Steps for Claude Code

1. **Start with Week 1**: Implement database schema
2. **Week 2**: Build classifier and RLHF collection
3. **Week 3**: Add verification layers
4. **Week 4**: Add execution engine
5. **Week 5**: Integrate agents

Then test end-to-end:
- User makes request
- Agent decomposes to atomic operations
- Each operation: classify → verify → execute
- Collect feedback
- Improve over time

**This is Talking Rock rebuilt from the ground up with ML at its core.**
