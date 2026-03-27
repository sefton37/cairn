"""Unit tests for CCManager (src/cairn/services/cc_manager.py).

Covers:
- _slugify() edge cases
- CCManager.list_agents()
- CCManager.create_agent()
- CCManager.delete_agent()
- CCManager.poll_events()
- CCManager.get_history()
- CCManager.send_message() (sync error paths only — process spawn is async/mocked)
- CCManager.stop_session()
- _summarize_tool_input()
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def run(coro):
    """Run a coroutine synchronously. Used because pytest-asyncio is not installed."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def isolated_play_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Point play_db at a temp dir and initialize the schema.

    Closes the connection before and after each test so tests are isolated.
    """
    import cairn.play_db as play_db

    data_dir = tmp_path / "reos-data"
    data_dir.mkdir()
    monkeypatch.setenv("TALKINGROCK_DATA_DIR", str(data_dir))

    play_db.close_connection()
    play_db.init_db()

    yield

    play_db.close_connection()


@pytest.fixture
def manager(isolated_play_db):
    """Return a fresh CCManager backed by an isolated in-memory-ish DB."""
    from cairn.services.cc_db_adapter import CairnCCDatabase
    from cairn.services.cc_manager import CCManager

    return CCManager(db=CairnCCDatabase())


# =============================================================================
# _slugify
# =============================================================================


class TestSlugify:
    """_slugify converts arbitrary names to URL-safe slugs."""

    def test_simple_name_lowercased(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("Hello") == "hello"

    def test_spaces_become_dashes(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("My Agent") == "my-agent"

    def test_special_chars_become_dashes(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("foo!bar@baz") == "foo-bar-baz"

    def test_consecutive_special_chars_collapse_to_one_dash(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("foo   bar") == "foo-bar"

    def test_leading_and_trailing_dashes_stripped(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("--hello--") == "hello"

    def test_already_slug_unchanged(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("my-agent-42") == "my-agent-42"

    def test_numbers_preserved(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("Agent 007") == "agent-007"

    def test_empty_string_returns_empty(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("") == ""

    def test_only_special_chars_returns_empty(self) -> None:
        from cairn.services.cc_manager import _slugify

        assert _slugify("!@#$%") == ""

    def test_unicode_letters_become_dashes(self) -> None:
        from cairn.services.cc_manager import _slugify

        # Non-ASCII letters are not in [a-z0-9-] so they become dashes
        result = _slugify("héllo")
        assert "-" in result or result == "h-llo"


# =============================================================================
# CCManager.list_agents
# =============================================================================


class TestListAgents:
    """list_agents returns correct data from the database."""

    def test_returns_empty_list_when_no_agents(self, manager) -> None:
        agents = manager.list_agents("alice")

        assert agents == []

    def test_returns_created_agent(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "My Agent", "a purpose")

        agents = manager.list_agents("alice")

        assert len(agents) == 1
        assert agents[0]["id"] == agent["id"]
        assert agents[0]["name"] == "My Agent"
        assert agents[0]["slug"] == "my-agent"
        assert agents[0]["purpose"] == "a purpose"

    def test_busy_is_false_when_no_process(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            manager.create_agent("alice", "Bot", "")

        agents = manager.list_agents("alice")

        assert agents[0]["busy"] is False

    def test_busy_reflects_in_memory_process_state(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"], busy=True)
        manager._procs[agent["id"]] = ap

        agents = manager.list_agents("alice")

        assert agents[0]["busy"] is True

    def test_does_not_return_agents_for_other_user(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            manager.create_agent("alice", "Alice Bot", "")

        agents = manager.list_agents("bob")

        assert agents == []

    def test_returns_multiple_agents_ordered_by_creation(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            manager.create_agent("alice", "First", "")
            manager.create_agent("alice", "Second", "")

        agents = manager.list_agents("alice")

        assert len(agents) == 2
        assert agents[0]["name"] == "First"
        assert agents[1]["name"] == "Second"


# =============================================================================
# CCManager.create_agent
# =============================================================================


class TestCreateAgent:
    """create_agent inserts a row, creates workspace, returns agent dict."""

    def test_returns_agent_dict_with_expected_keys(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "My Bot", "doing stuff")

        assert set(agent.keys()) == {"id", "name", "slug", "purpose", "cwd"}

    def test_slug_derived_from_name(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Cool Bot", "")

        assert agent["slug"] == "cool-bot"

    def test_purpose_stored_correctly(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "help with code")

        assert agent["purpose"] == "help with code"

    def test_cwd_contains_slug(self, manager, tmp_path) -> None:
        root = tmp_path / "agents"
        with patch("cairn.cc_manager.WORKSPACE_ROOT", root):
            agent = manager.create_agent("alice", "Code Bot", "")

        assert "code-bot" in agent["cwd"]

    def test_workspace_directory_created_on_disk(self, manager, tmp_path) -> None:
        root = tmp_path / "agents"
        with patch("cairn.cc_manager.WORKSPACE_ROOT", root):
            manager.create_agent("alice", "Dir Bot", "")

        assert (root / "dir-bot").is_dir()

    def test_workspace_contains_claude_md(self, manager, tmp_path) -> None:
        root = tmp_path / "agents"
        with patch("cairn.cc_manager.WORKSPACE_ROOT", root):
            manager.create_agent("alice", "Doc Bot", "for docs")

        assert (root / "doc-bot" / "CLAUDE.md").exists()

    def test_raises_rpc_error_on_duplicate_slug(self, manager, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            manager.create_agent("alice", "My Bot", "")

            with pytest.raises(RpcError) as exc_info:
                manager.create_agent("alice", "My Bot", "duplicate")

        assert exc_info.value.code == -32000
        assert "my-bot" in exc_info.value.message

    def test_raises_rpc_error_for_invalid_name(self, manager) -> None:
        from cairn.rpc_handlers import RpcError

        with pytest.raises(RpcError) as exc_info:
            manager.create_agent("alice", "!@#$", "")

        assert exc_info.value.code == -32000
        assert "Invalid" in exc_info.value.message

    def test_id_is_unique_hex_string(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            a1 = manager.create_agent("alice", "Bot One", "")
            a2 = manager.create_agent("alice", "Bot Two", "")

        assert a1["id"] != a2["id"]
        assert all(c in "0123456789abcdef" for c in a1["id"])


# =============================================================================
# CCManager.delete_agent
# =============================================================================


class TestDeleteAgent:
    """delete_agent removes the DB row and returns {ok: True}."""

    def test_returns_ok_true(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        result = manager.delete_agent(agent["id"])

        assert result == {"ok": True}

    def test_agent_no_longer_in_list_after_delete(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        manager.delete_agent(agent["id"])

        assert manager.list_agents("alice") == []

    def test_raises_rpc_error_when_not_found(self, manager) -> None:
        from cairn.rpc_handlers import RpcError

        with pytest.raises(RpcError) as exc_info:
            manager.delete_agent("nonexistent-id")

        assert exc_info.value.code == -32003

    def test_terminates_running_process(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=True)
        manager._procs[agent["id"]] = ap

        manager.delete_agent(agent["id"])

        mock_proc.terminate.assert_called_once()

    def test_does_not_error_when_process_already_exited(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = 0  # Already exited
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=False)
        manager._procs[agent["id"]] = ap

        # Should not raise
        result = manager.delete_agent(agent["id"])
        assert result == {"ok": True}
        mock_proc.terminate.assert_not_called()


# =============================================================================
# CCManager.poll_events
# =============================================================================


class TestPollEvents:
    """poll_events returns buffered events without blocking."""

    def test_returns_empty_when_no_process(self, manager) -> None:
        result = manager.poll_events("no-such-agent")

        assert result["events"] == []
        assert result["busy"] is False
        assert result["next_index"] == 0

    def test_returns_empty_when_process_has_no_events(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"])
        manager._procs[agent["id"]] = ap

        result = manager.poll_events(agent["id"])

        assert result["events"] == []
        assert result["next_index"] == 0

    def test_returns_buffered_events(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"])
        ap.events = [
            {"type": "user", "text": "hello"},
            {"type": "assistant_delta", "text": "hi"},
        ]
        manager._procs[agent["id"]] = ap

        result = manager.poll_events(agent["id"])

        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "user"
        assert result["events"][1]["type"] == "assistant_delta"
        assert result["next_index"] == 2

    def test_since_parameter_slices_events(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"])
        ap.events = [
            {"type": "user", "text": "hello"},
            {"type": "assistant_delta", "text": "hi"},
            {"type": "done"},
        ]
        manager._procs[agent["id"]] = ap

        result = manager.poll_events(agent["id"], since=1)

        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "assistant_delta"
        assert result["next_index"] == 3

    def test_busy_reflects_process_state(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"], busy=True)
        manager._procs[agent["id"]] = ap

        result = manager.poll_events(agent["id"])

        assert result["busy"] is True


# =============================================================================
# CCManager.get_history
# =============================================================================


class TestGetHistory:
    """get_history returns persisted messages in chronological order."""

    def test_returns_empty_list_when_no_history(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        history = manager.get_history(agent["id"])

        assert history == []

    def test_returns_empty_for_unknown_agent(self, manager) -> None:
        history = manager.get_history("nonexistent-id")

        assert history == []

    def test_returns_messages_in_chronological_order(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        # Persist messages directly via the internal helper
        manager._persist_history(agent["id"], "user", "first message")
        manager._persist_history(agent["id"], "assistant", "first reply")
        manager._persist_history(agent["id"], "user", "second message")

        history = manager.get_history(agent["id"])

        assert len(history) == 3
        assert history[0]["role"] == "user"
        assert history[0]["content"] == "first message"
        assert history[1]["role"] == "assistant"
        assert history[1]["content"] == "first reply"
        assert history[2]["role"] == "user"
        assert history[2]["content"] == "second message"

    def test_each_message_has_required_keys(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        manager._persist_history(agent["id"], "user", "hello")

        history = manager.get_history(agent["id"])

        assert set(history[0].keys()) == {"role", "content", "created_at"}

    def test_limit_caps_number_of_returned_messages(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        for i in range(10):
            manager._persist_history(agent["id"], "user", f"msg {i}")

        history = manager.get_history(agent["id"], limit=3)

        assert len(history) == 3

    def test_limit_returns_most_recent_messages(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        for i in range(5):
            manager._persist_history(agent["id"], "user", f"msg {i}")

        history = manager.get_history(agent["id"], limit=2)

        # limit=2 gets the 2 most recent (DESC LIMIT then reversed)
        contents = [h["content"] for h in history]
        assert "msg 3" in contents
        assert "msg 4" in contents


# =============================================================================
# CCManager.send_message (sync error paths)
# =============================================================================


class TestSendMessage:
    """send_message raises RpcError for missing agent or busy agent."""

    def test_raises_rpc_error_when_agent_not_found(self, manager) -> None:
        from cairn.rpc_handlers import RpcError

        with pytest.raises(RpcError) as exc_info:
            run(manager.send_message("nonexistent-agent-id", "hello"))

        assert exc_info.value.code == -32003

    def test_raises_rpc_error_when_agent_is_busy(self, manager, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        ap = AgentProcess(agent_id=agent["id"], busy=True)
        manager._procs[agent["id"]] = ap

        with pytest.raises(RpcError) as exc_info:
            run(manager.send_message(agent["id"], "hello"))

        assert exc_info.value.code == -32000
        assert "busy" in exc_info.value.message.lower()

    def test_accepted_response_structure(self, manager, tmp_path) -> None:
        """Successful send returns {agent_id, status: accepted}."""
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.stdout = MagicMock()
        mock_proc.stderr = MagicMock()

        async def fake_create_subprocess(*args, **kwargs):
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
            with patch("asyncio.create_task"):
                result = run(manager.send_message(agent["id"], "hello"))

        assert result["agent_id"] == agent["id"]
        assert result["status"] == "accepted"

    def test_spawn_failure_raises_rpc_error(self, manager, tmp_path) -> None:
        from cairn.rpc_handlers import RpcError

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError("no claude")):
            with pytest.raises(RpcError) as exc_info:
                run(manager.send_message(agent["id"], "hello"))

        assert exc_info.value.code == -32000
        assert "spawn" in exc_info.value.message.lower()

    def test_user_message_recorded_in_events(self, manager, tmp_path) -> None:
        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()

        async def fake_create_subprocess(*args, **kwargs):
            return mock_proc

        with patch("asyncio.create_subprocess_exec", side_effect=fake_create_subprocess):
            with patch("asyncio.create_task"):
                run(manager.send_message(agent["id"], "hello there"))

        ap = manager._procs[agent["id"]]
        assert any(e.get("type") == "user" and e.get("text") == "hello there" for e in ap.events)


# =============================================================================
# CCManager.stop_session
# =============================================================================


class TestStopSession:
    """stop_session terminates the process if running, otherwise is a no-op."""

    def test_returns_ok_when_no_process_running(self, manager) -> None:
        result = run(manager.stop_session("no-such-agent"))

        assert result == {"ok": True}

    def test_returns_ok_when_process_already_exited(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = 0  # Already done
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc)
        manager._procs[agent["id"]] = ap

        result = run(manager.stop_session(agent["id"]))

        assert result == {"ok": True}
        mock_proc.terminate.assert_not_called()

    def test_terminates_running_process(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = None  # Still running

        async def fake_wait():
            return 0

        mock_proc.wait = fake_wait
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=True)
        manager._procs[agent["id"]] = ap

        result = run(manager.stop_session(agent["id"]))

        assert result == {"ok": True}
        mock_proc.terminate.assert_called_once()

    def test_sets_busy_false_after_stop(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        async def fake_wait():
            return 0

        mock_proc.wait = fake_wait
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=True)
        manager._procs[agent["id"]] = ap

        run(manager.stop_session(agent["id"]))

        assert ap.busy is False

    def test_appends_done_event_after_stop(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        async def fake_wait():
            return 0

        mock_proc.wait = fake_wait
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=True)
        manager._procs[agent["id"]] = ap

        run(manager.stop_session(agent["id"]))

        assert any(e.get("type") == "done" for e in ap.events)

    def test_kills_process_after_timeout(self, manager, tmp_path) -> None:
        from cairn.services.cc_manager import AgentProcess

        with patch("cairn.cc_manager.WORKSPACE_ROOT", tmp_path / "agents"):
            agent = manager.create_agent("alice", "Bot", "")

        mock_proc = MagicMock()
        mock_proc.returncode = None

        # Return a pre-completed coroutine — wait_for is patched to raise before it runs
        async def fast_wait():
            return 0

        mock_proc.wait = fast_wait
        ap = AgentProcess(agent_id=agent["id"], proc=mock_proc, busy=True)
        manager._procs[agent["id"]] = ap

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            result = run(manager.stop_session(agent["id"]))

        assert result == {"ok": True}
        mock_proc.kill.assert_called_once()


# =============================================================================
# _summarize_tool_input
# =============================================================================


class TestSummarizeToolInput:
    """_summarize_tool_input extracts the relevant field for each tool type."""

    def test_bash_returns_command(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Bash", {"command": "ls -la", "other": "stuff"})

        assert result == "ls -la"

    def test_read_returns_file_path(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Read", {"file_path": "/tmp/foo.py"})

        assert result == "/tmp/foo.py"

    def test_write_returns_file_path(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Write", {"file_path": "/tmp/bar.py", "content": "..."})

        assert result == "/tmp/bar.py"

    def test_edit_returns_file_path(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Edit", {"file_path": "/tmp/baz.py"})

        assert result == "/tmp/baz.py"

    def test_glob_returns_pattern(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Glob", {"pattern": "**/*.py"})

        assert result == "**/*.py"

    def test_grep_returns_pattern_and_path(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Grep", {"pattern": "def foo", "path": "src/"})

        assert "def foo" in result
        assert "src/" in result

    def test_grep_with_only_pattern(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Grep", {"pattern": "TODO"})

        assert result == "TODO"

    def test_webfetch_returns_url(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("WebFetch", {"url": "https://example.com"})

        assert result == "https://example.com"

    def test_websearch_returns_query(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("WebSearch", {"query": "how to exit vim"})

        assert result == "how to exit vim"

    def test_unknown_tool_returns_json_dump(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("FancyTool", {"key": "value"})

        assert "key" in result
        assert "value" in result

    def test_unknown_tool_truncates_at_120_chars(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        long_input = {"key": "x" * 200}
        result = _summarize_tool_input("FancyTool", long_input)

        assert len(result) <= 120

    def test_none_input_returns_empty_string(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Bash", None)

        assert result == ""

    def test_empty_dict_returns_json_dump(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Bash", {})

        # Empty dict is falsy — returns ""
        assert result == ""

    def test_non_dict_input_returns_truncated_string(self) -> None:
        from cairn.services.cc_manager import _summarize_tool_input

        result = _summarize_tool_input("Bash", "raw string input")

        assert result == "raw string input"
