# RLHF Learning System

> **How Talking Rock learns from user feedback at multiple levels.**

The RLHF (Reinforcement Learning from Human Feedback) system captures user feedback to continuously improve classification accuracy and operation quality.

---

## Feedback Hierarchy

Feedback is collected at multiple levels, each with different reliability:

```
┌─────────────────────────────────────────────────────────────────┐
│                    FEEDBACK PYRAMID                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│                    ▲ Long-term Outcome                          │
│                   /│\   (Highest Confidence)                    │
│                  / │ \  • Operation persisted                   │
│                 /  │  \ • Pattern reused                        │
│                /   │   \• Referenced later                      │
│               ────────── ─────────────────                      │
│              /     │     \                                      │
│             /  Behavioral  \                                    │
│            /   (High Conf)  \                                   │
│           /    • Retry       \                                  │
│          /     • Undo         \                                 │
│         /      • Abandon       \                                │
│        ──────────────────────────                               │
│       /          │              \                               │
│      /      Correction          \                               │
│     /      (High Conf)           \                              │
│    /       • User fixes class     \                             │
│   /        • Provides reasoning    \                            │
│  ──────────────────────────────────                             │
│ /              │                    \                           │
│/          Approval                   \                          │
│          (Medium Conf)                \                         │
│          • Approve/reject              \                        │
│          • Time to decision             \                       │
│──────────────────────────────────────────                       │
│              Explicit Rating                                    │
│              (Medium Conf)                                      │
│              • 1-5 scale                                        │
│              • Dimensional ratings                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Feedback Types

### 1. Explicit Rating

User provides a direct 1-5 rating, optionally with dimensional breakdown.

```python
collect_explicit_rating(
    operation_id: str,
    user_id: str,
    rating: int,                    # 1-5
    dimensions: dict = None,        # {accuracy: 4, speed: 5, helpfulness: 3}
    comment: str = None
)
```

**Confidence:** Medium (0.7-0.9)
- Users may rate inconsistently
- Rating without context is less informative

### 2. Correction

User corrects a classification error. **Most valuable feedback.**

```python
collect_correction(
    operation_id: str,
    user_id: str,
    system_classification: dict,    # What system chose
    user_corrected_classification: dict,  # What it should be
    reasoning: str = None           # Why user made this correction
)
```

**Confidence:** High (0.9)
- Direct signal about classification error
- Reasoning provides training context

**Example:**
```python
collector.collect_correction(
    operation_id='op-123',
    user_id='user-1',
    system_classification={
        'destination': 'file',
        'consumer': 'human',
        'semantics': 'read'
    },
    user_corrected_classification={
        'destination': 'process',
        'consumer': 'machine',
        'semantics': 'execute'
    },
    reasoning='This was checking memory, not reading a file'
)
```

### 3. Approval

User approves or rejects the proposed operation.

```python
collect_approval(
    operation_id: str,
    user_id: str,
    approved: bool,
    time_to_decision_ms: int,       # How long user deliberated
    modified: bool = False,         # Did user modify before approving?
    modification_extent: float = 0.0,  # 0.0-1.0
    modification_details: dict = None
)
```

**Confidence:** Inferred from deliberation time:
- < 2 seconds: 0.9 (confident decision)
- 2-5 seconds: 0.7 (considered decision)
- 5-10 seconds: 0.5 (uncertain)
- > 10 seconds: 0.3 (struggled with decision)

### 4. Behavioral

Implicit signals from user actions.

```python
collect_behavioral_signals(
    operation_id: str,
    user_id: str,
    retried: bool = False,
    time_to_retry_ms: int = None,
    undid: bool = False,
    time_to_undo_ms: int = None,
    abandoned: bool = False
)
```

**Confidence:** High for quick actions:
- Quick retry (< 5s): 0.9 — system was wrong
- Quick undo (< 10s): 0.95 — system was wrong
- Slow retry/undo: 0.7 — might be user error

### 5. Long-term Outcome

Strongest signal: what happened over time.

```python
collect_long_term_outcome(
    operation_id: str,
    user_id: str,
    operation_persisted: bool,      # Did result stay?
    days_persisted: int,            # How long before change?
    reused_pattern: bool = False,   # Did user do similar again?
    referenced_later: bool = False  # Did user refer to this work?
)
```

**Confidence:** 0.95
- If user kept result and reused pattern → system was RIGHT
- If user reverted days later → system was WRONG

---

## Feedback Collection Flow

```
Operation Execution
        │
        ▼
┌───────────────────┐
│ Awaiting Approval │ ──────────────────────────────────────┐
└─────────┬─────────┘                                       │
          │                                                 │
          ▼                                                 │
    ┌─────────────┐     ┌────────────────────┐              │
    │   Approve   │────▶│ collect_approval() │              │
    │   [y/n]     │     │ time_to_decision   │              │
    └──────┬──────┘     └────────────────────┘              │
           │                                                │
           ▼                                                │
    ┌──────────────┐                                        │
    │ Executed     │                                        │
    └──────┬───────┘                                        │
           │                                                │
     ┌─────┴─────┐                                          │
     │           │                                          │
     ▼           ▼                                          │
┌─────────┐ ┌─────────┐    ┌─────────────────────────┐      │
│  Undo   │ │  Retry  │───▶│ collect_behavioral()    │      │
│         │ │         │    └─────────────────────────┘      │
└────┬────┘ └────┬────┘                                     │
     │           │                                          │
     ▼           ▼                                          │
┌─────────────────────────────────────────────────┐         │
│              Days/Weeks Later                    │         │
│  ┌─────────────────────────────────────────┐    │         │
│  │ collect_long_term_outcome()             │    │         │
│  │ - operation_persisted                    │    │         │
│  │ - reused_pattern                         │    │         │
│  └─────────────────────────────────────────┘    │         │
└─────────────────────────────────────────────────┘         │
                                                            │
┌───────────────────────────────────────────────────────────┘
│ Optional: User provides correction or rating
│  ┌─────────────────────────────────────────┐
│  │ collect_correction()                    │
│  │ collect_explicit_rating()               │
│  └─────────────────────────────────────────┘
└───────────────────────────────────────────────────────────
```

---

## Learning Metrics

### Classification Accuracy

Tracks how often system classifications match user expectations.

```python
def compute_learning_metrics(user_id: str, window_days: int = 7) -> dict:
    """Compute metrics over time window."""

    return {
        'classification_accuracy': correct / total,
        'user_satisfaction': avg_rating,
        'correction_rate': corrections / total,
        'by_destination_type': {
            'stream': 0.92,
            'file': 0.85,
            'process': 0.78
        },
        'by_consumer_type': {...},
        'by_execution_semantics': {...}
    }
```

### Improvement Tracking

Compares current window to previous window:

```python
{
    'classification_accuracy': 0.85,
    'previous_value': 0.80,
    'improvement': 0.05,  # +5%
    'p_value': 0.02       # Statistically significant
}
```

---

## Feedback Quality Evaluation

Not all feedback is equally useful. Quality metrics help weight feedback:

### Consistency Score

Do user's ratings align with their approvals?

```python
# If user rates 5/5 but then undoes → inconsistent
# If user rates 1/5 but approved → inconsistent
consistency_score = correlation(ratings, approvals)  # 0.0-1.0
```

### Informativeness Score

How detailed is the feedback?

```python
informativeness_score = corrections_with_reasoning / total_corrections
```

### Reliability Score

Can we trust this user's feedback?

Based on:
- Consistency over time
- Alignment with long-term outcomes
- Agreement with other users (if applicable)

---

## Database Schema

### User Feedback Table

```sql
CREATE TABLE user_feedback (
    id TEXT PRIMARY KEY,
    operation_block_id TEXT NOT NULL,
    user_id TEXT NOT NULL,

    -- Feedback type
    feedback_type TEXT NOT NULL,        -- 'explicit_rating', 'correction',
                                        -- 'approval', 'behavioral', 'long_term'

    -- Explicit feedback
    rating INTEGER,                     -- 1-5
    rating_dimensions JSON,             -- {accuracy: 4, speed: 5}
    comment TEXT,

    -- Correction feedback
    system_classification JSON,
    user_corrected_classification JSON,
    correction_reasoning TEXT,

    -- Approval feedback
    approved BOOLEAN,
    modified BOOLEAN,
    modification_extent REAL,           -- 0.0-1.0
    modification_details JSON,

    -- Behavioral feedback
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

    -- Meta-feedback
    feedback_confidence REAL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (operation_block_id) REFERENCES atomic_operations(block_id)
);
```

### Learning Metrics Table

```sql
CREATE TABLE rlhf_learning_metrics (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    metric_type TEXT NOT NULL,          -- 'classification_accuracy', etc.

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
    improvement REAL,
    confidence_interval JSON,
    p_value REAL,

    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Feedback Quality Table

```sql
CREATE TABLE feedback_quality_metrics (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,

    consistency_score REAL,
    informativeness_score REAL,
    reliability_score REAL,

    explicit_feedback_rate REAL,
    implicit_signals_available REAL,

    window_start TIMESTAMP NOT NULL,
    window_end TIMESTAMP NOT NULL,

    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Training Data Generation

Feedback is used to generate training data for ML models:

### Training Data View

```sql
CREATE VIEW training_data AS
SELECT
    ao.block_id,
    ao.user_request,
    ao.destination_type AS system_destination,
    ao.consumer_type AS system_consumer,
    ao.execution_semantics AS system_semantics,
    ao.classification_confidence,

    mlf.request_embedding,
    mlf.features_json,

    uf.approved,
    uf.user_corrected_classification,
    uf.rating,

    -- True labels (from user feedback)
    CASE
        WHEN uf.approved = 1 THEN ao.destination_type
        WHEN uf.user_corrected_classification IS NOT NULL
            THEN json_extract(uf.user_corrected_classification, '$.destination_type')
        ELSE NULL
    END AS true_destination,
    -- ... similar for consumer and semantics

FROM atomic_operations ao
JOIN ml_features mlf ON ao.block_id = mlf.operation_block_id
LEFT JOIN user_feedback uf ON ao.block_id = uf.operation_block_id
WHERE uf.feedback_type IN ('correction', 'approval')
  AND (uf.approved = 1 OR uf.user_corrected_classification IS NOT NULL);
```

### Dataset Snapshots

Periodically snapshot training data with quality metrics:

```sql
CREATE TABLE ml_datasets (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    dataset_name TEXT NOT NULL,

    start_date TIMESTAMP NOT NULL,
    end_date TIMESTAMP NOT NULL,

    train_operation_ids JSON NOT NULL,
    val_operation_ids JSON NOT NULL,
    test_operation_ids JSON NOT NULL,

    total_operations INTEGER NOT NULL,
    labeled_operations INTEGER NOT NULL,
    label_quality_score REAL,

    classification_accuracy REAL,
    model_version TEXT,
    model_performance JSON,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## Privacy Considerations

All learning happens **locally**:
- Feedback never leaves the user's machine
- No aggregation across users
- User can delete all feedback data
- Models trained on user's own data only

---

## Related Documentation

- [Foundation](./FOUNDATION.md) — Core philosophy (privacy by architecture)
- [Atomic Operations](./atomic-operations.md) — What gets classified
- [ML Features](./ml-features.md) — Features extracted for learning
- [Verification Layers](./verification-layers.md) — Verification that produces feedback opportunities
