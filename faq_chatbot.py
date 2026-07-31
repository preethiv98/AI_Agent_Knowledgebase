"""FAQ Chatbot - Interactive CLI chatbot powered by Anthropic Claude API."""

import os
import sys
from pathlib import Path

import anthropic
from dotenv import load_dotenv


MAX_FAQ_LENGTH = 100_000


class ContextTooLongError(Exception):
    """Raised when the API rejects a request due to context length."""
    pass


def load_faq(path: str = "output/faq.md") -> str:
    """Load and validate FAQ file content.

    Returns the full text content.
    Exits with non-zero code if:
      - File doesn't exist
      - File is empty/whitespace-only
      - File can't be read (permission/encoding error)
      - File exceeds 100,000 characters
    """
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        print(f"Error: FAQ file not found at '{path}'.")
        sys.exit(1)
    except (PermissionError, OSError, UnicodeDecodeError) as exc:
        print(f"Error: Could not read FAQ file at '{path}': {exc}")
        sys.exit(1)

    if not content.strip():
        print(f"Error: FAQ file at '{path}' is empty or contains only whitespace.")
        sys.exit(1)

    if len(content) > MAX_FAQ_LENGTH:
        print(
            f"Error: FAQ file at '{path}' exceeds {MAX_FAQ_LENGTH:,} characters "
            f"({len(content):,} characters). The file is too large for the system prompt."
        )
        sys.exit(1)

    return content


def load_api_key() -> str:
    """Load ANTHROPIC_API_KEY from .env in working directory.

    Returns the API key string.
    Exits with non-zero code if:
      - .env file doesn't exist
      - Key is missing or whitespace-only
    """
    env_path = Path(".env")

    if not env_path.exists():
        print("Error: .env file not found in the current directory.")
        sys.exit(1)

    load_dotenv(dotenv_path=env_path)

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    if api_key is None or api_key.strip() == "":
        print("Error: ANTHROPIC_API_KEY is not configured. Please set it in your .env file.")
        sys.exit(1)

    return api_key


def is_exit_command(user_input: str) -> bool:
    """Check if input is an exit command (exit/quit, case-insensitive, trimmed).

    Strips leading/trailing whitespace, converts to lowercase, and checks
    for an exact match against "exit" or "quit".

    Args:
        user_input: Raw user input string.

    Returns:
        True if the input is an exit command, False otherwise.
    """
    normalized = user_input.strip().lower()
    return normalized in ("exit", "quit")


def trim_history(history: list[dict], keep_latest: int = 2) -> list[dict]:
    """Remove oldest message pairs from history, keeping `keep_latest` pairs.

    A pair is one user message + one assistant message (2 entries).
    Returns the trimmed history as a contiguous suffix of the original.

    Args:
        history: Ordered list of message dicts with alternating user/assistant roles.
        keep_latest: Number of user-assistant pairs to retain (default 2).

    Returns:
        The most recent `keep_latest` pairs from the history. If the history
        already has fewer than or equal to `keep_latest` pairs, it is returned as-is.
    """
    keep_messages = keep_latest * 2
    if len(history) <= keep_messages:
        return history
    return history[-keep_messages:]


def build_system_prompt(faq_content: str) -> list[dict]:
    """Construct the system message blocks with cache_control.

    Returns a list of content blocks suitable for the `system` parameter
    of the Anthropic messages API, with cache_control on the FAQ block.

    The system prompt instructs the model to answer questions using ONLY
    the FAQ content, and to explicitly state when the FAQ does not contain
    enough information. The FAQ content is enclosed within delimiter markers
    to clearly separate instructions from reference material.

    Args:
        faq_content: The full text content of the FAQ file.

    Returns:
        A list containing a single text block dict with behavioral
        instructions, delimited FAQ content, and cache_control metadata.
    """
    return [
        {
            "type": "text",
            "text": (
                "You are a helpful FAQ assistant. Answer questions using ONLY the "
                "information in the FAQ document below. If the FAQ does not contain "
                "enough information to answer a question, say so explicitly. Do not "
                "use any knowledge outside the FAQ document.\n\n"
                "---BEGIN FAQ DOCUMENT---\n"
                f"{faq_content}\n"
                "---END FAQ DOCUMENT---"
            ),
            "cache_control": {"type": "ephemeral"},
        }
    ]


def send_message(
    client: anthropic.Anthropic,
    system: list[dict],
    history: list[dict],
    user_message: str,
    max_tokens: int = 1024,
    timeout: float = 30.0,
) -> str:
    """Send a message to Claude and return the response text.

    Raises:
      ContextTooLongError: if the API rejects due to context length
      anthropic.APIError: on other API failures
    """
    try:
        response = client.messages.create(
            model="claude-sonnet-4-5",
            system=system,
            messages=history + [{"role": "user", "content": user_message}],
            max_tokens=max_tokens,
            timeout=timeout,
        )
    except anthropic.BadRequestError as exc:
        error_message = str(exc).lower()
        if "context" in error_message or "token" in error_message:
            raise ContextTooLongError(str(exc)) from exc
        raise
    except anthropic.APIError:
        raise

    return response.content[0].text


def main() -> None:
    """Entry point: validate inputs, run REPL loop."""
    faq_content = load_faq()
    api_key = load_api_key()
    system = build_system_prompt(faq_content)
    client = anthropic.Anthropic(api_key=api_key)
    history: list[dict] = []

    print("Welcome! I'm your FAQ assistant. Ask me anything about the FAQ document.")
    print("Type 'exit' or 'quit' to end the session.\n")

    while True:
        try:
            user_input = input("You: ")
        except EOFError:
            print("\nGoodbye!")
            sys.exit(0)
        except KeyboardInterrupt:
            print("\nGoodbye!")
            sys.exit(0)

        if is_exit_command(user_input):
            print("Goodbye!")
            sys.exit(0)

        if not user_input.strip():
            continue

        # Append user message before the API call to maintain history
        history.append({"role": "user", "content": user_input})

        try:
            # Pass history without the current user message since send_message
            # appends user_message to the messages list internally
            response = send_message(client, system, history[:-1], user_input)
        except ContextTooLongError:
            # Trim history (includes the current user message), warn user, and retry
            history = trim_history(history)
            print("Warning: Conversation history was trimmed to fit within context limits.")
            try:
                response = send_message(client, system, history[:-1], user_input)
            except Exception:
                print("Error: Your question is too long for the model's context window. Please try a shorter question.")
                # Remove the user message to keep history consistent
                history.pop()
                continue
        except Exception as exc:
            print(f"Error: Could not generate a response. {exc}")
            # Remove the user message to keep history consistent
            history.pop()
            continue

        print(f"Assistant: {response}")
        history.append({"role": "assistant", "content": response})


if __name__ == "__main__":
    main()
