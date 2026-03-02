"""Tests for verify_command_safety_llm() in the security module."""

from unittest.mock import MagicMock

import pytest

from cairn.security import verify_command_safety_llm


class TestVerifyCommandSafetyLlmHappyPath:
    """Tests for commands the LLM judges as safe."""

    def test_safe_command_returns_true_and_no_reason(self):
        """LLM returns safe=true -> function returns (True, None)."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": true}'

        is_safe, reason = verify_command_safety_llm(
            command="ls -la /home",
            user_intent="list files in home directory",
            provider=provider,
        )

        assert is_safe is True
        assert reason is None

    def test_safe_command_calls_provider_with_correct_args(self):
        """Provider must be called with system prompt, user message, timeout, and zero temperature."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": true}'

        verify_command_safety_llm(
            command="df -h",
            user_intent="check disk usage",
            provider=provider,
        )

        provider.chat_json.assert_called_once()
        call_kwargs = provider.chat_json.call_args.kwargs
        assert "system" in call_kwargs
        assert "user" in call_kwargs
        assert call_kwargs["timeout_seconds"] == 10.0
        assert call_kwargs["temperature"] == 0.0

    def test_safe_command_user_message_contains_command_and_intent(self):
        """The user message sent to the provider must embed both command and user intent."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": true}'

        verify_command_safety_llm(
            command="systemctl status nginx",
            user_intent="check if nginx is running",
            provider=provider,
        )

        call_kwargs = provider.chat_json.call_args.kwargs
        user_msg = call_kwargs["user"]
        assert "systemctl status nginx" in user_msg
        assert "check if nginx is running" in user_msg


class TestVerifyCommandSafetyLlmBlocked:
    """Tests for commands the LLM judges as dangerous."""

    def test_blocked_command_returns_false_and_reason(self):
        """LLM returns safe=false with reason -> function returns (False, reason_string)."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": false, "reason": "data destruction"}'

        is_safe, reason = verify_command_safety_llm(
            command="rm -rf /home/user/important",
            user_intent="clean up files",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "data destruction"

    def test_blocked_command_reason_is_preserved_verbatim(self):
        """The exact reason string from the LLM response must be returned unchanged."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": false, "reason": "reads SSH private key"}'

        _, reason = verify_command_safety_llm(
            command="cat ~/.ssh/id_rsa",
            user_intent="show ssh key",
            provider=provider,
        )

        assert reason == "reads SSH private key"

    def test_blocked_command_with_no_reason_key_returns_none_reason(self):
        """If LLM marks unsafe but omits reason key, reason should be None."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": false}'

        is_safe, reason = verify_command_safety_llm(
            command="dd if=/dev/zero of=/dev/sda",
            user_intent="wipe disk",
            provider=provider,
        )

        assert is_safe is False
        assert reason is None


class TestVerifyCommandSafetyLlmFailClosed:
    """Tests that the function fails closed when the provider or response is unusable.

    Changed from fail-open to fail-closed as part of zero-trust hardening.
    """

    def test_provider_raises_exception_fails_closed(self):
        """If the provider throws any exception, function denies the command."""
        provider = MagicMock()
        provider.chat_json.side_effect = RuntimeError("Ollama not running")

        is_safe, reason = verify_command_safety_llm(
            command="ls -la",
            user_intent="list files",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM safety check unavailable"

    def test_provider_raises_connection_error_fails_closed(self):
        """A connection error (LLM server down) denies the command."""
        provider = MagicMock()
        provider.chat_json.side_effect = ConnectionError("Connection refused")

        is_safe, reason = verify_command_safety_llm(
            command="docker ps",
            user_intent="list containers",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM safety check unavailable"

    def test_provider_raises_timeout_fails_closed(self):
        """A timeout from the provider denies the command."""
        provider = MagicMock()
        provider.chat_json.side_effect = TimeoutError("Request timed out")

        is_safe, reason = verify_command_safety_llm(
            command="free -h",
            user_intent="check memory",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM safety check unavailable"

    def test_invalid_json_response_fails_closed(self):
        """Malformed JSON from provider denies the command, not a crash."""
        provider = MagicMock()
        provider.chat_json.return_value = "not valid json at all"

        is_safe, reason = verify_command_safety_llm(
            command="ls /tmp",
            user_intent="list temp files",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM safety check unavailable"

    def test_truncated_json_fails_closed(self):
        """Truncated/incomplete JSON from provider denies the command."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"safe": fal'

        is_safe, reason = verify_command_safety_llm(
            command="ps aux",
            user_intent="list processes",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM safety check unavailable"

    def test_missing_safe_key_defaults_to_unsafe(self):
        """Valid JSON missing the 'safe' key defaults to unsafe (fail-closed)."""
        provider = MagicMock()
        provider.chat_json.return_value = '{"status": "ok"}'

        is_safe, reason = verify_command_safety_llm(
            command="uptime",
            user_intent="check system uptime",
            provider=provider,
        )

        assert is_safe is False
        assert reason is None

    def test_empty_json_object_defaults_to_unsafe(self):
        """Empty JSON object missing 'safe' key defaults to unsafe (fail-closed)."""
        provider = MagicMock()
        provider.chat_json.return_value = "{}"

        is_safe, reason = verify_command_safety_llm(
            command="who",
            user_intent="see who is logged in",
            provider=provider,
        )

        assert is_safe is False
        assert reason is None

    def test_provider_returns_none_fails_closed(self):
        """None response from provider fails closed."""
        provider = MagicMock()
        provider.chat_json.return_value = None

        is_safe, reason = verify_command_safety_llm(
            command="cat /etc/hostname",
            user_intent="check hostname",
            provider=provider,
        )

        assert is_safe is False
        assert reason == "LLM returned empty or non-string response"
