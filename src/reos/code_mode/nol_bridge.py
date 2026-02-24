"""Python bridge to the nolang CLI binary.

Wraps assemble, verify, and run operations via subprocess calls.
All temporary file I/O is handled internally and cleaned up automatically.
"""
from __future__ import annotations

import json
import logging
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AssembleResult:
    """Result of assembling NOL text to binary."""

    success: bool
    binary_path: Path | None = None
    instruction_count: int = 0
    byte_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class VerifyResult:
    """Result of verifying a NOL binary."""

    success: bool
    instruction_count: int = 0
    error: str | None = None


@dataclass(frozen=True)
class RunResult:
    """Result of running a NOL program."""

    success: bool
    value_type: str | None = None
    value: object = None
    raw_json: dict | None = None
    error_type: str | None = None
    error: str | None = None


class NolBridgeError(Exception):
    """Error from the NOL bridge (configuration or setup failures)."""

    pass


class NolBridge:
    """Python bridge to the nolang CLI binary.

    Wraps assemble, verify, and run operations via subprocess calls.
    All file I/O uses temporary directories that are cleaned up automatically.

    The binary is expected to be the nolang CLI built from the NOL project:
        cargo build --release  # in /home/kellogg/dev/nol/

    Typical use:
        bridge = NolBridge(nol_binary=Path("/path/to/nolang"))
        result = bridge.assemble_verify_run("CONST I64 0 42\\nHALT\\n")
        if result.success:
            print(result.value)  # 42
    """

    def __init__(
        self,
        nol_binary: Path,
        sandbox_root: Path | None = None,
        timeout: float = 30.0,
    ):
        self._binary = Path(nol_binary)
        self._sandbox_root = Path(sandbox_root) if sandbox_root else None
        self._timeout = timeout

        if not self._binary.exists():
            raise NolBridgeError(f"NOL binary not found: {self._binary}")

    def assemble(self, assembly_text: str, output_path: Path | None = None) -> AssembleResult:
        """Assemble NOL text to binary.

        Writes assembly_text to a temporary .nol file, invokes the assembler,
        and returns the path to the resulting .nolb binary.

        If output_path is None, the binary is placed alongside the temp input file.
        The caller is responsible for deleting the output binary when done.

        Args:
            assembly_text: NOL assembly source (newline-separated instructions).
            output_path: Where to write the .nolb binary. Defaults to a temp path.

        Returns:
            AssembleResult with binary_path set on success, error set on failure.
        """
        with tempfile.NamedTemporaryFile(suffix=".nol", mode="w", delete=False) as f:
            f.write(assembly_text)
            input_path = Path(f.name)

        if output_path is None:
            output_path = input_path.with_suffix(".nolb")

        try:
            result = subprocess.run(
                [str(self._binary), "assemble", str(input_path), "-o", str(output_path)],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            if result.returncode == 0:
                # The assembler writes "assembled N instructions (M bytes) -> output"
                # to stderr on success.
                instr_count = 0
                byte_count = 0
                for line in result.stderr.splitlines():
                    if line.startswith("assembled "):
                        parts = line.split()
                        try:
                            instr_count = int(parts[1])
                            paren_idx = line.index("(")
                            byte_str = line[paren_idx + 1 : line.index(" bytes")]
                            byte_count = int(byte_str)
                        except (ValueError, IndexError):
                            pass

                return AssembleResult(
                    success=True,
                    binary_path=output_path,
                    instruction_count=instr_count,
                    byte_count=byte_count,
                )
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.debug("assemble failed: %s", error_msg)
                return AssembleResult(success=False, error=error_msg)

        except subprocess.TimeoutExpired:
            logger.warning("assemble timed out after %ss", self._timeout)
            return AssembleResult(success=False, error="assembly timed out")
        finally:
            # Always clean up the temporary .nol source file.
            input_path.unlink(missing_ok=True)

    def verify(self, binary_path: Path) -> VerifyResult:
        """Verify a NOL binary program via static analysis.

        Args:
            binary_path: Path to the .nolb binary to verify.

        Returns:
            VerifyResult with instruction_count set on success, error set on failure.
        """
        try:
            result = subprocess.run(
                [str(self._binary), "verify", str(binary_path)],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            if result.returncode == 0:
                # Verify writes "OK: path (N instructions)" to stdout.
                instr_count = 0
                for line in result.stdout.splitlines():
                    if line.startswith("OK:"):
                        try:
                            paren_idx = line.index("(")
                            count_str = line[paren_idx + 1 : line.index(" instructions")]
                            instr_count = int(count_str)
                        except (ValueError, IndexError):
                            pass

                return VerifyResult(success=True, instruction_count=instr_count)
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                logger.debug("verify failed: %s", error_msg)
                return VerifyResult(success=False, error=error_msg)

        except subprocess.TimeoutExpired:
            logger.warning("verify timed out after %ss", self._timeout)
            return VerifyResult(success=False, error="verification timed out")

    def run(self, binary_path: Path) -> RunResult:
        """Run a verified NOL binary program with --json output.

        Always passes --json so the output is machine-parseable.
        Optionally passes --sandbox if sandbox_root was set at construction.

        Args:
            binary_path: Path to the .nolb binary to execute.

        Returns:
            RunResult with value and value_type on success, error details on failure.
        """
        cmd = [str(self._binary), "run", str(binary_path), "--json"]
        if self._sandbox_root:
            cmd.extend(["--sandbox", str(self._sandbox_root)])

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            stdout = result.stdout.strip()
            if not stdout:
                error_msg = result.stderr.strip() or f"exit code {result.returncode}"
                logger.debug("run produced no JSON output: %s", error_msg)
                return RunResult(success=False, error=error_msg)

            try:
                data = json.loads(stdout)
            except json.JSONDecodeError as e:
                logger.debug("run produced invalid JSON: %s", e)
                return RunResult(success=False, error=f"invalid JSON output: {e}")

            if data.get("status") == "ok":
                result_data = data.get("result", {})
                return RunResult(
                    success=True,
                    value_type=result_data.get("type"),
                    value=result_data.get("value"),
                    raw_json=data,
                )
            else:
                return RunResult(
                    success=False,
                    error_type=data.get("error_type"),
                    error=data.get("message"),
                    raw_json=data,
                )

        except subprocess.TimeoutExpired:
            logger.warning("run timed out after %ss", self._timeout)
            return RunResult(success=False, error="execution timed out")

    def compute_hashes(self, assembly_text: str) -> str:
        """Compute FUNC block hashes and return assembly with real HASH values.

        Takes assembly text with placeholder HASH instructions (e.g.
        ``HASH 0x0000 0x0000 0x0000``) and replaces them with the correct
        blake3-derived values using the ``nolang hash`` subcommand.

        If the assembly has no FUNC blocks (no HASH placeholders), the text
        is returned unchanged.  On any error, the original text is returned so
        callers can still attempt assembly and get a useful error message.

        Args:
            assembly_text: NOL assembly source, possibly containing placeholder
                           HASH instructions.

        Returns:
            Assembly text with HASH instructions filled in with correct values.
        """
        # Fast path: if no HASH placeholder present, nothing to do.
        if "HASH" not in assembly_text:
            return assembly_text

        with tempfile.NamedTemporaryFile(suffix=".nol", mode="w", delete=False) as f:
            f.write(assembly_text)
            input_path = Path(f.name)

        try:
            result = subprocess.run(
                [str(self._binary), "hash", str(input_path)],
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )

            if result.returncode != 0:
                logger.debug("hash computation failed: %s", result.stderr.strip())
                return assembly_text

            # The hash subcommand outputs one "HASH 0xXXXX 0xYYYY 0xZZZZ" line per
            # FUNC block, in order of appearance.  Replace placeholder HASH lines
            # in the original text with the computed values, one-to-one in order.
            hash_lines = [
                line.strip()
                for line in result.stdout.splitlines()
                if line.strip().startswith("HASH ")
            ]
            if not hash_lines:
                logger.debug("unexpected hash output: %r", result.stdout)
                return assembly_text

            hash_iter = iter(hash_lines)
            lines = assembly_text.splitlines()
            output_lines = []
            for line in lines:
                stripped = line.strip()
                if stripped.startswith("HASH "):
                    computed = next(hash_iter, stripped)  # fall back to original if exhausted
                    # Preserve leading whitespace from original line
                    indent = line[: len(line) - len(line.lstrip())]
                    output_lines.append(indent + computed)
                else:
                    output_lines.append(line)

            return "\n".join(output_lines) + "\n"

        except subprocess.TimeoutExpired:
            logger.warning("hash computation timed out after %ss", self._timeout)
            return assembly_text
        finally:
            input_path.unlink(missing_ok=True)

    def assemble_verify_run(self, assembly_text: str) -> RunResult:
        """Convenience: assemble, verify, and run in one call.

        This is the primary entry point for RIVA. Takes NOL assembly text,
        runs it through the full pipeline, and returns a structured result.

        Assembly and verification errors are mapped to failed RunResults with
        structured error_type fields so callers can distinguish failure modes
        without inspecting message strings.

        Args:
            assembly_text: NOL assembly source to assemble, verify, and execute.

        Returns:
            RunResult. On success, value and value_type are populated.
            On failure, error_type is one of "assembly", "verification", or "runtime".
        """
        asm_result = self.assemble(assembly_text)
        if not asm_result.success:
            return RunResult(
                success=False,
                error_type="assembly",
                error=asm_result.error,
            )

        binary_path = asm_result.binary_path
        assert binary_path is not None

        try:
            verify_result = self.verify(binary_path)
            if not verify_result.success:
                return RunResult(
                    success=False,
                    error_type="verification",
                    error=verify_result.error,
                )

            return self.run(binary_path)
        finally:
            # Clean up the temporary binary regardless of outcome.
            binary_path.unlink(missing_ok=True)
