"""Tests for the Copper RPC proxy handler.

Verifies that handle_copper_proxy correctly maps copper/* method names to
HTTP calls against the Copper service, handles connection failures gracefully,
and respects the COPPER_URL environment variable.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

import cairn.rpc_handlers.copper as copper_mod
from cairn.rpc_handlers.copper import handle_copper_proxy


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal httpx response stand-in."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeClient:
    """Records every HTTP call made and returns a configurable response."""

    def __init__(self, response_payload: dict[str, Any] | None = None) -> None:
        self._response_payload = response_payload or {}
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> _FakeClient:
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False

    def _record(self, method: str, url: str, **kwargs: Any) -> _FakeResponse:
        self.calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse(self._response_payload)

    def get(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._record("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._record("POST", url, **kwargs)

    def delete(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._record("DELETE", url, **kwargs)

    def patch(self, url: str, **kwargs: Any) -> _FakeResponse:
        return self._record("PATCH", url, **kwargs)


class _RaisingClient:
    """Fake httpx.Client context manager that raises on enter."""

    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    def __enter__(self) -> _RaisingClient:
        raise self._exc

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def _patch_client(
    monkeypatch: pytest.MonkeyPatch,
    client: _FakeClient | _RaisingClient,
) -> None:
    """Replace httpx.Client in the copper module with *client*."""
    monkeypatch.setattr(copper_mod.httpx, "Client", lambda **_kw: client)
    # Bypass auto-start logic so tests only see the calls they expect
    monkeypatch.setattr(copper_mod, "_ensure_copper_running", lambda: True)


# ---------------------------------------------------------------------------
# GET endpoints
# ---------------------------------------------------------------------------


class TestGetEndpoints:
    """copper/status, copper/nodes, and copper/models map to GET requests."""

    def test_copper_status_calls_get_api_status(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """copper/status maps to GET /api/status."""
        fake = _FakeClient({"healthy": True})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/status", params={})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith("/api/status")
        assert result["copper_available"] is True
        assert result["healthy"] is True

    def test_copper_nodes_calls_get_api_nodes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """copper/nodes maps to GET /api/nodes."""
        fake = _FakeClient({"nodes": []})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/nodes", params={})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith("/api/nodes")
        assert result["copper_available"] is True

    def test_copper_models_calls_get_api_tags(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """copper/models maps to GET /api/tags."""
        fake = _FakeClient({"models": ["llama3"]})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/models", params={})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith("/api/tags")
        assert result["copper_available"] is True

    def test_copper_tasks_calls_get_api_tasks(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """copper/tasks maps to GET /api/tasks."""
        fake = _FakeClient({"tasks": []})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/tasks", params={})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith("/api/tasks")
        assert result["copper_available"] is True

    def test_copper_tasks_with_id_calls_get_api_tasks_id(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/tasks/some-uuid maps to GET /api/tasks/some-uuid."""
        task_id = "some-uuid"
        fake = _FakeClient({"id": task_id, "status": "running"})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method=f"copper/tasks/{task_id}", params={})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "GET"
        assert call["url"].endswith(f"/api/tasks/{task_id}")
        assert result["copper_available"] is True


# ---------------------------------------------------------------------------
# Timeout is passed to httpx.Client constructor
# ---------------------------------------------------------------------------


class TestTimeout:
    """All requests are constructed with a 5-second timeout."""

    def test_status_request_uses_5s_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """httpx.Client is instantiated with timeout=5.0 for copper/status."""
        captured_kwargs: dict[str, Any] = {}
        inner_fake = _FakeClient({"ok": True})

        def fake_client_factory(**kwargs: Any) -> _FakeClient:
            captured_kwargs.update(kwargs)
            return inner_fake

        monkeypatch.setattr(copper_mod.httpx, "Client", fake_client_factory)

        handle_copper_proxy(method="copper/status", params={})

        assert captured_kwargs.get("timeout") == 5.0

    def test_nodes_request_uses_5s_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """httpx.Client is instantiated with timeout=5.0 for copper/nodes."""
        captured_kwargs: dict[str, Any] = {}
        inner_fake = _FakeClient({})

        def fake_client_factory(**kwargs: Any) -> _FakeClient:
            captured_kwargs.update(kwargs)
            return inner_fake

        monkeypatch.setattr(copper_mod.httpx, "Client", fake_client_factory)

        handle_copper_proxy(method="copper/nodes", params={})

        assert captured_kwargs.get("timeout") == 5.0

    def test_models_request_uses_5s_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """httpx.Client is instantiated with timeout=5.0 for copper/models."""
        captured_kwargs: dict[str, Any] = {}
        inner_fake = _FakeClient({})

        def fake_client_factory(**kwargs: Any) -> _FakeClient:
            captured_kwargs.update(kwargs)
            return inner_fake

        monkeypatch.setattr(copper_mod.httpx, "Client", fake_client_factory)

        handle_copper_proxy(method="copper/models", params={})

        assert captured_kwargs.get("timeout") == 5.0

    def test_pull_request_uses_5s_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """httpx.Client is instantiated with timeout=5.0 for copper/pull."""
        captured_kwargs: dict[str, Any] = {}
        inner_fake = _FakeClient({})

        def fake_client_factory(**kwargs: Any) -> _FakeClient:
            captured_kwargs.update(kwargs)
            return inner_fake

        monkeypatch.setattr(copper_mod.httpx, "Client", fake_client_factory)

        handle_copper_proxy(method="copper/pull", params={"model": "llama3"})

        assert captured_kwargs.get("timeout") == 5.0


# ---------------------------------------------------------------------------
# Mutating endpoints
# ---------------------------------------------------------------------------


class TestMutatingEndpoints:
    """nodes/add, nodes/remove, nodes/update, and pull map to the right HTTP verbs."""

    def test_nodes_add_calls_post_api_nodes_with_params_as_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/nodes/add maps to POST /api/nodes with params as JSON body."""
        payload = {"name": "node1", "address": "192.168.1.10"}
        fake = _FakeClient({"created": True})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/nodes/add", params=payload)

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/api/nodes")
        assert call["json"] == payload
        assert result["copper_available"] is True

    def test_nodes_remove_calls_delete_api_nodes_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/nodes/remove maps to DELETE /api/nodes/{name}."""
        fake = _FakeClient({"deleted": True})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/nodes/remove", params={"name": "node1"})

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "DELETE"
        assert call["url"].endswith("/api/nodes/node1")
        assert result["copper_available"] is True

    def test_nodes_update_calls_patch_api_nodes_name_without_name_in_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/nodes/update maps to PATCH /api/nodes/{name} with name excluded from body."""
        fake = _FakeClient({"updated": True})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(
            method="copper/nodes/update",
            params={"name": "node1", "address": "10.0.0.5", "enabled": True},
        )

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "PATCH"
        assert call["url"].endswith("/api/nodes/node1")
        # name must NOT be in the body
        assert "name" not in call["json"]
        assert call["json"] == {"address": "10.0.0.5", "enabled": True}
        assert result["copper_available"] is True

    def test_nodes_update_does_not_mutate_caller_params(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/nodes/update leaves the caller's params dict unmodified."""
        fake = _FakeClient({})
        _patch_client(monkeypatch, fake)

        params = {"name": "node1", "address": "10.0.0.5"}
        handle_copper_proxy(method="copper/nodes/update", params=params)

        assert "name" in params  # original dict must be untouched

    def test_pull_calls_post_api_pull_with_params_as_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """copper/pull maps to POST /api/pull with params as JSON body."""
        payload = {"model": "llama3", "node": "node1"}
        fake = _FakeClient({"task_id": "abc-123"})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/pull", params=payload)

        assert len(fake.calls) == 1
        call = fake.calls[0]
        assert call["method"] == "POST"
        assert call["url"].endswith("/api/pull")
        assert call["json"] == payload
        assert result["copper_available"] is True


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    """Connection failures return copper_available: False without raising."""

    def test_connection_refused_returns_copper_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """ConnectionRefusedError returns copper_available: False without raising."""
        exc = ConnectionRefusedError("Connection refused")
        _patch_client(monkeypatch, _RaisingClient(exc))

        result = handle_copper_proxy(method="copper/status", params={})

        assert result["copper_available"] is False
        assert "error" in result

    def test_httpx_connect_error_returns_copper_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """httpx.ConnectError returns copper_available: False without raising."""
        exc = httpx.ConnectError("failed to connect")
        _patch_client(monkeypatch, _RaisingClient(exc))

        result = handle_copper_proxy(method="copper/status", params={})

        assert result["copper_available"] is False
        assert "error" in result

    def test_httpx_timeout_exception_returns_copper_unavailable(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """httpx.TimeoutException returns copper_available: False without raising."""
        exc = httpx.TimeoutException("timed out")
        _patch_client(monkeypatch, _RaisingClient(exc))

        result = handle_copper_proxy(method="copper/status", params={})

        assert result["copper_available"] is False
        assert "error" in result

    def test_no_exception_raised_on_connection_failure(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Connection failures must not propagate as exceptions to the caller."""
        exc = httpx.ConnectError("refused")
        _patch_client(monkeypatch, _RaisingClient(exc))

        # Should not raise — just return a dict
        result = handle_copper_proxy(method="copper/nodes", params={})
        assert isinstance(result, dict)

    def test_unknown_method_returns_error_with_copper_available_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unrecognised copper/ method returns a structured error, copper_available: True."""
        fake = _FakeClient({})
        _patch_client(monkeypatch, fake)

        result = handle_copper_proxy(method="copper/unknown_method", params={})

        assert result["copper_available"] is True
        assert "error" in result
        assert "copper/unknown_method" in result["error"]
        # No HTTP call should have been made
        assert len(fake.calls) == 0


# ---------------------------------------------------------------------------
# COPPER_URL environment variable
# ---------------------------------------------------------------------------


class TestCopperUrl:
    """The COPPER_URL environment variable overrides the default base URL."""

    def test_copper_url_env_var_is_used_for_requests(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Requests are sent to COPPER_URL when it is set in the environment."""
        custom_base = "http://copper.lan:19999"
        monkeypatch.setenv("COPPER_URL", custom_base)
        # Patch the module-level variable that was already resolved from the env
        monkeypatch.setattr(copper_mod, "_COPPER_BASE_URL", custom_base)

        fake = _FakeClient({"healthy": True})
        _patch_client(monkeypatch, fake)

        handle_copper_proxy(method="copper/status", params={})

        assert len(fake.calls) == 1
        assert fake.calls[0]["url"].startswith(custom_base)

    def test_default_copper_url_is_localhost_11400(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Without COPPER_URL set, requests go to http://localhost:11400."""
        monkeypatch.delenv("COPPER_URL", raising=False)
        monkeypatch.setattr(copper_mod, "_COPPER_BASE_URL", "http://localhost:11400")

        fake = _FakeClient({"ok": True})
        _patch_client(monkeypatch, fake)

        handle_copper_proxy(method="copper/status", params={})

        assert fake.calls[0]["url"].startswith("http://localhost:11400")
