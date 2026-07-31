# Requirements Document

## Introduction

A Python CLI chatbot that loads the generated FAQ document (`output/faq.md`), includes its full content in a system prompt, and uses the Anthropic Claude API to answer user questions in a multi-turn terminal conversation. The chatbot restricts answers to information found in the FAQ, maintains conversation history within a session, and provides a simple interactive prompt with graceful exit commands.

## Glossary

- **Chatbot**: The Python CLI application that reads the FAQ file, sends user questions to the Claude API, and displays answers in the terminal.
- **FAQ_File**: The markdown file located at `output/faq.md` containing generated question-answer pairs.
- **System_Prompt**: The initial prompt sent to the Claude API that includes the full FAQ content and instructions for answering behavior.
- **Conversation_History**: The ordered list of user messages and assistant responses maintained within a single session to support follow-up questions.
- **Session**: A single run of the Chatbot from startup to the user issuing an exit command.
- **API_Key**: The Anthropic API key loaded from the `.env` file via the `ANTHROPIC_API_KEY` environment variable.
- **Prompt_Cache**: Anthropic's server-side caching mechanism that avoids re-processing identical prompt prefixes on subsequent API calls within a session, reducing token costs.

## Requirements

### Requirement 1: FAQ File Loading

**User Story:** As a user, I want the chatbot to load the FAQ file at startup, so that it can answer my questions based on the FAQ content.

#### Acceptance Criteria

1. WHEN the Chatbot starts, THE Chatbot SHALL read the full contents of the FAQ_File located at `output/faq.md` relative to the current working directory.
2. IF the FAQ_File does not exist at startup, THEN THE Chatbot SHALL display an error message indicating the file was not found and exit with a non-zero exit code.
3. IF the FAQ_File is empty or contains only whitespace characters, THEN THE Chatbot SHALL display an error message indicating the file has no content and exit with a non-zero exit code.
4. IF the FAQ_File exists but cannot be read due to a permission or encoding error, THEN THE Chatbot SHALL display an error message indicating the file could not be read and exit with a non-zero exit code.

### Requirement 2: API Key Configuration

**User Story:** As a user, I want the chatbot to securely load the API key from my .env file, so that I don't need to hardcode credentials.

#### Acceptance Criteria

1. WHEN the Chatbot starts, THE Chatbot SHALL load the API_Key from the `.env` file in the working directory using the `ANTHROPIC_API_KEY` variable.
2. IF the `.env` file does not exist, THEN THE Chatbot SHALL display an error message indicating the `.env` file was not found and exit with a non-zero exit code.
3. IF the `ANTHROPIC_API_KEY` variable is missing or contains only whitespace in the `.env` file, THEN THE Chatbot SHALL display an error message indicating the API key is not configured and exit with a non-zero exit code.
4. THE Chatbot SHALL use the `python-dotenv` library to load environment variables from the `.env` file.

### Requirement 3: System Prompt Construction

**User Story:** As a user, I want the chatbot to use the FAQ content as context for answering, so that responses are grounded in the FAQ document.

#### Acceptance Criteria

1. THE Chatbot SHALL construct a System_Prompt that includes the verbatim, unmodified full text of the FAQ_File.
2. THE System_Prompt SHALL contain a clearly delimited section separating the behavioral instructions from the FAQ_File content, so that the model can distinguish instructions from reference material.
3. THE System_Prompt SHALL instruct the model to answer questions using only the information contained in the FAQ_File.
4. THE System_Prompt SHALL instruct the model to explicitly state when the FAQ does not contain sufficient information to answer a question, rather than generating an answer from other knowledge.
5. IF the FAQ_File content exceeds 100,000 characters, THEN THE Chatbot SHALL display an error message indicating the FAQ file is too large for the system prompt and exit with a non-zero exit code.

### Requirement 4: Multi-Turn Conversation

**User Story:** As a user, I want to ask follow-up questions that reference previous answers, so that I can explore topics in the FAQ conversationally.

#### Acceptance Criteria

1. THE Chatbot SHALL maintain a Conversation_History as an ordered list of alternating user messages and assistant responses, appending each user message when submitted and each assistant response when received, within the current Session.
2. WHEN the user submits a question, THE Chatbot SHALL send the System_Prompt, the full Conversation_History, and the new user message to the Claude API in a single request.
3. WHEN the user asks a follow-up question referencing a previous answer, THE Chatbot SHALL produce a response that is consistent with the referenced prior exchange in the Conversation_History and grounded in the FAQ content.
4. IF the Claude API rejects a request due to the Conversation_History exceeding the model's context length, THEN THE Chatbot SHALL remove the oldest user-assistant message pairs from the Conversation_History (retaining the most recent exchanges) and retry the request. IF after removing all but the current user message the request still fails, THEN THE Chatbot SHALL display an error message indicating the question is too long for the model's context window and allow the user to continue the Session by entering another question.
5. WHEN the Chatbot removes message pairs from the Conversation_History due to a context-length error, THE Chatbot SHALL display a warning message informing the user that older conversation history was trimmed.

### Requirement 5: Claude API Integration

**User Story:** As a user, I want the chatbot to use the Claude API for generating responses, so that I get high-quality answers.

#### Acceptance Criteria

1. THE Chatbot SHALL use the Anthropic Python SDK to communicate with the Claude API.
2. THE Chatbot SHALL use the `claude-sonnet-4-5` model for generating responses.
3. WHEN sending a request to the Claude API, THE Chatbot SHALL include the System_Prompt, the full Conversation_History, and a maximum token limit of 1024 tokens for the response.
4. IF the Claude API returns an error, THEN THE Chatbot SHALL display a message indicating that the response could not be generated, and allow the user to continue the Session by entering another question.
5. IF the Claude API request does not receive a response within 30 seconds, THEN THE Chatbot SHALL cancel the request, display a message indicating the request timed out, and allow the user to continue the Session by entering another question.

### Requirement 6: Interactive Terminal Interface

**User Story:** As a user, I want a simple terminal prompt where I can type questions and receive answers, so that I can interact with the chatbot naturally.

#### Acceptance Criteria

1. WHEN the Chatbot starts successfully, THE Chatbot SHALL display a welcome message indicating it is ready to answer questions.
2. WHILE the Session is active, THE Chatbot SHALL display a prompt indicator (e.g., `You: `) after startup and after each assistant response or empty input to signal that the user can type the next question.
3. WHEN the user submits a non-empty question, THE Chatbot SHALL display the assistant's response prefixed with a label (e.g., `Assistant: `) followed by re-displaying the prompt indicator.
4. WHEN the user submits an empty or whitespace-only input, THE Chatbot SHALL re-display the prompt without sending a request to the API.

### Requirement 7: Session Exit

**User Story:** As a user, I want to end the chatbot session gracefully by typing a command, so that I can close the program when I'm done.

#### Acceptance Criteria

1. WHEN the user types `exit`, THE Chatbot SHALL display a goodbye message and terminate with exit code 0.
2. WHEN the user types `quit`, THE Chatbot SHALL display a goodbye message and terminate with exit code 0.
3. THE Chatbot SHALL perform case-insensitive matching on exit commands and SHALL trim leading and trailing whitespace from user input before matching (e.g., `Exit`, `QUIT`, ` exit ` are recognized).
4. IF the user input, after trimming and case-normalization, does not exactly match `exit` or `quit`, THEN THE Chatbot SHALL treat the input as a question (e.g., "exit now" or "quit please" are not recognized as exit commands).
5. WHEN the user sends an EOF signal (Ctrl+D), THE Chatbot SHALL display a goodbye message and terminate with exit code 0.

### Requirement 8: FAQ-Only Answering Behavior

**User Story:** As a user, I want the chatbot to only answer from the FAQ content, so that I can trust the responses are accurate and sourced from the document.

#### Acceptance Criteria

1. WHEN the user asks a question that is answered in the FAQ_File, THE Chatbot SHALL provide an answer whose factual content is traceable to information present in the FAQ_File, using paraphrasing or summarization of the FAQ content without introducing claims not supported by the FAQ_File.
2. WHEN the user asks a question that is not covered or only partially covered by the FAQ_File, THE Chatbot SHALL respond by stating that the FAQ does not contain sufficient information to answer that question, without attempting to fill gaps with information from outside the FAQ_File.
3. THE Chatbot SHALL not generate factual claims, data, or recommendations using knowledge outside the FAQ_File content; however, basic conversational responses such as acknowledging the user's input or asking for clarification are permitted.
4. WHEN the user submits a non-question input such as a greeting, expression of thanks, or unintelligible text, THE Chatbot SHALL respond with a brief acknowledgement and prompt the user to ask a question about the FAQ content, without generating an FAQ-based answer.

### Requirement 9: Prompt Caching

**User Story:** As a user, I want the chatbot to use Anthropic's prompt caching so that the FAQ system prompt tokens are not re-billed at full input price on every turn.

#### Acceptance Criteria

1. WHEN sending a request to the Claude API, THE Chatbot SHALL include `cache_control: {"type": "ephemeral"}` on the system message block containing the FAQ content, enabling Anthropic's prompt caching.
2. THE Chatbot SHALL reuse the same Anthropic client instance across all turns within a Session so that the cached prompt remains valid.
3. THE Chatbot SHALL NOT modify the System_Prompt text between turns within the same Session, ensuring cache hits on subsequent requests.
