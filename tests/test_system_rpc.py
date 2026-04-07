"""Unit tests for system RPC handlers (src/cairn/rpc_handlers/system.py).

Each handler class tests a single handler function, verifying:
- delegation to dependencies
- parameter forwarding
- return value structure
- error paths (RpcError when play path missing, email not found, etc.)

No real DB, no real subprocess.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch, call

import pytest


# =============================================================================
# Helpers
# =============================================================================


def _mock_db() -> MagicMock:
    """Return a dummy Database object (handlers only use it as a pass-through)."""
    return MagicMock()


def _mock_store() -> MagicMock:
    """Return a mock cairn store."""
    store = MagicMock()
    conn = MagicMock()
    store._get_connection.return_value = conn
    return store


def _mock_row(**kwargs) -> MagicMock:
    """Return a MagicMock that behaves like a sqlite3 Row with given fields."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: kwargs[key]
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# =============================================================================
# handle_cairn_thunderbird_status
# =============================================================================


class TestHandleCairnThunderbirdStatus:
    """handle_cairn_thunderbird_status returns available/profile info via ThunderbirdBridge."""

    def test_returns_available_false_when_bridge_not_detected(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_thunderbird_status

        with patch("cairn.cairn.thunderbird.ThunderbirdBridge") as mock_cls:
            mock_cls.auto_detect.return_value = None
            result = handle_cairn_thunderbird_status(_mock_db())

        assert result["available"] is False
        assert "message" in result

    def test_returns_available_true_with_status_fields_when_bridge_detected(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_thunderbird_status

        bridge = MagicMock()
        bridge.config.profile_path = "/home/user/.thunderbird/abc.default"
        bridge.get_status.return_value = {
            "contacts_available": True,
            "calendar_available": True,
            "contact_count": 42,
        }

        with patch("cairn.cairn.thunderbird.ThunderbirdBridge") as mock_cls:
            mock_cls.auto_detect.return_value = bridge
            result = handle_cairn_thunderbird_status(_mock_db())

        assert result["available"] is True
        assert result["has_contacts"] is True
        assert result["has_calendar"] is True
        assert result["contact_count"] == 42
        assert "/home/user/.thunderbird/abc.default" in result["profile_path"]

    def test_defaults_status_fields_to_false_when_not_in_status_dict(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_thunderbird_status

        bridge = MagicMock()
        bridge.config.profile_path = "/some/path"
        bridge.get_status.return_value = {}

        with patch("cairn.cairn.thunderbird.ThunderbirdBridge") as mock_cls:
            mock_cls.auto_detect.return_value = bridge
            result = handle_cairn_thunderbird_status(_mock_db())

        assert result["has_contacts"] is False
        assert result["has_calendar"] is False
        assert result["contact_count"] == 0


# =============================================================================
# handle_thunderbird_check
# =============================================================================


class TestHandleThunderbirdCheck:
    """handle_thunderbird_check discovers profiles and checks stored integration state."""

    def _make_integration(self, installed=True, profiles=None):
        integration = MagicMock()
        integration.installed = installed
        integration.install_suggestion = None
        integration.profiles = profiles or []
        return integration

    def test_returns_not_configured_when_no_stored_state(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_check

        integration = self._make_integration()

        with (
            patch("cairn.cairn.thunderbird.get_thunderbird_integration_state", return_value=integration),
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None),
        ):
            result = handle_thunderbird_check(_mock_db())

        assert result["integration_state"] == "not_configured"
        assert result["installed"] is True
        assert result["profiles"] == []

    def test_returns_declined_when_stored_state_is_declined(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_check

        integration = self._make_integration()
        store = MagicMock()
        store.get_integration_state.return_value = {"state": "declined", "config": None}

        with (
            patch("cairn.cairn.thunderbird.get_thunderbird_integration_state", return_value=integration),
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_check(_mock_db())

        assert result["integration_state"] == "declined"

    def test_returns_active_when_stored_state_is_active(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_check

        integration = self._make_integration()
        store = MagicMock()
        store.get_integration_state.return_value = {
            "state": "active",
            "config": {"active_profiles": ["default"]},
        }

        with (
            patch("cairn.cairn.thunderbird.get_thunderbird_integration_state", return_value=integration),
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_check(_mock_db())

        assert result["integration_state"] == "active"
        assert result["active_profiles"] == ["default"]

    def test_serializes_profiles_and_accounts(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_check

        account = MagicMock()
        account.id = "acc1"
        account.name = "Work"
        account.email = "me@work.com"
        account.type = "imap"
        account.server = "imap.work.com"
        account.calendars = []
        account.address_books = []

        profile = MagicMock()
        profile.name = "default"
        profile.path = "/home/user/.thunderbird/default"
        profile.is_default = True
        profile.accounts = [account]

        integration = self._make_integration(profiles=[profile])

        with (
            patch("cairn.cairn.thunderbird.get_thunderbird_integration_state", return_value=integration),
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None),
        ):
            result = handle_thunderbird_check(_mock_db())

        assert len(result["profiles"]) == 1
        serialized = result["profiles"][0]
        assert serialized["name"] == "default"
        assert serialized["is_default"] is True
        assert len(serialized["accounts"]) == 1
        assert serialized["accounts"][0]["email"] == "me@work.com"


# =============================================================================
# handle_thunderbird_configure
# =============================================================================


class TestHandleThunderbirdConfigure:
    """handle_thunderbird_configure stores config via cairn store or raises RpcError."""

    def test_raises_rpc_error_when_no_play_path(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_thunderbird_configure

        with patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_thunderbird_configure(_mock_db(), active_profiles=["default"])

        assert exc_info.value.code == -32000

    def test_stores_config_and_returns_success(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_configure

        store = MagicMock()

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_configure(
                _mock_db(),
                active_profiles=["default"],
                active_accounts=["acc1"],
                all_active=True,
            )

        assert result["success"] is True
        assert result["config"]["active_profiles"] == ["default"]
        assert result["config"]["active_accounts"] == ["acc1"]
        assert result["config"]["all_active"] is True
        store.set_integration_active.assert_called_once()

    def test_active_accounts_defaults_to_empty_list(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_configure

        store = MagicMock()

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_configure(_mock_db(), active_profiles=["default"])

        assert result["config"]["active_accounts"] == []

    def test_delegates_to_set_integration_active_with_thunderbird_key(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_configure

        store = MagicMock()

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            handle_thunderbird_configure(_mock_db(), active_profiles=["p1"])

        args = store.set_integration_active.call_args
        assert args[0][0] == "thunderbird"


# =============================================================================
# handle_thunderbird_decline
# =============================================================================


class TestHandleThunderbirdDecline:
    """handle_thunderbird_decline marks integration declined or raises RpcError."""

    def test_raises_rpc_error_when_no_play_path(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_thunderbird_decline

        with patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_thunderbird_decline(_mock_db())

        assert exc_info.value.code == -32000

    def test_calls_set_integration_declined_and_returns_success(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_decline

        store = MagicMock()

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_decline(_mock_db())

        assert result == {"success": True}
        store.set_integration_declined.assert_called_once_with("thunderbird")


# =============================================================================
# handle_thunderbird_reset
# =============================================================================


class TestHandleThunderbirdReset:
    """handle_thunderbird_reset clears integration decline or raises RpcError."""

    def test_raises_rpc_error_when_no_play_path(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_thunderbird_reset

        with patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None):
            with pytest.raises(RpcError) as exc_info:
                handle_thunderbird_reset(_mock_db())

        assert exc_info.value.code == -32000

    def test_calls_clear_integration_decline_and_returns_success(self) -> None:
        from cairn.rpc_handlers.system import handle_thunderbird_reset

        store = MagicMock()

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
        ):
            result = handle_thunderbird_reset(_mock_db())

        assert result == {"success": True}
        store.clear_integration_decline.assert_called_once_with("thunderbird")


# =============================================================================
# handle_cairn_attention
# =============================================================================


class TestHandleCairnAttention:
    """handle_cairn_attention surfaces attention items or returns empty when no play path."""

    def test_returns_empty_items_when_no_play_path(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention

        with patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None):
            result = handle_cairn_attention(_mock_db())

        assert result == {"count": 0, "items": []}

    def test_returns_items_count_matching_surfaced_items(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention

        item = MagicMock()
        item.entity_type = "scene"
        item.entity_id = "scene-1"
        item.title = "Board Meeting"
        item.reason = "Upcoming"
        item.urgency = "high"
        item.calendar_start = None
        item.calendar_end = None
        item.is_recurring = False
        item.recurrence_frequency = None
        item.next_occurrence = None
        item.act_id = None
        item.scene_id = "scene-1"
        item.learned_boost = 0.0
        item.boost_reasons = []
        item.sender_name = None
        item.sender_email = None
        item.account_email = None
        item.email_date = None
        item.importance_score = None
        item.importance_reason = None
        item.email_message_id = None
        item.is_read = None

        store = MagicMock()
        store.get_integration_state.return_value = None

        surfacer = MagicMock()
        surfacer.surface_attention.return_value = [item]

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.cairn.thunderbird.ThunderbirdBridge") as mock_bridge_cls,
            patch("cairn.cairn.surfacing.CairnSurfacer", return_value=surfacer),
            patch("cairn.play_fs.list_acts", return_value=([], [])),
            patch("cairn.play_db.get_attention_priorities", return_value={}),
            patch("cairn.settings.settings") as mock_settings,
        ):
            mock_bridge_cls.auto_detect.return_value = None
            mock_settings.data_dir = MagicMock()
            mock_settings.data_dir.__truediv__ = lambda self, other: MagicMock()
            result = handle_cairn_attention(_mock_db(), hours=24, limit=5)

        assert result["count"] == 1
        assert len(result["items"]) == 1
        assert result["items"][0]["entity_id"] == "scene-1"

    def test_response_always_includes_health_warnings_key(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention

        store = MagicMock()
        store.get_integration_state.return_value = None

        surfacer = MagicMock()
        surfacer.surface_attention.return_value = []

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.cairn.thunderbird.ThunderbirdBridge") as mock_bridge_cls,
            patch("cairn.cairn.surfacing.CairnSurfacer", return_value=surfacer),
            patch("cairn.play_fs.list_acts", return_value=([], [])),
            patch("cairn.play_db.get_attention_priorities", return_value={}),
            patch("cairn.settings.settings") as mock_settings,
        ):
            mock_bridge_cls.auto_detect.return_value = None
            mock_settings.data_dir = MagicMock()
            mock_settings.data_dir.__truediv__ = lambda self, other: MagicMock()
            result = handle_cairn_attention(_mock_db())

        assert "health_warnings" in result
        assert isinstance(result["health_warnings"], list)


# =============================================================================
# handle_cairn_attention_reorder
# =============================================================================


class TestHandleCairnAttentionReorder:
    """handle_cairn_attention_reorder delegates to PrioritySignalService and returns result."""

    def test_returns_priorities_updated_and_analysis_text(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention_reorder

        signal_service = MagicMock()
        signal_service.process_reorder.return_value = {"priorities_updated": 3}

        conv_service = MagicMock()
        conv_service.get_active.return_value = None
        new_conv = MagicMock()
        new_conv.id = "conv-42"
        conv_service.start.return_value = new_conv

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value="/play/path"),
            patch("cairn.services.priority_signal_service.PrioritySignalService", return_value=signal_service),
            patch("cairn.services.conversation_service.ConversationService", return_value=conv_service),
            patch("cairn.services.priority_analysis_service.PriorityAnalysisService"),
            patch("cairn.services.priority_learning_service.PriorityLearningService"),
            patch("cairn.play_db.get_attention_priorities", return_value={}),
            patch("cairn.play_db._get_connection"),
        ):
            result = handle_cairn_attention_reorder(
                _mock_db(),
                ordered_scene_ids=["scene-1", "scene-2"],
            )

        assert "priorities_updated" in result
        assert result["priorities_updated"] == 3
        assert "analysis_text" in result
        assert "conversation_id" in result

    def test_handles_none_ordered_scene_ids_gracefully(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention_reorder

        signal_service = MagicMock()
        signal_service.process_reorder.return_value = {"priorities_updated": 0}

        conv_service = MagicMock()
        conv_service.get_active.return_value = None
        new_conv = MagicMock()
        new_conv.id = "conv-1"
        conv_service.start.return_value = new_conv

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None),
            patch("cairn.services.priority_signal_service.PrioritySignalService", return_value=signal_service),
            patch("cairn.services.conversation_service.ConversationService", return_value=conv_service),
            patch("cairn.services.priority_analysis_service.PriorityAnalysisService"),
            patch("cairn.services.priority_learning_service.PriorityLearningService"),
            patch("cairn.play_db.get_attention_priorities", return_value={}),
            patch("cairn.play_db._get_connection"),
        ):
            result = handle_cairn_attention_reorder(_mock_db(), ordered_scene_ids=None)

        assert result["priorities_updated"] == 0

    def test_converts_ordered_entities_list_of_lists_to_tuples(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_attention_reorder

        signal_service = MagicMock()
        signal_service.process_reorder.return_value = {"priorities_updated": 1}

        conv_service = MagicMock()
        conv_service.get_active.return_value = None
        new_conv = MagicMock()
        new_conv.id = "conv-2"
        conv_service.start.return_value = new_conv

        with (
            patch("cairn.rpc_handlers.system.get_current_play_path", return_value=None),
            patch("cairn.services.priority_signal_service.PrioritySignalService", return_value=signal_service),
            patch("cairn.services.conversation_service.ConversationService", return_value=conv_service),
            patch("cairn.services.priority_analysis_service.PriorityAnalysisService"),
            patch("cairn.services.priority_learning_service.PriorityLearningService"),
            patch("cairn.play_db.get_attention_priorities", return_value={}),
            patch("cairn.play_db._get_connection"),
        ):
            handle_cairn_attention_reorder(
                _mock_db(),
                ordered_entities=[["scene", "scene-1"], ["email", "email-1"]],
            )

        call_kwargs = signal_service.process_reorder.call_args[1]
        assert call_kwargs["ordered_entities"] == [("scene", "scene-1"), ("email", "email-1")]


# =============================================================================
# handle_debug_log
# =============================================================================


class TestHandleDebugLog:
    """handle_debug_log writes to stderr and returns ok."""

    def test_returns_ok_true(self) -> None:
        from cairn.rpc_handlers.system import handle_debug_log

        result = handle_debug_log(_mock_db(), msg="test message")

        assert result == {"ok": True}

    def test_writes_message_to_stderr_with_js_prefix(self, capsys) -> None:
        from cairn.rpc_handlers.system import handle_debug_log

        handle_debug_log(_mock_db(), msg="hello from frontend")

        captured = capsys.readouterr()
        assert "[JS] hello from frontend" in captured.err

    def test_empty_message_still_returns_ok(self, capsys) -> None:
        from cairn.rpc_handlers.system import handle_debug_log

        result = handle_debug_log(_mock_db(), msg="")

        assert result == {"ok": True}
        captured = capsys.readouterr()
        assert "[JS] " in captured.err


# =============================================================================
# handle_cairn_email_open
# =============================================================================


class TestHandleCairnEmailOpen:
    """handle_cairn_email_open marks email surfaced and opens Thunderbird."""

    def test_raises_rpc_error_when_email_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_cairn_email_open

        store = _mock_store()
        store._get_connection().execute.return_value.fetchone.return_value = None

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("subprocess.Popen"),
        ):
            with pytest.raises(RpcError) as exc_info:
                handle_cairn_email_open(_mock_db(), message_id=999)

        assert exc_info.value.code == -32001
        assert "not found" in exc_info.value.message

    def test_returns_success_with_message_id_when_found(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_open

        row = _mock_row(gloda_message_id=42, header_message_id="<abc@example.com>")
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("subprocess.Popen"),
        ):
            result = handle_cairn_email_open(_mock_db(), message_id=42)

        assert result["success"] is True
        assert result["message_id"] == 42

    def test_marks_email_surfaced_and_commits(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_open

        row = _mock_row(gloda_message_id=42, header_message_id="<mid@example.com>")
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("subprocess.Popen"),
        ):
            handle_cairn_email_open(_mock_db(), message_id=42)

        # Should have called execute twice: once to query, once to update
        assert conn.execute.call_count == 2
        conn.commit.assert_called_once()

    def test_opens_thunderbird_with_mid_uri_when_header_message_id_present(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_open

        row = _mock_row(gloda_message_id=7, header_message_id="<unique@host.com>")
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("subprocess.Popen") as mock_popen,
        ):
            handle_cairn_email_open(_mock_db(), message_id=7)

        mock_popen.assert_called_once()
        args = mock_popen.call_args[0][0]
        assert args[0] == "thunderbird"
        assert "mid:<unique@host.com>" in args[1]


# =============================================================================
# handle_cairn_email_dismiss
# =============================================================================


class TestHandleCairnEmailDismiss:
    """handle_cairn_email_dismiss marks email dismissed or raises RpcError."""

    def test_raises_rpc_error_when_email_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_cairn_email_dismiss

        store = _mock_store()
        store._get_connection().execute.return_value.fetchone.return_value = None

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            with pytest.raises(RpcError) as exc_info:
                handle_cairn_email_dismiss(_mock_db(), message_id=999)

        assert exc_info.value.code == -32001

    def test_returns_success_with_message_id_when_found(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_dismiss

        row = _mock_row(gloda_message_id=5)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            result = handle_cairn_email_dismiss(_mock_db(), message_id=5)

        assert result["success"] is True
        assert result["message_id"] == 5

    def test_sets_dismissed_flag_and_commits(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_dismiss

        row = _mock_row(gloda_message_id=5)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            handle_cairn_email_dismiss(_mock_db(), message_id=5)

        assert conn.execute.call_count == 2
        update_call = conn.execute.call_args_list[1]
        sql = update_call[0][0]
        assert "dismissed" in sql
        conn.commit.assert_called_once()


# =============================================================================
# handle_cairn_email_snooze
# =============================================================================


class TestHandleCairnEmailSnooze:
    """handle_cairn_email_snooze sets snoozed_until or raises RpcError."""

    def test_raises_rpc_error_when_email_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_cairn_email_snooze

        store = _mock_store()
        store._get_connection().execute.return_value.fetchone.return_value = None

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            with pytest.raises(RpcError) as exc_info:
                handle_cairn_email_snooze(_mock_db(), message_id=999)

        assert exc_info.value.code == -32001

    def test_returns_success_with_snoozed_until(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_snooze

        row = _mock_row(gloda_message_id=3)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            result = handle_cairn_email_snooze(_mock_db(), message_id=3, hours=8)

        assert result["success"] is True
        assert result["message_id"] == 3
        assert "snoozed_until" in result
        assert result["snoozed_until"] is not None

    def test_default_snooze_is_4_hours(self) -> None:
        from datetime import datetime, timedelta
        from cairn.rpc_handlers.system import handle_cairn_email_snooze

        row = _mock_row(gloda_message_id=3)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        before = datetime.now()
        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            result = handle_cairn_email_snooze(_mock_db(), message_id=3)
        after = datetime.now()

        snoozed = datetime.fromisoformat(result["snoozed_until"])
        # Should be roughly 4 hours from now
        lower = before + timedelta(hours=4)
        upper = after + timedelta(hours=4)
        assert lower <= snoozed <= upper

    def test_sets_snoozed_until_and_commits(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_snooze

        row = _mock_row(gloda_message_id=3)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            handle_cairn_email_snooze(_mock_db(), message_id=3, hours=2)

        assert conn.execute.call_count == 2
        update_call = conn.execute.call_args_list[1]
        sql = update_call[0][0]
        assert "snoozed_until" in sql
        conn.commit.assert_called_once()


# =============================================================================
# handle_cairn_email_upvote
# =============================================================================


class TestHandleCairnEmailUpvote:
    """handle_cairn_email_upvote increases importance score and creates boost rule."""

    def test_raises_rpc_error_when_email_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_cairn_email_upvote

        store = _mock_store()
        store._get_connection().execute.return_value.fetchone.return_value = None

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            with pytest.raises(RpcError) as exc_info:
                handle_cairn_email_upvote(_mock_db(), message_id=999)

        assert exc_info.value.code == -32001

    def test_returns_success_with_increased_score(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_upvote

        row = _mock_row(gloda_message_id=10, sender_email="boss@work.com", importance_score=0.5)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule"),
        ):
            result = handle_cairn_email_upvote(_mock_db(), message_id=10)

        assert result["success"] is True
        assert result["message_id"] == 10
        assert result["new_score"] == pytest.approx(0.65, abs=1e-6)

    def test_score_is_capped_at_1_0(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_upvote

        row = _mock_row(gloda_message_id=10, sender_email="x@y.com", importance_score=0.95)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule"),
        ):
            result = handle_cairn_email_upvote(_mock_db(), message_id=10)

        assert result["new_score"] == pytest.approx(1.0, abs=1e-6)

    def test_creates_positive_boost_rule_for_sender(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_upvote

        row = _mock_row(gloda_message_id=10, sender_email="vip@company.com", importance_score=0.0)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule") as mock_upsert,
        ):
            handle_cairn_email_upvote(_mock_db(), message_id=10)

        mock_upsert.assert_called_once()
        rule = mock_upsert.call_args[0][0]
        assert rule["feature_value"] == "vip@company.com"
        assert rule["boost_score"] > 0


# =============================================================================
# handle_cairn_email_downvote
# =============================================================================


class TestHandleCairnEmailDownvote:
    """handle_cairn_email_downvote decreases importance score and creates negative boost rule."""

    def test_raises_rpc_error_when_email_not_found(self) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.rpc_handlers.system import handle_cairn_email_downvote

        store = _mock_store()
        store._get_connection().execute.return_value.fetchone.return_value = None

        with patch("cairn.cairn.store.get_cairn_store", return_value=store):
            with pytest.raises(RpcError) as exc_info:
                handle_cairn_email_downvote(_mock_db(), message_id=999)

        assert exc_info.value.code == -32001

    def test_returns_success_with_decreased_score(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_downvote

        row = _mock_row(gloda_message_id=11, sender_email="spam@junk.com", importance_score=0.5)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule"),
        ):
            result = handle_cairn_email_downvote(_mock_db(), message_id=11)

        assert result["success"] is True
        assert result["message_id"] == 11
        assert result["new_score"] == pytest.approx(0.35, abs=1e-6)

    def test_score_is_floored_at_0_0(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_downvote

        row = _mock_row(gloda_message_id=11, sender_email="x@y.com", importance_score=0.05)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule"),
        ):
            result = handle_cairn_email_downvote(_mock_db(), message_id=11)

        assert result["new_score"] == pytest.approx(0.0, abs=1e-6)

    def test_creates_negative_boost_rule_for_sender(self) -> None:
        from cairn.rpc_handlers.system import handle_cairn_email_downvote

        row = _mock_row(gloda_message_id=11, sender_email="noisy@list.com", importance_score=0.3)
        store = _mock_store()
        conn = store._get_connection()
        conn.execute.return_value.fetchone.return_value = row

        with (
            patch("cairn.cairn.store.get_cairn_store", return_value=store),
            patch("cairn.play_db.upsert_boost_rule") as mock_upsert,
        ):
            handle_cairn_email_downvote(_mock_db(), message_id=11)

        mock_upsert.assert_called_once()
        rule = mock_upsert.call_args[0][0]
        assert rule["feature_value"] == "noisy@list.com"
        assert rule["boost_score"] < 0
