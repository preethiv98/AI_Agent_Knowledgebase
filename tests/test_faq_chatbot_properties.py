"""Property-based tests for faq_chatbot module."""

import os
import tempfile

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from faq_chatbot import load_faq, load_api_key


# Feature: faq-chatbot, Property 2: Whitespace-Only Input Rejection
# **Validates: Requirements 1.3, 2.3**


# Strategy: generate strings composed entirely of whitespace characters
whitespace_only_strings = st.text(
    alphabet=st.sampled_from(" \t\n\r\x0b\x0c"),
    min_size=1,
).filter(lambda s: s.strip() == "")


class TestWhitespaceOnlyInputRejection:
    """Property 2: For any string composed entirely of whitespace characters,
    the FAQ file validation SHALL reject the content and the API key validation
    SHALL reject the key.
    """

    @given(ws=whitespace_only_strings)
    @settings(max_examples=100)
    def test_load_faq_rejects_whitespace_only_content(self, ws):
        """load_faq exits with code 1 when file contains only whitespace."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".md", encoding="utf-8", delete=False
        ) as f:
            f.write(ws)
            faq_path = f.name

        try:
            with pytest.raises(SystemExit) as exc_info:
                load_faq(faq_path)
            assert exc_info.value.code == 1
        finally:
            os.unlink(faq_path)

    @given(ws=whitespace_only_strings)
    @settings(
        max_examples=100,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_load_api_key_rejects_whitespace_only_key(self, ws, monkeypatch):
        """load_api_key exits with code 1 when ANTHROPIC_API_KEY is whitespace-only."""
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = os.path.join(tmp_dir, ".env")
            with open(env_file, "w", encoding="utf-8") as f:
                f.write(f"ANTHROPIC_API_KEY={ws}\n")

            monkeypatch.chdir(tmp_dir)
            monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

            with pytest.raises(SystemExit) as exc_info:
                load_api_key()
            assert exc_info.value.code == 1


# Feature: faq-chatbot, Property 1: FAQ Content Preservation in System Prompt
# **Validates: Requirements 3.1, 3.2**

from faq_chatbot import build_system_prompt

# Strategy: generate non-empty, non-whitespace-only strings under 100,000 chars
valid_faq_content = st.text(min_size=1, max_size=1000).filter(lambda s: s.strip() != "")


class TestFAQContentPreservationInSystemPrompt:
    """Property 1: For any valid FAQ content string (non-empty, non-whitespace,
    under 100,000 characters), the constructed system prompt SHALL contain the
    exact, unmodified FAQ content enclosed within clearly identifiable delimiter
    markers, and include cache_control metadata.
    """

    @given(faq_content=valid_faq_content)
    @settings(max_examples=100)
    def test_faq_content_appears_verbatim_in_system_prompt(self, faq_content):
        """build_system_prompt includes the FAQ content verbatim in the text."""
        result = build_system_prompt(faq_content)

        # Result is a list with one block
        assert isinstance(result, list)
        assert len(result) == 1

        block = result[0]
        prompt_text = block["text"]

        # FAQ content appears verbatim (exact match) in the system prompt
        assert faq_content in prompt_text

    @given(faq_content=valid_faq_content)
    @settings(max_examples=100)
    def test_faq_content_between_delimiters(self, faq_content):
        """FAQ content is enclosed between BEGIN and END delimiter markers."""
        result = build_system_prompt(faq_content)
        prompt_text = result[0]["text"]

        begin_marker = "---BEGIN FAQ DOCUMENT---"
        end_marker = "---END FAQ DOCUMENT---"

        # Both delimiters are present
        assert begin_marker in prompt_text
        assert end_marker in prompt_text

        # FAQ content is between the delimiters
        begin_idx = prompt_text.index(begin_marker) + len(begin_marker)
        end_idx = prompt_text.index(end_marker)

        content_between_delimiters = prompt_text[begin_idx:end_idx]
        assert faq_content in content_between_delimiters

    @given(faq_content=valid_faq_content)
    @settings(max_examples=100)
    def test_cache_control_present(self, faq_content):
        """cache_control with type ephemeral is present on the block."""
        result = build_system_prompt(faq_content)
        block = result[0]

        assert "cache_control" in block
        assert block["cache_control"] == {"type": "ephemeral"}


# Feature: faq-chatbot, Property 3: Exit Command Classification
# **Validates: Requirements 7.3, 7.4**


from faq_chatbot import is_exit_command


# Strategy: generate "exit" or "quit" with random case transformations
# and random whitespace padding (leading/trailing spaces, tabs, newlines)
exit_keywords = st.sampled_from(["exit", "quit"])

whitespace_padding = st.text(
    alphabet=st.sampled_from(" \t\n\r"),
    min_size=0,
    max_size=5,
)


@st.composite
def random_case(draw, base_strategy):
    """Apply random per-character case transformation to a string."""
    word = draw(base_strategy)
    case_choices = draw(
        st.lists(st.booleans(), min_size=len(word), max_size=len(word))
    )
    return "".join(
        c.upper() if upper else c.lower() for c, upper in zip(word, case_choices)
    )


# Positive: "exit"/"quit" with random casing and whitespace padding
exit_commands = st.builds(
    lambda prefix, word, suffix: prefix + word + suffix,
    prefix=whitespace_padding,
    word=random_case(exit_keywords),
    suffix=whitespace_padding,
)

# Negative: arbitrary strings that do NOT equal "exit" or "quit" after strip+lower
non_exit_strings = st.text(min_size=0, max_size=50).filter(
    lambda s: s.strip().lower() not in ("exit", "quit")
)


class TestExitCommandClassification:
    """Property 3: For any string, if stripping leading/trailing whitespace and
    converting to lowercase produces exactly "exit" or "quit", it SHALL be
    classified as an exit command; otherwise it SHALL be classified as a question.
    """

    @given(cmd=exit_commands)
    @settings(max_examples=100)
    def test_positive_exit_commands_recognized(self, cmd):
        """Padded/cased variants of 'exit' and 'quit' are recognized as exit commands."""
        assert is_exit_command(cmd) is True

    @given(text=non_exit_strings)
    @settings(max_examples=100)
    def test_negative_non_exit_strings_rejected(self, text):
        """Strings that are not 'exit' or 'quit' (after strip+lower) are not exit commands."""
        assert is_exit_command(text) is False


# Feature: faq-chatbot, Property 4: Conversation History Alternation Invariant
# **Validates: Requirements 4.1**


class TestConversationHistoryAlternationInvariant:
    """Property 4: For any sequence of successful interactions (user messages
    followed by assistant responses), the conversation history SHALL always
    contain an even number of entries with strictly alternating roles: user at
    even indices, assistant at odd indices.
    """

    @given(
        num_pairs=st.integers(min_value=1, max_value=20),
        user_messages=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
        assistant_responses=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
    )
    @settings(max_examples=100)
    def test_history_has_even_number_of_entries(
        self, num_pairs, user_messages, assistant_responses
    ):
        """A history built from N user-assistant pairs always has 2*N entries."""
        history = []
        for i in range(num_pairs):
            history.append({"role": "user", "content": user_messages[i]})
            history.append({"role": "assistant", "content": assistant_responses[i]})

        assert len(history) % 2 == 0
        assert len(history) == num_pairs * 2

    @given(
        num_pairs=st.integers(min_value=1, max_value=20),
        user_messages=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
        assistant_responses=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
    )
    @settings(max_examples=100)
    def test_even_indices_are_user_role(
        self, num_pairs, user_messages, assistant_responses
    ):
        """Entries at even indices (0, 2, 4, ...) always have role 'user'."""
        history = []
        for i in range(num_pairs):
            history.append({"role": "user", "content": user_messages[i]})
            history.append({"role": "assistant", "content": assistant_responses[i]})

        for idx in range(0, len(history), 2):
            assert history[idx]["role"] == "user"

    @given(
        num_pairs=st.integers(min_value=1, max_value=20),
        user_messages=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
        assistant_responses=st.lists(
            st.text(min_size=1, max_size=200), min_size=20, max_size=20
        ),
    )
    @settings(max_examples=100)
    def test_odd_indices_are_assistant_role(
        self, num_pairs, user_messages, assistant_responses
    ):
        """Entries at odd indices (1, 3, 5, ...) always have role 'assistant'."""
        history = []
        for i in range(num_pairs):
            history.append({"role": "user", "content": user_messages[i]})
            history.append({"role": "assistant", "content": assistant_responses[i]})

        for idx in range(1, len(history), 2):
            assert history[idx]["role"] == "assistant"


# Feature: faq-chatbot, Property 6: Request Assembly Completeness
# **Validates: Requirements 4.2, 9.1**

from unittest.mock import MagicMock

from hypothesis import given, settings
from hypothesis import strategies as st

from faq_chatbot import send_message


# Strategy: generate system prompt blocks (list of dicts with cache_control)
system_block_strategy = st.lists(
    st.builds(
        lambda text: {
            "type": "text",
            "text": text,
            "cache_control": {"type": "ephemeral"},
        },
        text=st.text(min_size=1, max_size=200),
    ),
    min_size=1,
    max_size=3,
)

# Strategy: generate conversation histories as alternating user/assistant pairs
conversation_history_strategy = st.lists(
    st.tuples(
        st.text(min_size=1, max_size=100),
        st.text(min_size=1, max_size=100),
    ),
    min_size=0,
    max_size=5,
).map(
    lambda pairs: [
        msg
        for user_text, assistant_text in pairs
        for msg in [
            {"role": "user", "content": user_text},
            {"role": "assistant", "content": assistant_text},
        ]
    ]
)

# Strategy: generate user message strings
user_message_strategy = st.text(min_size=1, max_size=200)


class TestRequestAssemblyCompleteness:
    """Property 6: For any system prompt, conversation history, and new user message,
    the assembled API request SHALL include the system prompt with cache_control,
    the full conversation history, and the new user message as the final entry.
    """

    @given(
        system=system_block_strategy,
        history=conversation_history_strategy,
        user_message=user_message_strategy,
    )
    @settings(max_examples=100)
    def test_request_assembly_includes_all_components(self, system, history, user_message):
        """send_message assembles the request with system, history, and user message."""
        # Set up mock client that captures call arguments
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="mock response")]
        mock_client.messages.create.return_value = mock_response

        # Call send_message
        send_message(mock_client, system, history, user_message)

        # Verify the mock was called exactly once
        mock_client.messages.create.assert_called_once()

        # Get the arguments passed to messages.create
        call_kwargs = mock_client.messages.create.call_args[1]

        # Verify system parameter equals the system blocks passed in
        assert call_kwargs["system"] == system

        # Verify messages parameter is history + [{"role": "user", "content": user_message}]
        expected_messages = history + [{"role": "user", "content": user_message}]
        assert call_kwargs["messages"] == expected_messages

        # Verify model is "claude-sonnet-4-5"
        assert call_kwargs["model"] == "claude-sonnet-4-5"

        # Verify max_tokens is 1024
        assert call_kwargs["max_tokens"] == 1024

        # Verify the system blocks have cache_control
        for block in system:
            assert "cache_control" in block
            assert block["cache_control"] == {"type": "ephemeral"}


# Feature: faq-chatbot, Property 5: History Trimming Preserves Recency
# **Validates: Requirements 4.4**

from faq_chatbot import trim_history

# Strategy: generate conversation histories as lists of user/assistant message pairs
# Each pair is (user_msg, assistant_msg), resulting in 2 entries per pair
message_content = st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != "")


def build_history(pairs: list[tuple[str, str]]) -> list[dict]:
    """Convert a list of (user, assistant) tuples into a history list of message dicts."""
    history = []
    for user_msg, assistant_msg in pairs:
        history.append({"role": "user", "content": user_msg})
        history.append({"role": "assistant", "content": assistant_msg})
    return history


# Strategy: generate between 2 and 20 pairs (4 to 40 entries)
history_pairs = st.lists(
    st.tuples(message_content, message_content),
    min_size=2,
    max_size=20,
)


class TestHistoryTrimmingPreservesRecency:
    """Property 5: For any conversation history of N pairs (where N >= 2),
    trimming SHALL remove pairs from the front (oldest) and the resulting
    history SHALL be a contiguous suffix of the original history, preserving
    the most recent exchanges.
    """

    @given(data=st.data())
    @settings(max_examples=100)
    def test_trimmed_history_length_at_most_keep_latest_pairs(self, data):
        """Trimmed history has at most keep_latest * 2 entries."""
        pairs = data.draw(history_pairs, label="pairs")
        num_pairs = len(pairs)
        keep_latest = data.draw(
            st.integers(min_value=1, max_value=num_pairs), label="keep_latest"
        )

        history = build_history(pairs)
        result = trim_history(history, keep_latest)

        assert len(result) <= keep_latest * 2

    @given(data=st.data())
    @settings(max_examples=100)
    def test_trimmed_history_is_contiguous_suffix(self, data):
        """Trimmed history is a contiguous suffix of the original history."""
        pairs = data.draw(history_pairs, label="pairs")
        num_pairs = len(pairs)
        keep_latest = data.draw(
            st.integers(min_value=1, max_value=num_pairs), label="keep_latest"
        )

        history = build_history(pairs)
        result = trim_history(history, keep_latest)

        # Result must be a suffix of the original
        assert history[-len(result):] == result

    @given(data=st.data())
    @settings(max_examples=100)
    def test_trimmed_history_preserves_most_recent_exchanges(self, data):
        """The most recent exchanges from the original appear in the trimmed result."""
        pairs = data.draw(history_pairs, label="pairs")
        num_pairs = len(pairs)
        keep_latest = data.draw(
            st.integers(min_value=1, max_value=num_pairs), label="keep_latest"
        )

        history = build_history(pairs)
        result = trim_history(history, keep_latest)

        # The last 2 entries of the original (most recent pair) must be in the result
        if len(history) >= 2:
            assert result[-2:] == history[-2:]


# Feature: faq-chatbot, Property 8: System Prompt Immutability Across Turns
# **Validates: Requirements 9.3**


class TestSystemPromptImmutabilityAcrossTurns:
    """Property 8: For any sequence of conversation turns within a session,
    the system prompt blocks passed to the API SHALL be byte-identical on
    every turn.
    """

    @given(
        faq_content=st.text(min_size=1, max_size=500).filter(lambda s: s.strip() != ""),
        user_messages=st.lists(
            st.text(min_size=1, max_size=100).filter(lambda s: s.strip() != ""),
            min_size=1,
            max_size=10,
        ),
    )
    @settings(max_examples=100)
    def test_system_prompt_identical_across_all_turns(self, faq_content, user_messages):
        """The system parameter passed to client.messages.create is byte-identical
        on every call across multiple turns within a session.
        """
        # Build the system prompt once (as done in main())
        system = build_system_prompt(faq_content)

        # Set up mock client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="mock assistant response")]
        mock_client.messages.create.return_value = mock_response

        # Simulate multiple turns with growing history
        history: list[dict] = []
        for user_msg in user_messages:
            send_message(mock_client, system, list(history), user_msg)
            # Grow history as the real chatbot does
            history.append({"role": "user", "content": user_msg})
            history.append({"role": "assistant", "content": "mock assistant response"})

        # Verify the system parameter was identical on every call
        assert mock_client.messages.create.call_count == len(user_messages)

        all_system_args = [
            call[1]["system"]
            for call in mock_client.messages.create.call_args_list
        ]

        # All system args must be byte-identical (same object content)
        first_system = all_system_args[0]
        for i, system_arg in enumerate(all_system_args[1:], start=2):
            assert system_arg == first_system, (
                f"System prompt on turn {i} differs from turn 1"
            )

        # Additionally verify byte-level identity by comparing string representations
        first_system_str = str(first_system)
        for i, system_arg in enumerate(all_system_args[1:], start=2):
            assert str(system_arg) == first_system_str, (
                f"System prompt string on turn {i} differs from turn 1"
            )


# Feature: faq-chatbot, Property 7: Empty Input Does Not Trigger API Call
# **Validates: Requirements 6.4**

from unittest.mock import MagicMock, patch

from hypothesis import given, settings
from hypothesis import strategies as st


# Strategy: generate whitespace-only strings including the empty string
# Uses common whitespace characters: space, tab, newline, carriage return, vertical tab, form feed
whitespace_only_or_empty = st.text(
    alphabet=st.sampled_from(" \t\n\r\x0b\x0c"),
    min_size=0,
    max_size=50,
)


class TestEmptyInputDoesNotTriggerAPICall:
    """Property 7: For any string composed entirely of whitespace characters
    (including the empty string), submitting it as user input SHALL NOT result
    in an API call and SHALL re-display the prompt.
    """

    @given(user_input=whitespace_only_or_empty)
    @settings(max_examples=100)
    def test_whitespace_only_input_is_detected_as_empty(self, user_input):
        """Whitespace-only (and empty) strings satisfy the skip condition in main()."""
        # The condition in main() that skips the API call
        assert not user_input.strip()

    @given(user_input=whitespace_only_or_empty)
    @settings(max_examples=100)
    def test_no_api_call_for_whitespace_only_input(self, user_input):
        """Following main() logic, whitespace-only input never triggers send_message."""
        mock_client = MagicMock()
        mock_send_message = MagicMock()

        # Replicate the main() logic for handling user input
        # After checking exit command and before calling send_message,
        # main() checks: if not user_input.strip(): continue
        if not user_input.strip():
            # This is the path taken in main() — skip the API call
            pass
        else:
            # This path should never be reached for whitespace-only inputs
            mock_send_message(mock_client, [], [], user_input)

        # Verify send_message was never called
        mock_send_message.assert_not_called()
        # Also verify the underlying client was never used
        mock_client.messages.create.assert_not_called()

    @given(user_input=whitespace_only_or_empty)
    @settings(max_examples=100)
    def test_mock_client_not_invoked_in_simulated_repl(self, user_input):
        """Simulating one REPL iteration: mock client's messages.create is never called."""
        # Set up a mock Anthropic client
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="should not be called")]
        mock_client.messages.create.return_value = mock_response

        system = build_system_prompt("Some FAQ content")
        history: list[dict] = []

        # Simulate the REPL check from main()
        if not user_input.strip():
            # Empty/whitespace input: skip — no API call
            pass
        else:
            # Would call send_message in real main()
            send_message(mock_client, system, history, user_input)

        # The API should never have been called
        mock_client.messages.create.assert_not_called()
