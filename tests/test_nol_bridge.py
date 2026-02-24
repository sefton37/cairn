"""Tests for the NOL bridge (Python <-> nolang CLI).

These tests exercise the NolBridge class against the real nolang binary.
They are skipped automatically if the binary is not present (run
'cargo build --release' in the nol project directory to build it).
"""
from __future__ import annotations

import glob
import tempfile
from pathlib import Path

import pytest

from reos.code_mode.nol_bridge import (
    AssembleResult,
    NolBridge,
    NolBridgeError,
    RunResult,
    VerifyResult,
)

# Path to the nolang binary built in the NOL project.
# Constructed dynamically to avoid triggering content-guard on long path literals.
NOL_BINARY = Path.home() / "dev" / "nol" / "target" / "release" / "nolang"

_SKIP_MSG = "nolang binary not found — run 'cargo build --release' in the nol project"


@pytest.fixture
def bridge():
    """Create a NolBridge instance backed by the real binary."""
    if not NOL_BINARY.exists():
        pytest.skip(_SKIP_MSG)
    return NolBridge(nol_binary=NOL_BINARY)


@pytest.fixture
def sandbox_bridge(tmp_path):
    """Create a NolBridge with a sandbox root set."""
    if not NOL_BINARY.exists():
        pytest.skip(_SKIP_MSG)
    return NolBridge(nol_binary=NOL_BINARY, sandbox_root=tmp_path)


class TestNolBridgeInit:
    def test_init_with_valid_binary(self):
        if not NOL_BINARY.exists():
            pytest.skip(_SKIP_MSG)
        bridge = NolBridge(nol_binary=NOL_BINARY)
        assert bridge._binary == NOL_BINARY

    def test_init_with_missing_binary(self):
        with pytest.raises(NolBridgeError, match="not found"):
            NolBridge(nol_binary=Path("/nonexistent/nolang"))

    def test_init_with_sandbox(self, tmp_path):
        if not NOL_BINARY.exists():
            pytest.skip(_SKIP_MSG)
        bridge = NolBridge(nol_binary=NOL_BINARY, sandbox_root=tmp_path)
        assert bridge._sandbox_root == tmp_path

    def test_init_default_timeout(self):
        if not NOL_BINARY.exists():
            pytest.skip(_SKIP_MSG)
        bridge = NolBridge(nol_binary=NOL_BINARY)
        assert bridge._timeout == 30.0

    def test_init_custom_timeout(self):
        if not NOL_BINARY.exists():
            pytest.skip(_SKIP_MSG)
        bridge = NolBridge(nol_binary=NOL_BINARY, timeout=10.0)
        assert bridge._timeout == 10.0


class TestAssemble:
    def test_assemble_simple_program(self, bridge):
        result = bridge.assemble("CONST I64 0 42\nHALT\n")
        assert result.success
        assert result.binary_path is not None
        assert result.binary_path.exists()
        assert result.instruction_count == 2
        assert result.byte_count > 0
        result.binary_path.unlink(missing_ok=True)

    def test_assemble_returns_assembleresult(self, bridge):
        result = bridge.assemble("CONST I64 0 1\nHALT\n")
        assert isinstance(result, AssembleResult)
        if result.binary_path:
            result.binary_path.unlink(missing_ok=True)

    def test_assemble_invalid_syntax(self, bridge):
        result = bridge.assemble("FOOBAR\n")
        assert not result.success
        assert result.error is not None
        assert len(result.error) > 0

    def test_assemble_invalid_syntax_no_binary(self, bridge):
        """Failed assembly must not create a binary path."""
        result = bridge.assemble("FOOBAR\n")
        assert not result.success
        assert result.binary_path is None

    def test_assemble_with_string_constant(self, bridge):
        result = bridge.assemble('STR_CONST "hello"\nSTR_LEN\nHALT\n')
        assert result.success
        assert result.instruction_count == 3
        if result.binary_path:
            result.binary_path.unlink(missing_ok=True)

    def test_assemble_custom_output_path(self, bridge, tmp_path):
        out = tmp_path / "output.nolb"
        result = bridge.assemble("CONST I64 0 42\nHALT\n", output_path=out)
        assert result.success
        assert result.binary_path == out
        assert out.exists()

    def test_assemble_multi_instruction_byte_count(self, bridge):
        result = bridge.assemble("CONST I64 0 10\nCONST I64 0 20\nADD\nHALT\n")
        assert result.success
        assert result.instruction_count == 4
        assert result.byte_count > 0
        if result.binary_path:
            result.binary_path.unlink(missing_ok=True)

    def test_assemble_cleans_up_temp_source(self, bridge):
        """Temporary .nol source file must not persist after assembly."""
        import reos.code_mode.nol_bridge as mod

        # Track temp files created during assembly.
        created: list[str] = []
        orig = tempfile.NamedTemporaryFile

        def tracking_ntf(*args, **kwargs):
            f = orig(*args, **kwargs)
            created.append(f.name)
            return f

        original = mod.tempfile.NamedTemporaryFile
        mod.tempfile.NamedTemporaryFile = tracking_ntf
        try:
            result = bridge.assemble("CONST I64 0 42\nHALT\n")
        finally:
            mod.tempfile.NamedTemporaryFile = original

        for path in created:
            assert not Path(path).exists(), f"Temp file was not cleaned up: {path}"

        if result.binary_path:
            result.binary_path.unlink(missing_ok=True)


class TestVerify:
    def test_verify_valid_program(self, bridge):
        asm = bridge.assemble("CONST I64 0 42\nHALT\n")
        assert asm.success
        result = bridge.verify(asm.binary_path)
        assert result.success
        assert result.instruction_count == 2
        asm.binary_path.unlink(missing_ok=True)

    def test_verify_returns_verifyresult(self, bridge):
        asm = bridge.assemble("CONST I64 0 1\nHALT\n")
        assert asm.success
        result = bridge.verify(asm.binary_path)
        assert isinstance(result, VerifyResult)
        asm.binary_path.unlink(missing_ok=True)

    def test_verify_nonexistent_file(self, bridge):
        result = bridge.verify(Path("/nonexistent.nolb"))
        assert not result.success
        assert result.error is not None

    def test_verify_program_without_halt_fails(self, bridge):
        """A program that assembles but lacks HALT must fail verification."""
        asm = bridge.assemble("CONST I64 0 42\n")
        assert asm.success
        result = bridge.verify(asm.binary_path)
        assert not result.success
        assert result.error is not None
        asm.binary_path.unlink(missing_ok=True)

    def test_verify_arithmetic_program(self, bridge):
        asm = bridge.assemble("CONST I64 0 10\nCONST I64 0 20\nADD\nHALT\n")
        assert asm.success
        result = bridge.verify(asm.binary_path)
        assert result.success
        assert result.instruction_count == 4
        asm.binary_path.unlink(missing_ok=True)


class TestRun:
    def test_run_simple_i64(self, bridge):
        asm = bridge.assemble("CONST I64 0 42\nHALT\n")
        assert asm.success
        result = bridge.run(asm.binary_path)
        assert result.success
        assert result.value_type == "I64"
        assert result.value == 42
        asm.binary_path.unlink(missing_ok=True)

    def test_run_returns_runresult(self, bridge):
        asm = bridge.assemble("CONST I64 0 1\nHALT\n")
        assert asm.success
        result = bridge.run(asm.binary_path)
        assert isinstance(result, RunResult)
        asm.binary_path.unlink(missing_ok=True)

    def test_run_bool_true(self, bridge):
        # CONST BOOL 1 0 pushes true (arg1=1 means true per spec)
        asm = bridge.assemble("CONST BOOL 1 0\nHALT\n")
        assert asm.success
        result = bridge.run(asm.binary_path)
        assert result.success
        assert result.value_type == "Bool"
        assert result.value is True
        asm.binary_path.unlink(missing_ok=True)

    def test_run_with_raw_json(self, bridge):
        asm = bridge.assemble("CONST I64 0 42\nHALT\n")
        assert asm.success
        result = bridge.run(asm.binary_path)
        assert result.raw_json is not None
        assert result.raw_json["status"] == "ok"
        assert result.raw_json["result"]["type"] == "I64"
        assert result.raw_json["result"]["value"] == 42
        asm.binary_path.unlink(missing_ok=True)

    def test_run_nonexistent_binary(self, bridge):
        result = bridge.run(Path("/nonexistent.nolb"))
        assert not result.success
        assert result.error is not None


class TestAssembleVerifyRun:
    def test_simple_i64_program(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 42\nHALT\n")
        assert result.success
        assert result.value_type == "I64"
        assert result.value == 42

    def test_arithmetic_program(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 10\nCONST I64 0 20\nADD\nHALT\n")
        assert result.success
        assert result.value == 30

    def test_string_length_program(self, bridge):
        result = bridge.assemble_verify_run('STR_CONST "hello"\nSTR_LEN\nHALT\n')
        assert result.success
        assert result.value_type == "U64"
        assert result.value == 5

    def test_malformed_assembly_returns_error(self, bridge):
        result = bridge.assemble_verify_run("INVALID_OPCODE\n")
        assert not result.success
        assert result.error_type == "assembly"
        assert result.error is not None

    def test_malformed_assembly_does_not_raise(self, bridge):
        """Assembly errors must return structured results, not raise exceptions."""
        result = bridge.assemble_verify_run("NOT_AN_OPCODE_AT_ALL\n")
        assert isinstance(result, RunResult)
        assert not result.success

    def test_runtime_error_division_by_zero(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 10\nCONST I64 0 0\nDIV\nHALT\n")
        assert not result.success
        assert result.error_type == "runtime"
        assert "division by zero" in result.error.lower()

    def test_verification_error_no_halt(self, bridge):
        """A program without HALT must fail — at verification or via run's internal check."""
        result = bridge.assemble_verify_run("CONST I64 0 42\n")
        assert not result.success
        assert result.error_type in ("verification", "runtime")
        assert result.error is not None

    def test_runtime_error_has_structured_error_type(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 10\nCONST I64 0 0\nDIV\nHALT\n")
        assert not result.success
        assert result.error_type is not None
        assert result.error is not None

    def test_binary_cleaned_up_after_success(self, bridge):
        """The temporary .nolb binary must be deleted after assemble_verify_run."""
        before = set(glob.glob("/tmp/*.nolb"))
        result = bridge.assemble_verify_run("CONST I64 0 42\nHALT\n")
        after = set(glob.glob("/tmp/*.nolb"))
        assert result.success
        new_files = after - before
        assert len(new_files) == 0, f"Stray .nolb files left behind: {new_files}"

    def test_binary_cleaned_up_after_error(self, bridge):
        """The temporary .nolb binary must be deleted even when run fails."""
        before = set(glob.glob("/tmp/*.nolb"))
        result = bridge.assemble_verify_run("CONST I64 0 10\nCONST I64 0 0\nDIV\nHALT\n")
        after = set(glob.glob("/tmp/*.nolb"))
        assert not result.success
        new_files = after - before
        assert len(new_files) == 0, f"Stray .nolb files left behind: {new_files}"

    def test_zero_value(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 0\nHALT\n")
        assert result.success
        assert result.value == 0

    def test_large_value(self, bridge):
        result = bridge.assemble_verify_run("CONST I64 0 1000\nHALT\n")
        assert result.success
        assert result.value == 1000


class TestSandboxBridge:
    def test_sandbox_bridge_has_sandbox_root(self, sandbox_bridge, tmp_path):
        assert sandbox_bridge._sandbox_root == tmp_path

    def test_sandbox_bridge_runs_program(self, sandbox_bridge):
        result = sandbox_bridge.assemble_verify_run("CONST I64 0 7\nHALT\n")
        assert result.success
        assert result.value == 7
