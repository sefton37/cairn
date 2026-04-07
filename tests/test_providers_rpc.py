"""Unit tests for the providers/ RPC handler functions (src/cairn/rpc_handlers/providers.py).

Each handler is tested with mocked dependencies so tests only verify that:
- the handler delegates to the right external calls
- parameters are validated and forwarded correctly
- return values have the expected shape
- RpcError is raised on invalid input or unreachable services

No real filesystem, no real subprocess, no real HTTP, no real DB.
"""

from __future__ import annotations

from unittest.mock import MagicMock, mock_open, patch

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _mock_db() -> MagicMock:
    """Return a dummy Database whose get_state/set_state methods are mocked."""
    db = MagicMock()
    db.get_state.return_value = None
    return db


def _make_health(reachable: bool = True, model_count: int = 2, error: str | None = None) -> MagicMock:
    """Return a mock Ollama health object."""
    h = MagicMock()
    h.reachable = reachable
    h.model_count = model_count
    h.error = error
    return h


def _make_model_detail(name: str) -> MagicMock:
    """Return a mock detailed model object."""
    m = MagicMock()
    m.name = name
    m.to_dict.return_value = {"name": name}
    return m


def _default_hardware() -> dict:
    return {
        "ram_gb": 8.0,
        "gpu_available": False,
        "gpu_name": None,
        "gpu_vram_gb": None,
        "gpu_type": None,
        "recommended_max_params": "8b",
    }


def _patch_ollama_status(health, detailed, hardware):
    """Context manager: patch all external calls needed by handle_ollama_status."""
    from contextlib import ExitStack

    stack = ExitStack()
    stack.enter_context(
        patch("cairn.rpc_handlers.providers.detect_system_hardware", return_value=hardware)
    )
    stack.enter_context(patch("cairn.ollama.check_ollama", return_value=health))
    stack.enter_context(
        patch("cairn.ollama.list_ollama_models_detailed", return_value=detailed)
    )
    stack.enter_context(
        patch("cairn.settings.settings", ollama_url="http://localhost:11434", ollama_model="llama3:8b")
    )
    return stack


def _patch_httpx_post(status_code: int, json_data: dict):
    """Context manager: patch httpx.Client so POST returns a fixed JSON response."""
    from contextlib import ExitStack

    stack = ExitStack()

    mock_response = MagicMock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = json_data

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response

    stack.enter_context(patch("httpx.Client", return_value=mock_client))
    return stack


# =============================================================================
# detect_system_hardware
# =============================================================================


class TestDetectSystemHardware:
    """detect_system_hardware reads /proc/meminfo and queries GPU tools."""

    def test_returns_expected_keys(self) -> None:
        from cairn.rpc_handlers.providers import detect_system_hardware

        meminfo = "MemTotal:       16384000 kB\nMemFree:        8000000 kB\n"

        with patch("builtins.open", mock_open(read_data=meminfo)):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = detect_system_hardware()

        assert "ram_gb" in result
        assert "gpu_available" in result
        assert "recommended_max_params" in result

    def test_parses_ram_from_proc_meminfo(self) -> None:
        from cairn.rpc_handlers.providers import detect_system_hardware

        # 16 GB = 16777216 kB
        meminfo = "MemTotal:       16777216 kB\n"

        with patch("builtins.open", mock_open(read_data=meminfo)):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = detect_system_hardware()

        assert result["ram_gb"] == pytest.approx(16.0, abs=0.5)

    def test_recommends_13b_for_16gb_ram(self) -> None:
        from cairn.rpc_handlers.providers import detect_system_hardware

        # Exactly 16 GB RAM, no GPU
        meminfo = "MemTotal:       16777216 kB\n"

        with patch("builtins.open", mock_open(read_data=meminfo)):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = detect_system_hardware()

        assert result["recommended_max_params"] == "13b"

    def test_recommends_3b_when_no_hardware_detected(self) -> None:
        from cairn.rpc_handlers.providers import detect_system_hardware

        with patch("builtins.open", side_effect=OSError("no proc")):
            with patch("subprocess.run", side_effect=FileNotFoundError):
                result = detect_system_hardware()

        # Conservative default with no detectable memory
        assert result["recommended_max_params"] == "3b"

    def test_detects_nvidia_gpu(self) -> None:
        from cairn.rpc_handlers.providers import detect_system_hardware

        meminfo = "MemTotal:       8192000 kB\n"
        nvidia_proc = MagicMock()
        nvidia_proc.returncode = 0
        nvidia_proc.stdout = "NVIDIA GeForce RTX 3080, 10240\n"

        def fake_run(cmd, **kwargs):
            if cmd[0] == "nvidia-smi":
                return nvidia_proc
            raise FileNotFoundError

        with patch("builtins.open", mock_open(read_data=meminfo)):
            with patch("subprocess.run", side_effect=fake_run):
                result = detect_system_hardware()

        assert result["gpu_available"] is True
        assert result["gpu_type"] == "nvidia"
        assert result["gpu_name"] == "NVIDIA GeForce RTX 3080"


# =============================================================================
# handle_ollama_status
# =============================================================================


class TestHandleOllamaStatus:
    """handle_ollama_status assembles Ollama health, model list, and hardware."""

    def test_returns_expected_keys_when_reachable(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_status

        health = _make_health(reachable=True, model_count=1)
        detailed = [_make_model_detail("llama3:8b")]
        hardware = _default_hardware()

        with _patch_ollama_status(health, detailed, hardware):
            result = handle_ollama_status(_mock_db())

        assert "url" in result
        assert "reachable" in result
        assert "available_models" in result
        assert "hardware" in result

    def test_reachable_true_includes_model_list(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_status

        health = _make_health(reachable=True, model_count=2)
        detailed = [_make_model_detail("llama3:8b"), _make_model_detail("mistral:7b")]
        hardware = _default_hardware()

        with _patch_ollama_status(health, detailed, hardware):
            result = handle_ollama_status(_mock_db())

        assert result["reachable"] is True
        assert "llama3:8b" in result["available_models"]
        assert "mistral:7b" in result["available_models"]

    def test_unreachable_returns_empty_model_list(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_status

        health = _make_health(reachable=False, model_count=0, error="connection refused")
        hardware = _default_hardware()

        with _patch_ollama_status(health, [], hardware):
            result = handle_ollama_status(_mock_db())

        assert result["reachable"] is False
        assert result["available_models"] == []

    def test_uses_stored_url_from_db_when_present(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_status

        db = _mock_db()
        db.get_state.side_effect = lambda key: (
            "http://custom:11434" if key == "ollama_url" else None
        )

        health = _make_health()
        hardware = _default_hardware()
        check_mock = MagicMock(return_value=health)

        with patch("cairn.rpc_handlers.providers.detect_system_hardware", return_value=hardware):
            with patch("cairn.ollama.check_ollama", check_mock):
                with patch("cairn.ollama.list_ollama_models_detailed", return_value=[]):
                    with patch("cairn.settings.settings", ollama_url="http://localhost:11434",
                               ollama_model="llama3:8b"):
                        handle_ollama_status(db)

        call_kwargs = check_mock.call_args
        assert call_kwargs.kwargs.get("url") == "http://custom:11434"


# =============================================================================
# handle_ollama_set_url
# =============================================================================


class TestHandleOllamaSetUrl:
    """handle_ollama_set_url validates URL format and tests the connection."""

    def test_returns_ok_true_for_reachable_url(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_url

        health = _make_health(reachable=True)
        db = _mock_db()

        with patch("cairn.ollama.check_ollama", return_value=health):
            result = handle_ollama_set_url(db, url="http://localhost:11434")

        assert result["ok"] is True
        assert result["url"] == "http://localhost:11434"

    def test_raises_rpc_error_for_non_http_url(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_ollama_set_url

        with pytest.raises(RpcError) as exc_info:
            handle_ollama_set_url(_mock_db(), url="ftp://localhost:11434")

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_ollama_unreachable(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_ollama_set_url

        health = _make_health(reachable=False, error="connection refused")

        with patch("cairn.ollama.check_ollama", return_value=health):
            with pytest.raises(RpcError) as exc_info:
                handle_ollama_set_url(_mock_db(), url="http://bad-host:11434")

        assert exc_info.value.code == -32010

    def test_stores_url_in_db_on_success(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_url

        health = _make_health(reachable=True)
        db = _mock_db()

        with patch("cairn.ollama.check_ollama", return_value=health):
            handle_ollama_set_url(db, url="http://localhost:11434")

        db.set_state.assert_called_once_with(key="ollama_url", value="http://localhost:11434")


# =============================================================================
# handle_ollama_set_model
# =============================================================================


class TestHandleOllamaSetModel:
    """handle_ollama_set_model verifies the model exists before storing it."""

    def test_returns_ok_true_when_model_found(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_model

        db = _mock_db()

        with patch("cairn.ollama.list_ollama_models", return_value=["llama3:8b", "mistral:7b"]):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_set_model(db, model="llama3:8b")

        assert result["ok"] is True
        assert result["model"] == "llama3:8b"

    def test_raises_rpc_error_when_model_not_in_list(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_ollama_set_model

        with patch("cairn.ollama.list_ollama_models", return_value=["mistral:7b"]):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                with pytest.raises(RpcError) as exc_info:
                    handle_ollama_set_model(_mock_db(), model="nonexistent:13b")

        assert exc_info.value.code == -32602

    def test_stores_model_in_db_on_success(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_model

        db = _mock_db()

        with patch("cairn.ollama.list_ollama_models", return_value=["llama3:8b"]):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                handle_ollama_set_model(db, model="llama3:8b")

        db.set_state.assert_called_once_with(key="ollama_model", value="llama3:8b")


# =============================================================================
# handle_ollama_model_info
# =============================================================================


class TestHandleOllamaModelInfo:
    """handle_ollama_model_info POSTs to /api/show and parses model details."""

    def test_returns_model_name_in_result(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_model_info

        api_response = {
            "details": {"parameter_size": "8B", "family": "llama", "families": []},
            "model_info": {"llama.context_length": 8192},
            "parameters": "",
            "template": "",
            "modelfile": "",
        }

        with _patch_httpx_post(200, api_response):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_model_info(_mock_db(), model="llama3:8b")

        assert result["model"] == "llama3:8b"
        assert "context_length" in result
        assert "capabilities" in result

    def test_returns_error_key_when_http_fails(self) -> None:
        import httpx

        from cairn.rpc_handlers.providers import handle_ollama_model_info

        with patch("httpx.Client") as mock_client_cls:
            instance = MagicMock()
            mock_client_cls.return_value.__enter__ = MagicMock(return_value=instance)
            mock_client_cls.return_value.__exit__ = MagicMock(return_value=False)
            instance.post.side_effect = httpx.ConnectError("refused")

            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_model_info(_mock_db(), model="llama3:8b")

        assert "error" in result
        assert result["model"] == "llama3:8b"

    def test_parses_context_length_from_model_info(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_model_info

        api_response = {
            "details": {"parameter_size": "8B", "family": "llama", "families": []},
            "model_info": {"llama.context_length": 32768},
            "parameters": "",
            "template": "",
            "modelfile": "",
        }

        with _patch_httpx_post(200, api_response):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_model_info(_mock_db(), model="llama3:8b")

        assert result["context_length"] == 32768


# =============================================================================
# handle_ollama_set_gpu
# =============================================================================


class TestHandleOllamaSetGpu:
    """handle_ollama_set_gpu stores 'true'/'false' and returns gpu_enabled."""

    def test_stores_true_string_when_enabled(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_gpu

        db = _mock_db()
        result = handle_ollama_set_gpu(db, enabled=True)

        db.set_state.assert_called_once_with(key="ollama_gpu_enabled", value="true")
        assert result["ok"] is True
        assert result["gpu_enabled"] is True

    def test_stores_false_string_when_disabled(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_gpu

        db = _mock_db()
        result = handle_ollama_set_gpu(db, enabled=False)

        db.set_state.assert_called_once_with(key="ollama_gpu_enabled", value="false")
        assert result["gpu_enabled"] is False


# =============================================================================
# handle_ollama_set_context
# =============================================================================


class TestHandleOllamaSetContext:
    """handle_ollama_set_context validates 512-131072 range."""

    def test_stores_valid_context_length(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_context

        db = _mock_db()
        result = handle_ollama_set_context(db, num_ctx=4096)

        db.set_state.assert_called_once_with(key="ollama_num_ctx", value="4096")
        assert result["ok"] is True
        assert result["num_ctx"] == 4096

    def test_raises_rpc_error_below_minimum(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_ollama_set_context

        with pytest.raises(RpcError) as exc_info:
            handle_ollama_set_context(_mock_db(), num_ctx=256)

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_above_maximum(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_ollama_set_context

        with pytest.raises(RpcError) as exc_info:
            handle_ollama_set_context(_mock_db(), num_ctx=200000)

        assert exc_info.value.code == -32602

    def test_accepts_boundary_values_512_and_131072(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_set_context

        db = _mock_db()
        r1 = handle_ollama_set_context(db, num_ctx=512)
        r2 = handle_ollama_set_context(db, num_ctx=131072)

        assert r1["num_ctx"] == 512
        assert r2["num_ctx"] == 131072


# =============================================================================
# handle_ollama_pull_start
# =============================================================================


class TestHandleOllamaPullStart:
    """handle_ollama_pull_start registers a pull and starts a background thread."""

    def test_returns_pull_id_and_model(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_pull_start

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_pull_start(_mock_db(), model="llama3:8b")

        assert "pull_id" in result
        assert result["model"] == "llama3:8b"

    def test_registers_pull_id_in_active_pulls(self) -> None:
        import cairn.rpc_handlers.providers as mod
        from cairn.rpc_handlers.providers import handle_ollama_pull_start

        with patch("threading.Thread") as mock_thread_cls:
            mock_thread_cls.return_value = MagicMock()
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_pull_start(_mock_db(), model="mistral:7b")

        pull_id = result["pull_id"]
        with mod._pull_lock:
            registered = pull_id in mod._active_pulls
            mod._active_pulls.pop(pull_id, None)

        assert registered is True

    def test_starts_background_thread(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_pull_start

        with patch("threading.Thread") as mock_thread_cls:
            thread_instance = MagicMock()
            mock_thread_cls.return_value = thread_instance
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_pull_start(_mock_db(), model="llama3:8b")

        thread_instance.start.assert_called_once()

        # Cleanup
        import cairn.rpc_handlers.providers as mod
        with mod._pull_lock:
            mod._active_pulls.pop(result["pull_id"], None)


# =============================================================================
# handle_ollama_pull_status
# =============================================================================


class TestHandleOllamaPullStatus:
    """handle_ollama_pull_status reads _active_pulls and cleans up completed ones."""

    def test_returns_not_found_for_unknown_pull_id(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_pull_status

        result = handle_ollama_pull_status(pull_id="does-not-exist")

        assert result["done"] is True
        assert "error" in result

    def test_returns_in_progress_state(self) -> None:
        import cairn.rpc_handlers.providers as mod
        from cairn.rpc_handlers.providers import handle_ollama_pull_status

        pull_id = "test-prog"
        with mod._pull_lock:
            mod._active_pulls[pull_id] = {
                "model": "llama3:8b",
                "status": "downloading",
                "progress": 42,
                "total": 1000,
                "completed": 420,
                "error": None,
                "done": False,
            }

        result = handle_ollama_pull_status(pull_id=pull_id)

        assert result["done"] is False
        assert result["progress"] == 42
        assert result["model"] == "llama3:8b"

        # Not yet removed (not done); cleanup manually
        with mod._pull_lock:
            mod._active_pulls.pop(pull_id, None)

    def test_removes_completed_pull_after_reporting(self) -> None:
        import cairn.rpc_handlers.providers as mod
        from cairn.rpc_handlers.providers import handle_ollama_pull_status

        pull_id = "test-done"
        with mod._pull_lock:
            mod._active_pulls[pull_id] = {
                "model": "llama3:8b",
                "status": "success",
                "progress": 100,
                "total": 1000,
                "completed": 1000,
                "error": None,
                "done": True,
            }

        result = handle_ollama_pull_status(pull_id=pull_id)

        assert result["done"] is True
        with mod._pull_lock:
            assert pull_id not in mod._active_pulls


# =============================================================================
# handle_ollama_test_connection
# =============================================================================


class TestHandleOllamaTestConnection:
    """handle_ollama_test_connection returns reachability status."""

    def test_returns_reachable_true_when_ollama_up(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_test_connection

        health = _make_health(reachable=True, model_count=3)

        with patch("cairn.ollama.check_ollama", return_value=health):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_test_connection(_mock_db())

        assert result["reachable"] is True
        assert result["model_count"] == 3

    def test_returns_reachable_false_when_ollama_down(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_test_connection

        health = _make_health(reachable=False, model_count=0, error="refused")

        with patch("cairn.ollama.check_ollama", return_value=health):
            with patch("cairn.settings.settings", ollama_url="http://localhost:11434"):
                result = handle_ollama_test_connection(_mock_db())

        assert result["reachable"] is False
        assert result["error"] == "refused"

    def test_uses_explicit_url_when_provided(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_test_connection

        health = _make_health(reachable=True)
        check_mock = MagicMock(return_value=health)

        with patch("cairn.ollama.check_ollama", check_mock):
            handle_ollama_test_connection(_mock_db(), url="http://other-host:11434")

        check_mock.assert_called_once_with(url="http://other-host:11434")


# =============================================================================
# handle_ollama_check_installed
# =============================================================================


class TestHandleOllamaCheckInstalled:
    """handle_ollama_check_installed delegates to providers module."""

    def test_returns_installed_true_when_ollama_found(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_check_installed

        with patch("cairn.providers.check_ollama_installed", return_value=True):
            with patch("cairn.providers.get_ollama_install_command", return_value="curl ..."):
                result = handle_ollama_check_installed(_mock_db())

        assert result["installed"] is True

    def test_returns_install_command_when_not_installed(self) -> None:
        from cairn.rpc_handlers.providers import handle_ollama_check_installed

        with patch("cairn.providers.check_ollama_installed", return_value=False):
            with patch("cairn.providers.get_ollama_install_command", return_value="curl -fsSL ..."):
                result = handle_ollama_check_installed(_mock_db())

        assert result["installed"] is False
        assert result["install_command"] == "curl -fsSL ..."


# =============================================================================
# handle_providers_list
# =============================================================================


class TestHandleProvidersList:
    """handle_providers_list returns current provider and available providers."""

    def _make_provider(self, pid: str, name: str, local: bool, needs_key: bool) -> MagicMock:
        p = MagicMock()
        p.id = pid
        p.name = name
        p.description = f"{name} description"
        p.is_local = local
        p.requires_api_key = needs_key
        return p

    def test_returns_expected_structure(self) -> None:
        from cairn.rpc_handlers.providers import handle_providers_list

        provider = self._make_provider("ollama", "Ollama", local=True, needs_key=False)

        with patch("cairn.providers.get_current_provider_type", return_value="ollama"):
            with patch("cairn.providers.list_providers", return_value=[provider]):
                with patch("cairn.providers.check_keyring_available", return_value=True):
                    result = handle_providers_list(_mock_db())

        assert "current_provider" in result
        assert "available_providers" in result
        assert "keyring_available" in result

    def test_includes_key_status_for_providers_requiring_one(self) -> None:
        from cairn.rpc_handlers.providers import handle_providers_list

        provider = self._make_provider("openai", "OpenAI", local=False, needs_key=True)

        with patch("cairn.providers.get_current_provider_type", return_value="ollama"):
            with patch("cairn.providers.list_providers", return_value=[provider]):
                with patch("cairn.providers.check_keyring_available", return_value=True):
                    with patch("cairn.providers.has_api_key", return_value=True):
                        result = handle_providers_list(_mock_db())

        p = result["available_providers"][0]
        assert p["has_api_key"] is True

    def test_has_api_key_is_none_for_local_providers(self) -> None:
        from cairn.rpc_handlers.providers import handle_providers_list

        provider = self._make_provider("ollama", "Ollama", local=True, needs_key=False)

        with patch("cairn.providers.get_current_provider_type", return_value="ollama"):
            with patch("cairn.providers.list_providers", return_value=[provider]):
                with patch("cairn.providers.check_keyring_available", return_value=True):
                    result = handle_providers_list(_mock_db())

        p = result["available_providers"][0]
        assert p["has_api_key"] is None


# =============================================================================
# handle_providers_set
# =============================================================================


class TestHandleProvidersSet:
    """handle_providers_set validates provider and stores the selection."""

    def test_returns_ok_true_for_known_provider(self) -> None:
        from cairn.rpc_handlers.providers import handle_providers_set

        provider_info = MagicMock()

        with patch("cairn.providers.get_provider_info", return_value=provider_info):
            with patch("cairn.providers.set_provider_type"):
                result = handle_providers_set(_mock_db(), provider="ollama")

        assert result["ok"] is True
        assert result["provider"] == "ollama"

    def test_raises_rpc_error_for_unknown_provider(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_providers_set

        with patch("cairn.providers.get_provider_info", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_providers_set(_mock_db(), provider="nonexistent")

        assert exc_info.value.code == -32602

    def test_raises_rpc_error_when_set_provider_raises_llm_error(self) -> None:
        from cairn.providers import LLMError
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.providers import handle_providers_set

        provider_info = MagicMock()

        with patch("cairn.providers.get_provider_info", return_value=provider_info):
            with patch("cairn.providers.set_provider_type", side_effect=LLMError("bad config")):
                with pytest.raises(RpcError) as exc_info:
                    handle_providers_set(_mock_db(), provider="ollama")

        assert exc_info.value.code == -32010
