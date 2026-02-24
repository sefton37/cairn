"""Tests for IntentToNolTranslator (Phase 4)."""
from __future__ import annotations

from pathlib import Path

import pytest

from reos.code_mode.intent_to_nol import (
    IntentToNolTranslator,
    NolFunctionSignature,
    NolMemoCache,
)


class TestNolMemoCache:
    def test_empty_cache(self):
        cache = NolMemoCache()
        assert cache.size() == 0
        assert cache.get("abc") is None
        assert not cache.has("abc")

    def test_put_and_get(self):
        cache = NolMemoCache()
        sig = NolFunctionSignature(
            func_name="test",
            param_count=0,
            param_types=[],
            assembly="CONST I64 0 42\nHALT\n",
            intent_hash="abc123",
        )
        cache.put(sig)
        assert cache.size() == 1
        assert cache.has("abc123")
        assert cache.get("abc123") == sig

    def test_clear(self):
        cache = NolMemoCache()
        sig = NolFunctionSignature(
            func_name="test",
            param_count=0,
            param_types=[],
            assembly="test",
            intent_hash="abc",
        )
        cache.put(sig)
        cache.clear()
        assert cache.size() == 0


class TestIntentToNolTranslator:
    def test_translate_simple(self):
        translator = IntentToNolTranslator()
        sig = translator.translate(
            what="Compute the sum of two integers",
            acceptance=["Returns an I64 value"],
        )
        assert sig.func_name.startswith("Compute")
        assert sig.param_count == 0
        assert "CONST" in sig.assembly
        assert "HALT" in sig.assembly
        assert sig.intent_hash  # non-empty

    def test_translate_with_params(self):
        translator = IntentToNolTranslator()
        sig = translator.translate(
            what="Add two numbers",
            acceptance=["Returns sum"],
            param_types=["I64", "I64"],
        )
        assert sig.param_count == 2
        assert sig.param_types == ["I64", "I64"]
        # Flat translate puts params in comments, not PARAM instructions
        assert "PARAM[0]: I64" in sig.assembly
        assert "PARAM[1]: I64" in sig.assembly

    def test_translate_produces_valid_nol(self):
        """The generated assembly should be parseable by the nolang assembler."""
        NOL_BINARY = Path.home() / "dev" / "nol" / "target" / "release" / "nolang"
        if not NOL_BINARY.exists():
            pytest.skip("nolang binary not found")

        from reos.code_mode.nol_bridge import NolBridge
        bridge = NolBridge(nol_binary=NOL_BINARY)

        translator = IntentToNolTranslator()
        sig = translator.translate(
            what="Return zero",
            acceptance=["Result is 0"],
        )

        result = bridge.assemble(sig.assembly)
        assert result.success, f"Assembly failed: {result.error}"

    def test_hash_memoization(self):
        translator = IntentToNolTranslator()

        sig1 = translator.translate("Do X", ["Criterion A"])
        sig2 = translator.translate("Do X", ["Criterion A"])

        assert sig1 is sig2  # Same object from cache
        assert translator.cache.size() == 1

    def test_different_intents_different_hashes(self):
        translator = IntentToNolTranslator()

        sig1 = translator.translate("Do X", ["Criterion A"])
        sig2 = translator.translate("Do Y", ["Criterion B"])

        assert sig1.intent_hash != sig2.intent_hash
        assert translator.cache.size() == 2

    def test_hash_deterministic(self):
        h1 = IntentToNolTranslator.compute_intent_hash("Do X", ["A", "B"])
        h2 = IntentToNolTranslator.compute_intent_hash("Do X", ["A", "B"])
        assert h1 == h2

    def test_hash_order_independent_for_acceptance(self):
        # Acceptance criteria are sorted before hashing
        h1 = IntentToNolTranslator.compute_intent_hash("Do X", ["A", "B"])
        h2 = IntentToNolTranslator.compute_intent_hash("Do X", ["B", "A"])
        assert h1 == h2

    def test_acceptance_in_comments(self):
        translator = IntentToNolTranslator()
        sig = translator.translate(
            what="Test",
            acceptance=["Output is positive", "No side effects"],
        )
        assert "; POST[0]: " in sig.assembly
        assert "; POST[1]: " in sig.assembly


class TestTranslateWithChildren:
    def test_children_become_helper_functions(self):
        translator = IntentToNolTranslator()
        sig = translator.translate_with_children(
            what="Parent task",
            acceptance=["All subtasks complete"],
            children=[
                {"what": "Child A", "acceptance": ["A done"]},
                {"what": "Child B", "acceptance": ["B done"]},
            ],
        )
        assert len(sig.children) == 2
        # Assembly should contain multiple FUNC/ENDFUNC blocks
        func_count = sig.assembly.count("ENDFUNC")
        assert func_count >= 3  # 2 children + 1 parent

    def test_child_caching(self):
        translator = IntentToNolTranslator()

        # First call: creates children
        sig1 = translator.translate_with_children(
            what="Parent",
            acceptance=[],
            children=[{"what": "Shared child", "acceptance": ["done"]}],
        )

        # Second call with same child: should use cache
        sig2 = translator.translate(
            what="Shared child",
            acceptance=["done"],
        )

        assert sig2.intent_hash == sig1.children[0].intent_hash

    def test_produces_valid_nol_with_children(self):
        NOL_BINARY = Path.home() / "dev" / "nol" / "target" / "release" / "nolang"
        if not NOL_BINARY.exists():
            pytest.skip("nolang binary not found")

        from reos.code_mode.nol_bridge import NolBridge
        bridge = NolBridge(nol_binary=NOL_BINARY)

        translator = IntentToNolTranslator()
        sig = translator.translate_with_children(
            what="Parent task",
            acceptance=["Done"],
            children=[
                {"what": "Step 1", "acceptance": ["Step 1 done"]},
            ],
        )

        result = bridge.assemble(sig.assembly)
        assert result.success, f"Assembly failed: {result.error}"
