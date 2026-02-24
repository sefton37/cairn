"""Intent-to-NOL translator.

Converts RIVA intentions (what + acceptance criteria) into NOL assembly
function signatures. This creates a bridge where:
- `Intention.acceptance` → NOL POST conditions (as inline comments)
- Child intentions → NOL helper FUNC blocks
- HASH fields make decomposition trees content-addressable

The hash memoization enables: same intention twice → cached result.

Note on HASH placeholders
--------------------------
Generated assembly uses ``HASH 0x0000 0x0000 0x0000`` as a placeholder.
The NOL assembler accepts placeholder hashes (it records them verbatim);
only the *verifier* enforces hash correctness.

To obtain assembly that passes full verification, call
``NolBridge.compute_hashes(sig.assembly)`` to replace placeholders with
the blake3-derived values before running ``assemble → verify → run``.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NolFunctionSignature:
    """A NOL function signature derived from an intention.

    Attributes:
        func_name: Descriptive name (for documentation, not used in NOL).
        param_count: Number of parameters.
        param_types: Type tags for each parameter (e.g. ``["I64", "I64"]``).
        assembly: Complete NOL assembly text for this function (may contain
                  ``HASH 0x0000 0x0000 0x0000`` placeholders — call
                  ``NolBridge.compute_hashes`` to fill them in before
                  verification).
        intent_hash: SHA-256 hash of the intention (for memoization).
        children: Child function signatures (from decomposed intentions).
    """

    func_name: str
    param_count: int
    param_types: list[str]
    assembly: str
    intent_hash: str
    children: list[NolFunctionSignature] = field(default_factory=list)


class NolMemoCache:
    """Content-addressable cache for verified NOL functions.

    Uses intent_hash as the key.  If an intention's hash matches a previously
    translated function, skip re-translation and reuse the cached result.
    """

    def __init__(self) -> None:
        self._cache: dict[str, NolFunctionSignature] = {}

    def get(self, intent_hash: str) -> NolFunctionSignature | None:
        """Look up a cached function by intent hash."""
        return self._cache.get(intent_hash)

    def put(self, sig: NolFunctionSignature) -> None:
        """Cache a translated function signature."""
        self._cache[sig.intent_hash] = sig
        logger.debug("Cached NOL function: %s (hash=%s)", sig.func_name, sig.intent_hash[:12])

    def has(self, intent_hash: str) -> bool:
        """Check if a hash is cached."""
        return intent_hash in self._cache

    def size(self) -> int:
        """Number of cached entries."""
        return len(self._cache)

    def clear(self) -> None:
        """Clear the cache."""
        self._cache.clear()


class IntentToNolTranslator:
    """Translates RIVA intentions into NOL assembly.

    The translation follows these principles:

    1. An Intention's ``what`` becomes the function's purpose (comment/doc).
    2. An Intention's ``acceptance`` criteria become POST-condition comments
       embedded in the function body as ``; POST[n]: <criterion>`` lines.
    3. Child intentions become helper FUNC blocks (via
       :meth:`translate_with_children`).
    4. The ``intent_hash`` is computed from ``what`` + ``acceptance`` for
       deterministic memoization — the same intention twice always yields
       the same (cached) result.

    Simple translations (no children) produce a flat NOL program:
    ``CONST I64 0 0 / HALT`` — a zero-returning skeleton that assembles
    immediately.  The comments carry the POST-condition documentation.

    Decomposed translations (with children) produce a multi-FUNC program
    where each child is a separate ``FUNC`` block.  These programs contain
    ``HASH 0x0000 0x0000 0x0000`` placeholder instructions.  Call
    ``NolBridge.compute_hashes(sig.assembly)`` before verification.
    """

    def __init__(self, memo_cache: NolMemoCache | None = None) -> None:
        self._cache = memo_cache or NolMemoCache()

    @staticmethod
    def compute_intent_hash(what: str, acceptance: list[str]) -> str:
        """Compute a deterministic hash for an intention.

        The hash is based on the intention's ``what`` and sorted
        ``acceptance`` criteria.  Same intention → same hash → cache hit.
        Acceptance criteria are sorted so order does not affect the hash.
        """
        content = what + "\n" + "\n".join(sorted(acceptance))
        return hashlib.sha256(content.encode()).hexdigest()

    def translate(
        self,
        what: str,
        acceptance: list[str],
        param_types: list[str] | None = None,
    ) -> NolFunctionSignature:
        """Translate an intention into a NOL function signature.

        Produces a flat NOL program (no FUNC block) that assembles directly.
        The acceptance criteria appear as ``; POST[n]:`` comment lines in the
        assembly, serving as inline documentation of the intended postconditions.

        Args:
            what: The intention's goal description.
            acceptance: List of acceptance criteria (become POST comments).
            param_types: Optional parameter types — currently noted in comments
                         only for flat programs (PARAM is inside FUNC blocks).

        Returns:
            :class:`NolFunctionSignature` with assembleable ``assembly`` text.
        """
        intent_hash = self.compute_intent_hash(what, acceptance)

        # Check cache first
        cached = self._cache.get(intent_hash)
        if cached is not None:
            logger.debug("Cache hit for intent: %s (hash=%s)", what[:50], intent_hash[:12])
            return cached

        params = param_types or []

        lines: list[str] = []

        # Intent description as a comment header
        lines.append(f"; INTENT: {what[:80]}")

        # Acceptance criteria as POST-condition comments
        for i, criterion in enumerate(acceptance):
            lines.append(f"; POST[{i}]: {criterion}")

        # Parameter types as comments (flat programs have no PARAM instructions)
        for i, ptype in enumerate(params):
            lines.append(f"; PARAM[{i}]: {ptype}")

        # Body: return zero (placeholder — real body filled in by LLM in Phase 3)
        lines.append("CONST I64 0 0")
        lines.append("HALT")

        assembly = "\n".join(lines) + "\n"

        sig = NolFunctionSignature(
            func_name=what[:80],
            param_count=len(params),
            param_types=params,
            assembly=assembly,
            intent_hash=intent_hash,
        )

        self._cache.put(sig)
        return sig

    def translate_with_children(
        self,
        what: str,
        acceptance: list[str],
        children: list[dict[str, Any]],
        param_types: list[str] | None = None,
    ) -> NolFunctionSignature:
        """Translate an intention with child intentions into multi-FUNC NOL.

        Each child becomes a helper FUNC block (lower function indices).
        The parent becomes the last FUNC block, calling children by index.

        The generated assembly contains ``HASH 0x0000 0x0000 0x0000``
        placeholder instructions.  For a fully verifiable program, call
        ``NolBridge.compute_hashes(sig.assembly)`` before assembling.

        Args:
            what: Parent intention goal.
            acceptance: Parent acceptance criteria.
            children: List of dicts with ``'what'`` and ``'acceptance'`` keys,
                      optionally ``'param_types'``.
            param_types: Parent parameter types.

        Returns:
            :class:`NolFunctionSignature` with multi-FUNC ``assembly`` text.
        """
        # Translate children first (populates cache for re-use)
        child_sigs: list[NolFunctionSignature] = []
        for child in children:
            child_sig = self.translate(
                what=child["what"],
                acceptance=child.get("acceptance", []),
                param_types=child.get("param_types"),
            )
            child_sigs.append(child_sig)

        # Check parent cache
        intent_hash = self.compute_intent_hash(what, acceptance)
        cached = self._cache.get(intent_hash)
        if cached is not None:
            return cached

        params = param_types or []

        all_lines: list[str] = []

        # Helper FUNC blocks (one per child, in order)
        for child_sig in child_sigs:
            child_lines = self._build_func_block(
                what=child_sig.func_name,
                acceptance=[],  # already translated — keep child body minimal
                param_types=child_sig.param_types,
            )
            all_lines.extend(child_lines)

        # Parent FUNC block
        parent_lines = self._build_func_block(
            what=what,
            acceptance=acceptance,
            param_types=params,
        )
        all_lines.extend(parent_lines)

        # Entry point: push zero-args for parent params, then CALL parent func
        for _ in params:
            all_lines.append("CONST I64 0 0")
        parent_func_idx = len(child_sigs)  # 0-indexed: children are 0..N-1, parent is N
        all_lines.append(f"CALL {parent_func_idx}")
        all_lines.append("HALT")

        assembly = "\n".join(all_lines) + "\n"

        sig = NolFunctionSignature(
            func_name=what[:80],
            param_count=len(params),
            param_types=params,
            assembly=assembly,
            intent_hash=intent_hash,
            children=child_sigs,
        )

        self._cache.put(sig)
        return sig

    @staticmethod
    def _build_func_block(
        what: str,
        acceptance: list[str],
        param_types: list[str] | None,
    ) -> list[str]:
        """Build a FUNC block as a list of assembly lines.

        The block includes:
        - ``FUNC n_params body_len``
        - ``PARAM type`` lines (one per param)
        - ``; POST[n]:`` comment lines (one per acceptance criterion)
        - ``CONST I64 0 0`` placeholder body
        - ``RET``
        - ``HASH 0x0000 0x0000 0x0000`` (placeholder — fill via compute_hashes)
        - ``ENDFUNC``

        body_len counts: PARAM * n + body_instructions + 1 (HASH).
        """
        params = param_types or []
        n_params = len(params)

        # Body instructions: CONST I64 0 0, RET (2 real instructions)
        # HASH counts as one body instruction per spec
        # PARAM instructions are inside body_len per spec
        body_len = n_params + 2 + 1  # PARAMs + (CONST + RET) + HASH

        lines: list[str] = []
        lines.append(f"FUNC {n_params} {body_len}")

        for ptype in params:
            lines.append(f"PARAM {ptype}")

        # POST conditions as comments (the acceptance criteria bridge)
        lines.append(f"; INTENT: {what[:80]}")
        for i, criterion in enumerate(acceptance):
            lines.append(f"; POST[{i}]: {criterion}")

        # Placeholder body
        lines.append("CONST I64 0 0")
        lines.append("RET")

        # HASH placeholder — replace via NolBridge.compute_hashes()
        lines.append("HASH 0x0000 0x0000 0x0000")
        lines.append("ENDFUNC")

        return lines

    @property
    def cache(self) -> NolMemoCache:
        """Access the memoization cache."""
        return self._cache
