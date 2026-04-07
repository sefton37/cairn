"""Round-trip dispatch audit for the UI RPC server.

Sends JSON-RPC requests through the real _handle_jsonrpc_request dispatcher to
verify the dispatch tables are intact, the JSON-RPC protocol is enforced, and
a representative set of handlers return valid responses.

Run with:
    PYTHONPATH="src" .venv/bin/python3 -m pytest tests/test_rpc_roundtrip_dispatch.py -x --tb=short -q --no-cov
"""

from __future__ import annotations

from typing import Any

import pytest


# ---------------------------------------------------------------------------
# Test helper
# ---------------------------------------------------------------------------


def _rpc(db: Any, *, req_id: int, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC 2.0 request through the real dispatcher and return the response."""
    import cairn.ui_rpc_server as ui

    req: dict = {"jsonrpc": "2.0", "id": req_id, "method": method}
    p = dict(params) if params else {}
    p.setdefault("__session", "test-session")
    req["params"] = p
    resp = ui._handle_jsonrpc_request(db, req)
    assert resp is not None
    return resp


# ---------------------------------------------------------------------------
# Fixture: isolated DB with a fresh singleton
# ---------------------------------------------------------------------------


@pytest.fixture
def rpc_db(isolated_db_singleton: Any) -> Any:
    """Isolated DB singleton for round-trip RPC tests.

    Composes with the conftest isolated_db_singleton fixture which swaps
    the global DB singleton to a temp file and tears it down afterwards.
    """
    from cairn.db import get_db

    return get_db()


# ===========================================================================
# Group 1 — Dispatch table audit
# ===========================================================================


class TestDispatchTableAudit:
    """Every registered handler in every lookup table must be callable."""

    def test_all_simple_handlers_are_callable(self) -> None:
        """Every entry in _SIMPLE_HANDLERS maps to a callable."""
        import cairn.ui_rpc_server as ui

        for method, handler in ui._SIMPLE_HANDLERS.items():
            assert callable(handler), f"_SIMPLE_HANDLERS[{method!r}] is not callable"

    def test_all_string_param_handlers_are_callable(self) -> None:
        """Every entry in _STRING_PARAM_HANDLERS maps to a (callable, str) pair."""
        import cairn.ui_rpc_server as ui

        for method, (handler, param_name) in ui._STRING_PARAM_HANDLERS.items():
            assert callable(handler), (
                f"_STRING_PARAM_HANDLERS[{method!r}] handler is not callable"
            )
            assert isinstance(param_name, str) and param_name, (
                f"_STRING_PARAM_HANDLERS[{method!r}] param_name is not a non-empty string"
            )

    def test_all_no_db_string_handlers_are_callable(self) -> None:
        """Every entry in _NO_DB_STRING_HANDLERS maps to a (callable, str) pair."""
        import cairn.ui_rpc_server as ui

        for method, (handler, param_name) in ui._NO_DB_STRING_HANDLERS.items():
            assert callable(handler), (
                f"_NO_DB_STRING_HANDLERS[{method!r}] handler is not callable"
            )
            assert isinstance(param_name, str) and param_name, (
                f"_NO_DB_STRING_HANDLERS[{method!r}] param_name is not a non-empty string"
            )

    def test_all_int_param_handlers_are_callable(self) -> None:
        """Every entry in _INT_PARAM_HANDLERS maps to a (callable, str) pair."""
        import cairn.ui_rpc_server as ui

        for method, (handler, param_name) in ui._INT_PARAM_HANDLERS.items():
            assert callable(handler), (
                f"_INT_PARAM_HANDLERS[{method!r}] handler is not callable"
            )
            assert isinstance(param_name, str) and param_name, (
                f"_INT_PARAM_HANDLERS[{method!r}] param_name is not a non-empty string"
            )

    def test_http_methods_all_resolve_to_callables(self) -> None:
        """Every entry in http_rpc._METHODS maps to a (callable, bool) pair."""
        import cairn.http_rpc as http_rpc

        for method, (handler, needs_db) in http_rpc._METHODS.items():
            assert callable(handler), f"_METHODS[{method!r}] handler is not callable"
            assert isinstance(needs_db, bool), (
                f"_METHODS[{method!r}] needs_db flag is not a bool"
            )

    def test_handler_count_matches_expectations(self) -> None:
        """Total methods registered in the stdio dispatcher meets minimum expected count.

        This catches accidental removals — if the number drops significantly below
        the threshold, a handler was silently deleted.
        """
        import cairn.ui_rpc_server as ui

        total = (
            len(ui._SIMPLE_HANDLERS)
            + len(ui._STRING_PARAM_HANDLERS)
            + len(ui._NO_DB_STRING_HANDLERS)
            + len(ui._INT_PARAM_HANDLERS)
        )
        # At time of writing there are >25 entries across the four tables.
        # A drop below 20 would indicate something went wrong.
        assert total >= 20, (
            f"Only {total} handlers registered across lookup tables — "
            "possible accidental deletion"
        )


# ===========================================================================
# Group 2 — Dispatch table parity
# ===========================================================================


class TestDispatchTableParity:
    """Key methods must appear in both (or only one) dispatcher as documented."""

    # Methods that must exist in BOTH the stdio and HTTP dispatchers.
    # These are drawn exclusively from the four stdio lookup tables
    # (_SIMPLE_HANDLERS, _STRING_PARAM_HANDLERS, _NO_DB_STRING_HANDLERS,
    # _INT_PARAM_HANDLERS) so they can be enumerated programmatically.
    # Inline-only stdio methods (e.g. blocks/create, ollama/set_gpu) are
    # handled by the inline if-chain and are not listed here.
    _SHARED_METHODS = [
        "play/acts/list",
        "safety/settings",
        "health/status",
        "health/findings",
        "consciousness/start",
        "consciousness/poll",
        "personas/list",
    ]

    # Auth and stdio-only methods — must NOT be in the HTTP _METHODS table.
    _STDIO_ONLY_METHODS = [
        "auth/login",
        "auth/logout",
        "auth/refresh",
        "auth/validate",
    ]

    def _all_stdio_methods(self) -> set[str]:
        """Collect all method names reachable from the stdio dispatcher."""
        import cairn.ui_rpc_server as ui

        methods: set[str] = set()
        methods.update(ui._SIMPLE_HANDLERS)
        methods.update(ui._STRING_PARAM_HANDLERS)
        methods.update(ui._NO_DB_STRING_HANDLERS)
        methods.update(ui._INT_PARAM_HANDLERS)
        # Auth methods and inline-only methods are not in the lookup tables but
        # are handled inline.  We can't enumerate them without parsing the
        # source, so we add the ones we know about explicitly.
        methods.update({"auth/login", "auth/logout", "auth/validate", "auth/refresh"})
        methods.update({"ping", "initialize", "debug/log", "tools/call"})
        return methods

    def test_shared_methods_exist_in_both_dispatchers(self) -> None:
        """A curated set of methods must be present in both stdio and HTTP dispatch."""
        import cairn.http_rpc as http_rpc

        stdio_methods = self._all_stdio_methods()
        http_methods = set(http_rpc._METHODS)

        for method in self._SHARED_METHODS:
            assert method in stdio_methods, (
                f"{method!r} missing from stdio dispatcher"
            )
            assert method in http_methods, (
                f"{method!r} missing from HTTP _METHODS dispatcher"
            )

    def test_stdio_only_methods_not_in_http_dispatcher(self) -> None:
        """Auth methods handled inline in stdio must NOT appear in HTTP _METHODS.

        The HTTP path handles auth via dedicated endpoints and Bearer tokens,
        not via JSON-RPC dispatch.
        """
        import cairn.http_rpc as http_rpc

        http_methods = set(http_rpc._METHODS)

        for method in self._STDIO_ONLY_METHODS:
            assert method not in http_methods, (
                f"{method!r} should be stdio-only but was found in HTTP _METHODS"
            )

    def test_http_methods_not_blacklisted_in_stdio(self) -> None:
        """No HTTP method should appear in the HTTP blacklist.

        http_rpc._BLACKLISTED_METHODS documents methods that deliberately exist
        only on stdio and must never be reachable via HTTP.  If any method shows
        up in both _METHODS and _BLACKLISTED_METHODS, the blacklist and registry
        are inconsistent.
        """
        import cairn.http_rpc as http_rpc

        http_methods = set(http_rpc._METHODS)
        blacklisted = set(http_rpc._BLACKLISTED_METHODS)

        overlap = http_methods & blacklisted
        assert not overlap, (
            f"Methods appear in both _METHODS and _BLACKLISTED_METHODS: {sorted(overlap)}. "
            "This is a dispatch table inconsistency — remove them from one or the other."
        )


# ===========================================================================
# Group 3 — JSON-RPC protocol
# ===========================================================================


class TestJsonRpcProtocol:
    """The dispatcher must enforce the JSON-RPC 2.0 contract."""

    def test_unknown_method_returns_method_not_found_error(self, rpc_db: Any) -> None:
        """Dispatching a completely unknown method must return a JSON-RPC error."""
        resp = _rpc(rpc_db, req_id=1, method="bogus/does_not_exist")

        assert "error" in resp, f"Expected error response, got: {resp}"
        assert "result" not in resp

    def test_notification_returns_none(self, rpc_db: Any) -> None:
        """A request with no id is a notification; the dispatcher must return None."""
        import cairn.ui_rpc_server as ui

        req: dict = {
            "jsonrpc": "2.0",
            "method": "bogus/notification",
            "params": {"__session": "test-session"},
        }
        result = ui._handle_jsonrpc_request(rpc_db, req)
        assert result is None

    def test_session_required_for_non_exempt_methods(self, rpc_db: Any) -> None:
        """Non-exempt methods called without __session must receive error -32003."""
        import cairn.ui_rpc_server as ui

        req: dict = {
            "jsonrpc": "2.0",
            "id": 42,
            "method": "play/acts/list",
            "params": {},  # no __session
        }
        resp = ui._handle_jsonrpc_request(rpc_db, req)

        assert resp is not None
        assert "error" in resp, f"Expected error for missing session, got: {resp}"
        assert resp["error"]["code"] == -32003

    def test_exempt_methods_work_without_session(self, rpc_db: Any) -> None:
        """'ping' and 'debug/log' are exempt from session enforcement."""
        import cairn.ui_rpc_server as ui

        # ping — handled inline, but not in the dispatch tables
        ping_req: dict = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {}}
        ping_resp = ui._handle_jsonrpc_request(rpc_db, ping_req)
        # ping may be handled or fall through to unknown-method; what it must NOT do
        # is return a -32003 session-required error.
        if ping_resp is not None and "error" in ping_resp:
            assert ping_resp["error"]["code"] != -32003, (
                "ping must not be rejected for missing session"
            )

        # debug/log
        log_req: dict = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "debug/log",
            "params": {"msg": "test"},  # no __session
        }
        log_resp = ui._handle_jsonrpc_request(rpc_db, log_req)
        assert log_resp is not None
        assert "error" not in log_resp or log_resp["error"]["code"] != -32003, (
            "debug/log must not be rejected for missing session"
        )

    def test_auth_validate_works_without_session(self, rpc_db: Any) -> None:
        """auth/validate is handled before the __session guard; it must not return -32003."""
        import cairn.ui_rpc_server as ui

        req: dict = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "auth/validate",
            "params": {"session_token": "fake-token-for-testing"},  # no __session key
        }
        resp = ui._handle_jsonrpc_request(rpc_db, req)

        assert resp is not None
        # The response may be an error (invalid session), but it must NOT be -32003
        if "error" in resp:
            assert resp["error"]["code"] != -32003, (
                "auth/validate must not require __session"
            )

    def test_missing_method_field_returns_error(self, rpc_db: Any) -> None:
        """A request with no 'method' key must return an error response."""
        import cairn.ui_rpc_server as ui

        req: dict = {"jsonrpc": "2.0", "id": 99, "params": {"__session": "s"}}
        resp = ui._handle_jsonrpc_request(rpc_db, req)

        # Either an error response or None (treated as unknown method).
        # If a response is returned, it must not be a clean result.
        if resp is not None:
            assert "error" in resp, (
                f"Request without method should not return a clean result: {resp}"
            )


# ===========================================================================
# Group 4 — Smoke tests (real round-trips through the dispatcher)
# ===========================================================================


class TestSimpleHandlerSmoke:
    """Send real requests through the dispatcher for methods that work with just a DB."""

    def test_play_acts_list_returns_acts_key(self, rpc_db: Any) -> None:
        """play/acts/list must return a response with an 'acts' list."""
        resp = _rpc(rpc_db, req_id=1, method="play/acts/list")

        assert "result" in resp, f"Expected result, got: {resp}"
        result = resp["result"]
        assert "acts" in result, f"Expected 'acts' key in result: {result}"
        assert isinstance(result["acts"], list)

    def test_safety_settings_returns_rate_limits(self, rpc_db: Any) -> None:
        """safety/settings must return a response containing 'rate_limits'."""
        resp = _rpc(rpc_db, req_id=2, method="safety/settings")

        assert "result" in resp, f"Expected result, got: {resp}"
        result = resp["result"]
        assert "rate_limits" in result, f"Expected 'rate_limits' key in result: {result}"

    def test_consciousness_start_returns_started_status(
        self, rpc_db: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """consciousness/start must return {'status': 'started'} when the observer is available."""
        from unittest.mock import MagicMock

        mock_observer = MagicMock()
        mock_observer.start_session.return_value = None

        mock_get_instance = MagicMock(return_value=mock_observer)
        monkeypatch.setattr(
            "cairn.cairn.consciousness_stream.ConsciousnessObserver.get_instance",
            mock_get_instance,
        )

        resp = _rpc(rpc_db, req_id=3, method="consciousness/start")

        assert "result" in resp, f"Expected result, got: {resp}"
        assert resp["result"] == {"status": "started"}
        mock_observer.start_session.assert_called_once()

    def test_ollama_set_gpu_roundtrip_stores_setting(self, rpc_db: Any) -> None:
        """ollama/set_gpu with enabled=true must return ok=True and gpu_enabled=True."""
        resp = _rpc(rpc_db, req_id=4, method="ollama/set_gpu", params={"enabled": True})

        assert "result" in resp, f"Expected result, got: {resp}"
        result = resp["result"]
        assert result.get("ok") is True
        assert result.get("gpu_enabled") is True

    def test_debug_log_returns_ok(self, rpc_db: Any) -> None:
        """debug/log must return {'ok': True} (no __session required)."""
        import cairn.ui_rpc_server as ui

        req: dict = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "debug/log",
            "params": {"msg": "smoke test"},
        }
        resp = ui._handle_jsonrpc_request(rpc_db, req)

        assert resp is not None
        assert "result" in resp, f"Expected result, got: {resp}"
        assert resp["result"] == {"ok": True}
