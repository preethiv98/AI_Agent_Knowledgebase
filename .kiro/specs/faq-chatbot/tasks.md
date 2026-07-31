# Implementation Plan: FAQ Chatbot

## Overview

Build a single-file Python CLI chatbot (`faq_chatbot.py`) that loads the generated FAQ document, embeds it in a cached system prompt, and provides a multi-turn conversational interface via the Anthropic Claude API. The implementation follows incremental steps: startup validation, system prompt construction, API integration, REPL loop, history management, and testing.

## Tasks

- [x] 1. Create the chatbot module with startup validation
  - [x] 1.1 Create `faq_chatbot.py` with FAQ file loading and validation
    - Implement `load_faq(path)` function that reads `output/faq.md`
    - Handle file not found, empty/whitespace content, permission/encoding errors, and >100,000 character limit
    - Each error case prints a message and exits with code 1
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.5_

  - [x] 1.2 Implement API key loading and validation
    - Implement `load_api_key()` function using `python-dotenv`
    - Handle missing `.env` file, missing/whitespace-only `ANTHROPIC_API_KEY`
    - Each error case prints a message and exits with code 1
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [x] 1.3 Write property test for whitespace-only input rejection
    - **Property 2: Whitespace-Only Input Rejection**
    - Generate whitespace-only strings with hypothesis; verify `load_faq` and `load_api_key` reject them
    - **Validates: Requirements 1.3, 2.3**

- [x] 2. Implement system prompt construction and exit command logic
  - [x] 2.1 Implement `build_system_prompt(faq_content)` function
    - Construct a single system block with behavioral instructions, delimiter markers, and FAQ content
    - Include `cache_control: {"type": "ephemeral"}` on the block
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 9.1_

  - [x] 2.2 Implement `is_exit_command(user_input)` function
    - Strip whitespace, lowercase, check exact match against "exit" and "quit"
    - Non-exact matches (e.g., "exit now") return False
    - _Requirements: 7.3, 7.4_

  - [x] 2.3 Write property test for FAQ content preservation in system prompt
    - **Property 1: FAQ Content Preservation in System Prompt**
    - Generate random non-whitespace strings; verify they appear verbatim within delimiters in the system prompt
    - **Validates: Requirements 3.1, 3.2**

  - [x] 2.4 Write property test for exit command classification
    - **Property 3: Exit Command Classification**
    - Generate strings with random casing/whitespace padding of "exit"/"quit" plus non-matching strings; verify classification
    - **Validates: Requirements 7.3, 7.4**

- [x] 3. Implement Claude API integration
  - [x] 3.1 Define `ContextTooLongError` exception class
    - Custom exception raised when the API rejects due to context length
    - _Requirements: 4.4_

  - [x] 3.2 Implement `send_message()` function
    - Use `anthropic.Anthropic` client to call `messages.create`
    - Use model `claude-sonnet-4-5`, max_tokens=1024, timeout=30s
    - Catch `anthropic.BadRequestError` with context/token keywords and raise `ContextTooLongError`
    - Catch other API errors and re-raise as generic error
    - Handle timeout via the SDK's `timeout` parameter
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

  - [x] 3.3 Write property test for request assembly completeness
    - **Property 6: Request Assembly Completeness**
    - Generate random system prompts, histories, and messages; verify assembled request includes system with cache_control, full history, and new user message as final entry
    - **Validates: Requirements 4.2, 9.1**

- [x] 4. Implement conversation history management
  - [x] 4.1 Implement `trim_history(history, keep_latest)` function
    - Remove oldest user-assistant pairs from front of list
    - Keep `keep_latest` pairs (default 2)
    - Return trimmed history as contiguous suffix of original
    - _Requirements: 4.4, 4.5_

  - [x] 4.2 Write property test for conversation history alternation invariant
    - **Property 4: Conversation History Alternation Invariant**
    - Simulate sequences of user/assistant pairs; verify even count and alternating roles
    - **Validates: Requirements 4.1**

  - [x] 4.3 Write property test for history trimming preserves recency
    - **Property 5: History Trimming Preserves Recency**
    - Generate histories of varying lengths; trim and verify result is a suffix preserving most recent exchanges
    - **Validates: Requirements 4.4**

- [x] 5. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement the REPL loop and main entry point
  - [x] 6.1 Implement `main()` function with REPL loop
    - Call `load_faq()`, `load_api_key()`, `build_system_prompt()`
    - Create single `anthropic.Anthropic` client instance reused across turns
    - Display welcome message on successful startup
    - Loop: display `You: ` prompt, read input
    - Handle EOF (Ctrl+D) and KeyboardInterrupt (Ctrl+C) with goodbye message and exit code 0
    - Handle exit/quit commands via `is_exit_command()`
    - Skip empty/whitespace-only input without API call
    - On valid question: append to history, call `send_message()`, display response with `Assistant: ` prefix, append response to history
    - On `ContextTooLongError`: trim history, warn user, retry
    - On other API error or timeout: display error, allow user to continue
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 5.4, 5.5, 6.1, 6.2, 6.3, 6.4, 7.1, 7.2, 7.5, 8.1, 8.2, 8.3, 8.4, 9.2, 9.3_

  - [x] 6.2 Write property test for empty input not triggering API call
    - **Property 7: Empty Input Does Not Trigger API Call**
    - Generate whitespace-only strings; verify no API call is made using a mock client
    - **Validates: Requirements 6.4**

  - [x] 6.3 Write property test for system prompt immutability across turns
    - **Property 8: System Prompt Immutability Across Turns**
    - Simulate multiple turns; verify system prompt blocks are byte-identical across calls
    - **Validates: Requirements 9.3**

- [x] 7. Add entry point to pyproject.toml and wire up
  - [x] 7.1 Register chatbot entry point in `pyproject.toml`
    - Add `faq-chatbot = "faq_chatbot:main"` under `[project.scripts]`
    - _Requirements: (project setup)_

  - [x] 7.2 Write unit tests for end-to-end startup and interaction flows
    - Test startup with valid FAQ file (mocked), welcome message display
    - Test multi-turn conversation with mocked Anthropic client
    - Test error scenarios: file not found, API error, timeout, context trim
    - Test exit commands and EOF handling
    - _Requirements: 1.1, 1.2, 2.1, 5.4, 5.5, 6.1, 7.1, 7.2, 7.5_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation
- Property tests validate universal correctness properties from the design document
- Unit tests validate specific examples and edge cases
- All tests use mocked Anthropic client to avoid real API calls
- The chatbot reuses the existing `anthropic` and `python-dotenv` dependencies already in the project

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "2.2", "3.1"] },
    { "id": 1, "tasks": ["1.3", "2.1", "3.2", "4.1"] },
    { "id": 2, "tasks": ["2.3", "2.4", "3.3", "4.2", "4.3"] },
    { "id": 3, "tasks": ["6.1"] },
    { "id": 4, "tasks": ["6.2", "6.3", "7.1"] },
    { "id": 5, "tasks": ["7.2"] }
  ]
}
```
