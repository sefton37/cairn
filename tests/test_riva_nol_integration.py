"""Tests for RIVA → NOL integration (Phase 3).

Covers:
- Action dataclass NOL fields (nol_assembly, nol_binary)
- Action.to_dict() / from_dict() with NOL fields
- WorkContext.nol_bridge field
- _verify_nol_structural layer function
"""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from reos.code_mode.intention import Action, ActionType, WorkContext
from reos.code_mode.nol_bridge import NolBridge
from reos.code_mode.optimization.verification_layers import (
    LayerResult,
    VerificationLayer,
    _verify_nol_structural,
)


def run_async(coro):
    """Run a coroutine synchronously.

    Compatibility shim so async tests run without pytest-asyncio.
    Replace with @pytest.mark.asyncio once pytest-asyncio is installed.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# Path to the nolang binary built in the NOL project.
NOL_BINARY = Path.home() / "dev" / "nol" / "target" / "release" / "nolang"


@pytest.fixture
def nol_bridge():
    """Create a NolBridge backed by the real binary, skip if absent."""
    if not NOL_BINARY.exists():
        pytest.skip("nolang binary not found — run 'cargo build --release' in the nol project")
    return NolBridge(nol_binary=NOL_BINARY)


@pytest.fixture
def work_ctx(nol_bridge):
    """Minimal WorkContext with NOL bridge wired in."""
    sandbox = MagicMock()
    checkpoint = MagicMock()
    return WorkContext(
        sandbox=sandbox,
        llm=None,
        checkpoint=checkpoint,
        nol_bridge=nol_bridge,
    )


# ---------------------------------------------------------------------------
# NOL_STRUCTURAL verification layer
# ---------------------------------------------------------------------------


class TestNolStructuralVerification:
    def test_valid_nol_assembly_passes(self, work_ctx):
        """Valid assembly with HALT should pass structural verification."""
        action = Action(
            type=ActionType.COMMAND,
            content="compute 42",
            nol_assembly="CONST I64 0 42\nHALT\n",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert result.passed
        assert result.confidence == 1.0
        assert "2 instructions" in result.reason

    def test_invalid_nol_assembly_fails(self, work_ctx):
        """Unrecognised opcode should fail with assembly error."""
        action = Action(
            type=ActionType.COMMAND,
            content="bad code",
            nol_assembly="INVALID_OPCODE\n",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert not result.passed
        assert "assembly failed" in result.reason.lower()

    def test_no_nol_assembly_passes_with_low_confidence(self, work_ctx):
        """Actions without NOL assembly should pass transparently (non-blocking)."""
        action = Action(
            type=ActionType.COMMAND,
            content="regular command",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert result.passed
        assert result.confidence == 0.5

    def test_no_nol_bridge_fails(self):
        """When nol_bridge is None but assembly is present, layer must fail."""
        sandbox = MagicMock()
        checkpoint = MagicMock()
        ctx = WorkContext(sandbox=sandbox, llm=None, checkpoint=checkpoint)
        action = Action(
            type=ActionType.COMMAND,
            content="compute",
            nol_assembly="CONST I64 0 42\nHALT\n",
        )
        result = run_async(_verify_nol_structural(action, ctx))
        assert not result.passed
        assert "not configured" in result.reason.lower()

    def test_result_is_layer_result_type(self, work_ctx):
        """Return type must be LayerResult."""
        action = Action(
            type=ActionType.COMMAND,
            content="test",
            nol_assembly="CONST I64 0 1\nHALT\n",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert isinstance(result, LayerResult)
        assert result.layer == VerificationLayer.NOL_STRUCTURAL

    def test_assembly_without_halt_fails_verification(self, work_ctx):
        """Assembly that lacks HALT passes the assembler but fails the verifier."""
        action = Action(
            type=ActionType.COMMAND,
            content="no halt",
            nol_assembly="CONST I64 0 42\n",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert not result.passed

    def test_successful_result_includes_instruction_count(self, work_ctx):
        """Successful structural verification should populate instruction_count detail."""
        action = Action(
            type=ActionType.COMMAND,
            content="arithmetic",
            nol_assembly="CONST I64 0 10\nCONST I64 0 20\nADD\nHALT\n",
        )
        result = run_async(_verify_nol_structural(action, work_ctx))
        assert result.passed
        assert result.details.get("instruction_count") == 4

    def test_temp_binary_cleaned_up_on_success(self, work_ctx):
        """No .nolb files should be left behind after a successful structural check."""
        import glob

        before = set(glob.glob("/tmp/*.nolb"))
        action = Action(
            type=ActionType.COMMAND,
            content="compute",
            nol_assembly="CONST I64 0 42\nHALT\n",
        )
        run_async(_verify_nol_structural(action, work_ctx))
        after = set(glob.glob("/tmp/*.nolb"))
        assert (after - before) == set(), "Stray .nolb files left after structural verify"


# ---------------------------------------------------------------------------
# Action dataclass — NOL fields
# ---------------------------------------------------------------------------


class TestActionNolFields:
    def test_action_default_nol_fields_are_none(self):
        """nol_assembly and nol_binary default to None."""
        action = Action(type=ActionType.COMMAND, content="test")
        assert action.nol_assembly is None
        assert action.nol_binary is None

    def test_action_stores_nol_assembly(self):
        action = Action(
            type=ActionType.COMMAND,
            content="test",
            nol_assembly="CONST I64 0 42\nHALT\n",
        )
        assert action.nol_assembly == "CONST I64 0 42\nHALT\n"

    def test_action_stores_nol_binary(self):
        action = Action(
            type=ActionType.COMMAND,
            content="test",
            nol_binary=b"\x00\x01\x02",
        )
        assert action.nol_binary == b"\x00\x01\x02"

    def test_action_to_dict_includes_nol_assembly(self):
        action = Action(
            type=ActionType.COMMAND,
            content="test",
            nol_assembly="CONST I64 0 42\nHALT\n",
        )
        d = action.to_dict()
        assert d["nol_assembly"] == "CONST I64 0 42\nHALT\n"

    def test_action_to_dict_excludes_nol_binary(self):
        """nol_binary is ephemeral runtime data and must not appear in serialized form."""
        action = Action(
            type=ActionType.COMMAND,
            content="test",
            nol_binary=b"\x00\x01",
        )
        d = action.to_dict()
        assert "nol_binary" not in d

    def test_action_to_dict_nol_assembly_none_by_default(self):
        action = Action(type=ActionType.COMMAND, content="test")
        d = action.to_dict()
        assert d["nol_assembly"] is None

    def test_action_from_dict_with_nol_assembly(self):
        d = {
            "type": "command",
            "content": "test",
            "nol_assembly": "CONST I64 0 42\nHALT\n",
        }
        action = Action.from_dict(d)
        assert action.nol_assembly == "CONST I64 0 42\nHALT\n"

    def test_action_from_dict_without_nol_assembly(self):
        d = {"type": "command", "content": "test"}
        action = Action.from_dict(d)
        assert action.nol_assembly is None

    def test_action_roundtrip_with_nol_assembly(self):
        original = Action(
            type=ActionType.COMMAND,
            content="test",
            target="some/file.py",
            nol_assembly="CONST I64 0 99\nHALT\n",
        )
        restored = Action.from_dict(original.to_dict())
        assert restored.type == original.type
        assert restored.content == original.content
        assert restored.target == original.target
        assert restored.nol_assembly == original.nol_assembly


# ---------------------------------------------------------------------------
# WorkContext — nol_bridge field
# ---------------------------------------------------------------------------


class TestWorkContextNolBridge:
    def test_work_context_nol_bridge_defaults_to_none(self):
        """nol_bridge must default to None for backward compatibility."""
        sandbox = MagicMock()
        checkpoint = MagicMock()
        ctx = WorkContext(sandbox=sandbox, llm=None, checkpoint=checkpoint)
        assert ctx.nol_bridge is None

    def test_work_context_accepts_nol_bridge(self, nol_bridge):
        """A real NolBridge instance can be assigned to nol_bridge."""
        sandbox = MagicMock()
        checkpoint = MagicMock()
        ctx = WorkContext(
            sandbox=sandbox,
            llm=None,
            checkpoint=checkpoint,
            nol_bridge=nol_bridge,
        )
        assert ctx.nol_bridge is nol_bridge

    def test_work_context_nol_bridge_accessible_via_fixture(self, work_ctx, nol_bridge):
        """Fixture-created WorkContext wires nol_bridge correctly."""
        assert work_ctx.nol_bridge is nol_bridge


# ---------------------------------------------------------------------------
# VerificationLayer enum — NOL_STRUCTURAL present
# ---------------------------------------------------------------------------


class TestVerificationLayerEnum:
    def test_nol_structural_in_enum(self):
        assert VerificationLayer.NOL_STRUCTURAL.value == "nol_structural"

    def test_nol_structural_is_first_layer(self):
        """NOL_STRUCTURAL should precede SYNTAX in enum declaration order."""
        members = list(VerificationLayer)
        nol_idx = members.index(VerificationLayer.NOL_STRUCTURAL)
        syntax_idx = members.index(VerificationLayer.SYNTAX)
        assert nol_idx < syntax_idx
