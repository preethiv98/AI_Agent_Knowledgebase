"""End-to-end unit tests for FAQ chatbot startup and interaction flows.

Tests cover startup validation, multi-turn conversation, error scenarios,
exit commands, and signal handling. All Anthropic API calls are mocked.
"""

import sys
from unittest.mock import MagicMock, patch

import anthropic
import pytest

from faq_chatbot import main, ContextTooLongError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_response(text: str) -> MagicMock:
    """Create a mock Anthropic API response with given text content."""
    response = MagicMock()
    content_block = MagicMock()
    content_block.text = text
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# 1. Startup with valid FAQ file — welcome message display
# ---------------------------------------------------------------------------


class TestStartupWelcomeMessage:
    """Verify the chatbot displays a welcome message on successful startup."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: Hello?\nA: World.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["exit"])
    def test_displays_welcome_message(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Welcome" in captured.out or "welcome" in captured.out
        assert "FAQ" in captured.out or "faq" in captured.out.lower()


# ---------------------------------------------------------------------------
# 2. Multi-turn conversation
# ---------------------------------------------------------------------------


class TestMultiTurnConversation:
    """Verify multi-turn conversation with mocked Anthropic client."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: What is X?\nA: X is Y.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["What is X?", "Tell me more", "exit"])
    def test_responses_displayed_with_assistant_prefix(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _make_mock_response("X is Y."),
            _make_mock_response("More details about X."),
        ]

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Assistant: X is Y." in captured.out
        assert "Assistant: More details about X." in captured.out

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: What is X?\nA: X is Y.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["Q1", "Q2", "Q3", "exit"])
    def test_history_grows_with_each_turn(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.side_effect = [
            _make_mock_response("A1"),
            _make_mock_response("A2"),
            _make_mock_response("A3"),
        ]

        with pytest.raises(SystemExit):
            main()

        # Verify calls: each successive call should include growing history
        calls = mock_client.messages.create.call_args_list
        assert len(calls) == 3

        # First call: messages should have just the user message
        first_messages = calls[0].kwargs["messages"]
        assert len(first_messages) == 1
        assert first_messages[0]["role"] == "user"
        assert first_messages[0]["content"] == "Q1"

        # Second call: should include first exchange + new user message
        second_messages = calls[1].kwargs["messages"]
        assert len(second_messages) == 3
        assert second_messages[0] == {"role": "user", "content": "Q1"}
        assert second_messages[1] == {"role": "assistant", "content": "A1"}
        assert second_messages[2] == {"role": "user", "content": "Q2"}

        # Third call: should include first two exchanges + new user message
        third_messages = calls[2].kwargs["messages"]
        assert len(third_messages) == 5
        assert third_messages[4] == {"role": "user", "content": "Q3"}


# ---------------------------------------------------------------------------
# 3. File not found
# ---------------------------------------------------------------------------


class TestFileNotFound:
    """Verify sys.exit(1) when FAQ file is not found."""

    def test_exits_with_code_1_when_faq_missing(self, tmp_path, monkeypatch, capsys):
        """Without mocking load_faq, use a dir with no faq.md."""
        monkeypatch.chdir(tmp_path)
        # Also create a .env so we don't fail there first
        (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=sk-test\n")

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "not found" in captured.out.lower()


# ---------------------------------------------------------------------------
# 4. API error — session continues
# ---------------------------------------------------------------------------


class TestApiError:
    """Verify that API errors display a message but the session continues."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: A?\nA: B.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["Hello?", "exit"])
    def test_api_error_displays_message_and_continues(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APIError(
            message="Internal server error",
            request=MagicMock(),
            body=None,
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        # Should exit with 0 via the "exit" input after the error
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Error" in captured.out or "error" in captured.out


# ---------------------------------------------------------------------------
# 5. Timeout
# ---------------------------------------------------------------------------


class TestTimeout:
    """Verify timeout-related exceptions display a timeout message."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: A?\nA: B.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["Hello?", "exit"])
    def test_timeout_displays_message_and_continues(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.messages.create.side_effect = anthropic.APITimeoutError(
            request=MagicMock(),
        )

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        # Should display some error message about the failure
        assert "Error" in captured.out or "error" in captured.out


# ---------------------------------------------------------------------------
# 6. Context trim
# ---------------------------------------------------------------------------


class TestContextTrim:
    """Verify context trimming warning when context length is exceeded."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nQ: A?\nA: B.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["Hello?", "exit"])
    def test_context_trim_shows_warning_then_succeeds(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        # First call raises BadRequestError with context/token keyword,
        # which triggers ContextTooLongError in send_message.
        # After trim, the retry succeeds.
        bad_request = anthropic.BadRequestError(
            message="prompt is too long: context window exceeded with too many tokens",
            response=MagicMock(status_code=400, headers={}, json=lambda: {}),
            body={"error": {"message": "context window exceeded with too many tokens"}},
        )
        mock_client.messages.create.side_effect = [
            bad_request,
            _make_mock_response("Trimmed response."),
        ]

        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "trimmed" in captured.out.lower() or "trim" in captured.out.lower()
        assert "Assistant: Trimmed response." in captured.out


# ---------------------------------------------------------------------------
# 7. Exit commands
# ---------------------------------------------------------------------------


class TestExitCommands:
    """Verify exit/quit commands display goodbye and exit with code 0."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nContent here.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["exit"])
    def test_exit_command_goodbye(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out or "goodbye" in captured.out

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nContent here.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=["quit"])
    def test_quit_command_goodbye(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out or "goodbye" in captured.out


# ---------------------------------------------------------------------------
# 8. EOF handling (Ctrl+D)
# ---------------------------------------------------------------------------


class TestEofHandling:
    """Verify EOF signal displays goodbye and exits with code 0."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nContent here.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=EOFError)
    def test_eof_displays_goodbye_and_exits_0(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out or "goodbye" in captured.out


# ---------------------------------------------------------------------------
# 9. Ctrl+C handling (KeyboardInterrupt)
# ---------------------------------------------------------------------------


class TestKeyboardInterruptHandling:
    """Verify Ctrl+C displays goodbye and exits with code 0."""

    @patch("faq_chatbot.load_faq", return_value="# FAQ\nContent here.")
    @patch("faq_chatbot.load_api_key", return_value="sk-ant-test-key")
    @patch("faq_chatbot.anthropic.Anthropic")
    @patch("builtins.input", side_effect=KeyboardInterrupt)
    def test_ctrl_c_displays_goodbye_and_exits_0(
        self, mock_input, mock_client_cls, mock_api_key, mock_faq, capsys
    ):
        with pytest.raises(SystemExit) as exc_info:
            main()
        assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Goodbye" in captured.out or "goodbye" in captured.out
