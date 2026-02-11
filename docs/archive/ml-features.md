# ML Feature Extraction

> **Feature extraction for atomic operation classification.**

Features are extracted from every user request to support ML-based classification. All extraction happens locally using lightweight models.

---

## Feature Categories

```
User Request: "Check memory usage and optimize auth.py"
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    FEATURE EXTRACTION                            │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  LEXICAL FEATURES                                          │ │
│  │  • token_count: 7                                          │ │
│  │  • verb_count: 2 (check, optimize)                         │ │
│  │  • noun_count: 2 (memory, usage)                           │ │
│  │  • has_file_extension: true (.py)                          │ │
│  │  • file_extension_type: "py"                               │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  SEMANTIC FEATURES (Embeddings)                            │ │
│  │  • request_embedding: [0.12, -0.34, ...] (384-dim)         │ │
│  │  • verb_embeddings: [[...], [...]]                         │ │
│  │  • object_embeddings: [[...], [...]]                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  SYNTACTIC FEATURES                                        │ │
│  │  • has_imperative_verb: true                               │ │
│  │  • has_interrogative: false                                │ │
│  │  • has_conditional: false                                  │ │
│  │  • has_negation: false                                     │ │
│  │  • sentence_count: 1                                       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  DOMAIN FEATURES                                           │ │
│  │  • mentions_code: true                                     │ │
│  │  • detected_languages: ["python"]                          │ │
│  │  • mentions_system_resource: true (memory)                 │ │
│  │  • has_file_operation: false                               │ │
│  │  • mentions_testing: false                                 │ │
│  │  • mentions_git: false                                     │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  CONTEXT FEATURES                                          │ │
│  │  • time_of_day: 14 (hour)                                  │ │
│  │  • day_of_week: 2 (Tuesday)                                │ │
│  │  • recent_operation_count: 5                               │ │
│  │  • recent_success_rate: 0.85                               │ │
│  │  • user_skill_estimate: 0.7                                │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Lexical Features

Extracted from tokenization and POS tagging.

### Extraction

```python
def _extract_lexical_features(request: str, tokens: list, pos_tags: list) -> dict:
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
```

### Feature Definitions

| Feature | Type | Description |
|---------|------|-------------|
| `token_count` | int | Number of tokens |
| `char_count` | int | Character length |
| `verb_count` | int | Number of verbs detected |
| `noun_count` | int | Number of nouns detected |
| `verbs` | list[str] | Actual verb tokens |
| `nouns` | list[str] | Actual noun tokens |
| `has_file_extension` | bool | Contains file extension |
| `file_extension_type` | str | Extension if present |
| `avg_word_length` | float | Average token length |

---

## Semantic Features (Embeddings)

Generated using sentence-transformers for semantic similarity.

### Model

```python
# all-MiniLM-L6-v2: 22MB, runs on CPU
# 384-dimensional embeddings
model = SentenceTransformer('all-MiniLM-L6-v2')
```

### Extraction

```python
def _extract_semantic_features(request: str, tokens: list, pos_tags: list) -> dict:
    """Extract embeddings for semantic similarity."""

    # Full request embedding
    request_emb = self.embedder.encode(request, convert_to_numpy=True)

    # Verb embeddings (for action classification)
    verbs = [token for token, tag in pos_tags if tag.startswith('VB')]
    verb_embs = [self.embedder.encode(v, convert_to_numpy=True) for v in verbs]

    # Object embeddings (for destination classification)
    nouns = [token for token, tag in pos_tags if tag.startswith('NN')]
    object_embs = [self.embedder.encode(n, convert_to_numpy=True) for n in nouns]

    return {
        'request_embedding': request_emb,        # ndarray (384,)
        'verb_embeddings': np.array(verb_embs),  # ndarray (n_verbs, 384)
        'object_embeddings': np.array(object_embs),  # ndarray (n_nouns, 384)
        'verb_tokens': verbs,
        'object_tokens': nouns
    }
```

### Storage

Embeddings are stored as binary blobs (float32):

```python
request_emb_blob = features['semantic']['request_embedding'].astype(np.float32).tobytes()
```

### Uses

- **Semantic similarity** — Compare request to known operation patterns
- **Classification** — Input to ML classifier
- **Intent verification** — Check operation matches request

---

## Syntactic Features

Extracted from sentence structure.

### Extraction

```python
def _extract_syntactic_features(request: str, tokens: list, pos_tags: list) -> dict:
    """Extract syntax-level features."""

    return {
        'has_imperative_verb': any(tag == 'VB' for _, tag in pos_tags),
        'has_interrogative': request.strip().endswith('?'),
        'has_conditional': any(word in tokens for word in ['if', 'when', 'should', 'would']),
        'has_negation': any(word in tokens for word in ['not', 'no', "don't", "won't", "can't"]),
        'sentence_count': len(re.split(r'[.!?]', request))
    }
```

### Feature Definitions

| Feature | Type | Relevance |
|---------|------|-----------|
| `has_imperative_verb` | bool | Commands have imperatives → `execute` |
| `has_interrogative` | bool | Questions → `read` semantics |
| `has_conditional` | bool | May need decomposition |
| `has_negation` | bool | Affects intent understanding |
| `sentence_count` | int | Complex requests may need decomposition |

---

## Domain Features

Domain-specific indicators for classification.

### Extraction

```python
def _extract_domain_features(request: str, tokens: list) -> dict:
    """Extract domain-specific indicators."""

    # Code-related patterns
    code_patterns = {
        'python': r'\.(py|pyx|pyd)\b',
        'javascript': r'\.(js|jsx|ts|tsx)\b',
        'java': r'\.(java|class|jar)\b',
        'cpp': r'\.(cpp|cc|cxx|h|hpp)\b',
        'rust': r'\.rs\b',
        'shell': r'\.(sh|bash|zsh)\b'
    }

    detected_languages = [
        lang for lang, pattern in code_patterns.items()
        if re.search(pattern, request, re.IGNORECASE)
    ]

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
```

### Classification Hints

| Feature | Destination | Consumer | Semantics |
|---------|-------------|----------|-----------|
| `mentions_code` | file | machine | - |
| `mentions_system_resource` | process | - | - |
| `has_file_operation` | file | - | execute |
| `has_immediate_verb` | stream | human | read |
| `mentions_testing` | process | machine | interpret |
| `mentions_git` | file/process | machine | execute |

---

## Context Features

Environmental context at time of operation.

### Extraction

```python
def _extract_context_features(context: dict) -> dict:
    """Extract features from system/user context."""

    return {
        'time_of_day': context.get('time_of_day', 0),       # hour 0-23
        'day_of_week': context.get('day_of_week', 0),       # 0=Monday
        'recent_operation_count': context.get('recent_operation_count', 0),
        'recent_success_rate': context.get('recent_success_rate', 0.0),
        'user_skill_estimate': context.get('user_skill_estimate', 0.5)
    }
```

### Uses

- **Time patterns** — User behavior varies by time of day
- **Session context** — Recent operations inform classification
- **Skill adaptation** — Adjust verification strictness

---

## Database Storage

### ML Features Table

```sql
CREATE TABLE ml_features (
    operation_block_id TEXT PRIMARY KEY,

    -- Raw features (JSON for flexibility)
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

    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id)
);
```

### Conversion to DB Format

```python
def features_to_db_format(features: dict) -> tuple:
    """Convert features to database storage format."""

    # Convert embeddings to bytes
    request_emb = features['semantic']['request_embedding'].astype(np.float32).tobytes()

    verb_emb = None
    if features['semantic']['verb_embeddings'] is not None:
        verb_emb = features['semantic']['verb_embeddings'].astype(np.float32).tobytes()

    obj_emb = None
    if features['semantic']['object_embeddings'] is not None:
        obj_emb = features['semantic']['object_embeddings'].astype(np.float32).tobytes()

    # Store non-embedding features as JSON
    features_json = json.dumps({
        'lexical': {k: v for k, v in features['lexical'].items()
                    if not isinstance(v, np.ndarray)},
        'syntactic': features['syntactic'],
        'domain': features['domain'],
        'context': features['context'],
        'request_hash': features['request_hash']
    })

    return features_json, request_emb, verb_emb, obj_emb
```

---

## Performance

### Extraction Time

| Component | Time | Notes |
|-----------|------|-------|
| Tokenization | < 10ms | NLTK punkt |
| POS Tagging | < 50ms | NLTK perceptron |
| Embedding | ~ 100ms | sentence-transformers |
| **Total** | < 200ms | Acceptable for interactive use |

### Model Size

| Component | Size |
|-----------|------|
| all-MiniLM-L6-v2 | 22MB |
| NLTK data | ~ 30MB |
| **Total** | ~ 52MB |

### Dependencies

```python
# Required
nltk
sentence-transformers
numpy

# Install
pip install sentence-transformers nltk numpy
```

---

## Feature Pipeline Integration

```
User Request
     │
     ▼
┌─────────────────┐
│ FeatureExtractor │
│ .extract_all()   │
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  {                                      │
│    'lexical': {...},                    │
│    'semantic': {                        │
│      'request_embedding': ndarray,      │
│      'verb_embeddings': ndarray,        │
│      ...                                │
│    },                                   │
│    'syntactic': {...},                  │
│    'domain': {...},                     │
│    'context': {...},                    │
│    'request_hash': 'abc123...'          │
│  }                                      │
└────────────────────┬────────────────────┘
                     │
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐    ┌─────────────────┐
│  Classifier     │    │  ML Features    │
│  (Rule-based    │    │  Table          │
│   or ML model)  │    │  (for training) │
└─────────────────┘    └─────────────────┘
```

---

## Related Documentation

- [Foundation](./FOUNDATION.md) — Core philosophy
- [Atomic Operations](./atomic-operations.md) — What gets classified
- [RLHF Learning](./rlhf-learning.md) — How features inform learning
- [Verification Layers](./verification-layers.md) — Features in intent verification
