"""Unit tests for is_exit_command function."""

import pytest

from faq_chatbot import is_exit_command


class TestIsExitCommand:
    """Tests for exit command detection."""

    @pytest.mark.parametrize(
        "input_str",
        [
            "exit",
            "quit",
            "EXIT",
            "QUIT",
            "Exit",
            "Quit",
            "  exit  ",
            "  quit  ",
            "\texit\n",
            " QUIT ",
        ],
    )
    def test_recognized_exit_commands(self, input_str):
        """Exit/quit with any casing or surrounding whitespace should return True."""
        assert is_exit_command(input_str) is True

    @pytest.mark.parametrize(
        "input_str",
        [
            "exit now",
            "quit please",
            "exiting",
            "quitting",
            "please exit",
            "exitquit",
            "ex it",
            "hello",
            "",
            "   ",
            "exits",
            "EXIT!",
        ],
    )
    def test_non_exit_inputs(self, input_str):
        """Non-exact matches should return False."""
        assert is_exit_command(input_str) is False
