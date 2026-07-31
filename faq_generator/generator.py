"""QA pair generator using the Anthropic Claude API."""

import json
import logging
import time
from pathlib import Path

import anthropic

from faq_generator.models import QAPair

logger = logging.getLogger(__name__)

_SYSTEM_MESSAGE = (
    "You are a technical documentation assistant. Read the following text and generate between 3 and 10 FAQ entries.\n"
    "Return ONLY a JSON array with objects having \"question\" and \"answer\" keys. No prose, no markdown fences."
)

_MAX_RETRIES = 3
_RETRY_DELAY = 10  # seconds


def generate_qa_pairs(chunk: str, chunk_id: str, api_key: str) -> list[QAPair]:
    """Send a chunk to Claude and return parsed QA pairs.

    Retries on HTTP 429; logs and returns [] on unrecoverable error.

    Args:
        chunk: The text chunk to generate QA pairs from.
        chunk_id: An identifier for this chunk, used in log messages.
        api_key: The Anthropic API key.

    Returns:
        A list of QAPair objects. doc_path and chunk_index are left as
        placeholder values (Path("") and 0) to be set by the caller.
    """
    client = anthropic.Anthropic(api_key=api_key)
    user_message = f"Text:\n{chunk}"

    last_error: Exception | None = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            response = client.messages.create(
                model="claude-sonnet-4-5",
                max_tokens=2048,
                system=_SYSTEM_MESSAGE,
                messages=[{"role": "user", "content": user_message}],
            )
            raw_text = response.content[0].text
            break  # success — exit retry loop
        except anthropic.RateLimitError as exc:
            last_error = exc
            if attempt < _MAX_RETRIES:
                logger.warning(
                    "Rate limit hit for chunk %s (attempt %d/%d). Retrying in %ds.",
                    chunk_id, attempt, _MAX_RETRIES, _RETRY_DELAY,
                )
                time.sleep(_RETRY_DELAY)
            else:
                logger.error(
                    "Rate limit exceeded for chunk %s after %d attempts. Skipping.",
                    chunk_id, _MAX_RETRIES,
                )
                return []
        except anthropic.APIError as exc:
            logger.error(
                "API error for chunk %s: %s. Skipping.", chunk_id, exc
            )
            return []
    else:
        # Loop completed without break — all retries exhausted by RateLimitError
        logger.error(
            "Rate limit exceeded for chunk %s after %d attempts. Skipping.",
            chunk_id, _MAX_RETRIES,
        )
        return []

    # Defensively strip markdown code fences that the model may wrap around JSON
    stripped = raw_text.strip()
    if stripped.startswith("```json"):
        stripped = stripped[len("```json"):]
    elif stripped.startswith("```"):
        stripped = stripped[len("```"):]
    if stripped.endswith("```"):
        stripped = stripped[:-3]
    stripped = stripped.strip()

    # Parse the JSON response
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as exc:
        logger.debug(
            "Raw response for chunk %s (first 200 chars): %s",
            chunk_id, raw_text[:200],
        )
        logger.error(
            "JSON parse error for chunk %s: %s. Skipping.", chunk_id, exc
        )
        return []

    # Filter and construct QAPair objects
    pairs: list[QAPair] = []
    if isinstance(data, list):
        for entry in data:
            if not isinstance(entry, dict):
                continue
            question = entry.get("question", "")
            answer = entry.get("answer", "")
            if not isinstance(question, str) or not isinstance(answer, str):
                continue
            if not question.strip() or not answer.strip():
                continue
            pairs.append(
                QAPair(
                    question=question,
                    answer=answer,
                    doc_path=Path(""),
                    chunk_index=0,
                )
            )

    if len(pairs) < 3:
        logger.warning(
            "Chunk %s produced only %d valid QA pair(s) (expected at least 3).",
            chunk_id, len(pairs),
        )

    return pairs
