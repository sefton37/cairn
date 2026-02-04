# CAIRN Simplification Plan

## The Problem

A simple question like "what do you think of my story" was going through **11 processing layers** before reaching the LLM. This over-engineering caused the persona_context (user's story) to potentially get lost or delayed.

## Changes Made (Phase 1)

### 1. Intent-Aware Verification Mode
**File:** `src/reos/atomic_ops/cairn_integration.py`

Before: All queries used STANDARD verification (4 layers: syntax, safety, semantic, behavioral)

After: READ/INTERPRET operations on STREAM destinations use FAST verification (2 layers: syntax, safety only)

```python
# In process_request(), before calling verify():
if operation.classification:
    is_read_op = operation.classification.semantics in (READ, INTERPRET)
    is_stream = operation.classification.destination == STREAM
    if is_read_op and is_stream:
        self.verifier.set_mode(VerificationMode.FAST)  # 2 layers
    else:
        self.verifier.set_mode(VerificationMode.STANDARD)  # 4 layers
```

**Impact:** Conversational queries skip semantic and behavioral verification.

### 2. Removed Redundant Decomposition Call
**Files:**
- `src/reos/atomic_ops/processor.py` - Added clarification fields to ProcessingResult
- `src/reos/atomic_ops/cairn_integration.py` - Use ProcessingResult fields instead of calling decompose() again

Before: Decomposer was called twice per request (once in processor, once in bridge)

After: Decomposer called once; ProcessingResult carries clarification info

```python
# ProcessingResult now includes:
@dataclass
class ProcessingResult:
    ...
    needs_clarification: bool = False
    clarification_prompt: str | None = None
```

**Impact:** One fewer LLM call for complex requests.

### 3. Conditional Intent Enhancement
**File:** `src/reos/atomic_ops/cairn_integration.py`

Before: `_enhance_with_intent()` ran for ALL queries

After: Only runs when needed (contextual references like "fix that" or missing classification)

```python
contextual_refs = {"that", "it", "this", "those", "them"}
words = set(user_input.lower().split())
has_contextual_ref = bool(words & contextual_refs)

if self.intent_engine and has_contextual_ref:
    # Only enhance when we need to resolve contextual references
    operation = self._enhance_with_intent(...)
elif self.intent_engine and not operation.classification:
    # Also enhance if we don't have a classification yet
    operation = self._enhance_with_intent(...)
```

**Impact:** Simple queries skip redundant pattern matching.

## New Layer Count

| Query Type | Before | After |
|------------|--------|-------|
| Personal question | 11 layers | ~6 layers |
| Calendar query (read) | 11 layers | ~7 layers |
| Create/Update mutation | 11 layers | 11 layers (full verification needed) |

## What's Preserved

1. **Atomic Operations** - Still created for learning
2. **Classification** - Still done for all requests
3. **Full Verification** - Still runs for mutations (CREATE, UPDATE, DELETE)
4. **Intent Engine** - Core logic unchanged
5. **Learning from Feedback** - Undo, approval, rejection still tracked

## Future Simplifications (Phase 2)

### Merge Layer 5 (Intent Enhancement) with Layer 11.1 (Intent Extraction)
Both do pattern matching and action detection. Could be consolidated.

### Make Atomic Op Recording Async
Record the atomic operation AFTER response generation for conversational queries. This moves learning out of the critical path.

### Skip Decomposition for Single-Sentence Queries
Simple questions don't need decomposition analysis at all.

## Files Modified

1. `src/reos/atomic_ops/cairn_integration.py`
   - Intent-aware verification mode selection
   - Removed redundant decomposition call
   - Conditional intent enhancement

2. `src/reos/atomic_ops/processor.py`
   - Added clarification fields to ProcessingResult

3. `src/reos/agent.py`
   - Cleaned up debug logging

4. `src/reos/cairn/intent_engine.py`
   - Cleaned up debug logging

---

*These changes preserve the atomic operation structure for AI learning while reducing overhead for simple conversational queries.*
