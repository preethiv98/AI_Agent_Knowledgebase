"""Unit tests for faq_generator.generator.generate_qa_pairs."""

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from faq_generator.generator import generate_qa_pairs
from faq_generator.models import QAPair


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_response(pairs: list[dict]) -> MagicMock:
    """Build a fake anthropic response carrying a JSON-encoded list of pairs."""
    content_block = SimpleNamespace(text=json.dumps(pairs))
    response = MagicMock()
    response.content = [content_block]
    return response


# ---------------------------------------------------------------------------
# Successful parse tests
# ---------------------------------------------------------------------------

class TestSuccessfulParse:
    def test_returns_qa_pairs_for_valid_response(self):
        pairs = [
            {"question": "What is X?", "answer": "X is Y."},
            {"question": "How does Z work?", "answer": "Z works by doing W."},
            {"question": "Why use this?", "answer": "Because it's useful."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("some chunk text", "chunk-1", "fake-key")

        assert len(result) == 3
        assert all(isinstance(p, QAPair) for p in result)
        assert result[0].question == "What is X?"
        assert result[0].answer == "X is Y."

    def test_placeholder_doc_path_and_chunk_index(self):
        pairs = [
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
            {"question": "Q3?", "answer": "A3."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "chunk-1", "fake-key")

        for pair in result:
            assert pair.doc_path == Path("")
            assert pair.chunk_index == 0

    def test_api_key_passed_to_client(self):
        pairs = [{"question": "Q?", "answer": "A."} for _ in range(3)]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            generate_qa_pairs("chunk", "c1", "my-secret-key")

        mock_cls.assert_called_once_with(api_key="my-secret-key")


# ---------------------------------------------------------------------------
# Filtering of malformed / empty entries
# ---------------------------------------------------------------------------

class TestFiltering:
    def test_filters_missing_question_key(self):
        pairs = [
            {"answer": "No question here."},
            {"question": "Good Q?", "answer": "Good A."},
            {"question": "Another Q?", "answer": "Another A."},
            {"question": "Third Q?", "answer": "Third A."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3
        assert all(p.question for p in result)

    def test_filters_missing_answer_key(self):
        pairs = [
            {"question": "Q with no answer?"},
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
            {"question": "Q3?", "answer": "A3."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3

    def test_filters_whitespace_only_question(self):
        pairs = [
            {"question": "   ", "answer": "Answer."},
            {"question": "Real Q?", "answer": "Real A."},
            {"question": "Real Q2?", "answer": "Real A2."},
            {"question": "Real Q3?", "answer": "Real A3."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3

    def test_filters_whitespace_only_answer(self):
        pairs = [
            {"question": "Q?", "answer": "\n\t "},
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
            {"question": "Q3?", "answer": "A3."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3

    def test_filters_empty_string_question(self):
        pairs = [
            {"question": "", "answer": "An answer."},
            {"question": "Q1?", "answer": "A1."},
            {"question": "Q2?", "answer": "A2."},
            {"question": "Q3?", "answer": "A3."},
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3

    def test_non_dict_entries_are_skipped(self):
        # A mix of dicts, strings, and nulls in the JSON array
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            content_block = SimpleNamespace(
                text=json.dumps([
                    "not a dict",
                    None,
                    {"question": "Q?", "answer": "A."},
                    {"question": "Q2?", "answer": "A2."},
                    {"question": "Q3?", "answer": "A3."},
                ])
            )
            mock_cls.return_value.messages.create.return_value.content = [content_block]
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3


# ---------------------------------------------------------------------------
# Fewer-than-3 warning
# ---------------------------------------------------------------------------

class TestFewPairsWarning:
    def test_warns_when_fewer_than_3_pairs(self, caplog):
        pairs = [{"question": "Only one Q?", "answer": "Only one A."}]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            with caplog.at_level(logging.WARNING, logger="faq_generator.generator"):
                result = generate_qa_pairs("chunk", "special-chunk", "k")

        assert len(result) == 1
        assert "special-chunk" in caplog.text
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_no_warning_for_exactly_3_pairs(self, caplog):
        pairs = [
            {"question": f"Q{i}?", "answer": f"A{i}."} for i in range(3)
        ]
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.return_value = _make_response(pairs)
            with caplog.at_level(logging.WARNING, logger="faq_generator.generator"):
                generate_qa_pairs("chunk", "c1", "k")

        warning_records = [r for r in caplog.records if r.levelno == logging.WARNING]
        assert len(warning_records) == 0


# ---------------------------------------------------------------------------
# Retry logic (429 / RateLimitError)
# ---------------------------------------------------------------------------

class TestRetryLogic:
    def test_retries_on_rate_limit_and_succeeds(self):
        """First two calls raise RateLimitError; third succeeds."""
        import anthropic as anthropic_mod

        pairs = [{"question": f"Q{i}?", "answer": f"A{i}."} for i in range(3)]
        success_response = _make_response(pairs)

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = [
                anthropic_mod.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                ),
                anthropic_mod.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                ),
                success_response,
            ]
            with patch("faq_generator.generator.time.sleep") as mock_sleep:
                result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3
        assert mock_sleep.call_count == 2
        mock_sleep.assert_called_with(10)

    def test_returns_empty_after_3_rate_limit_failures(self):
        """All three attempts raise RateLimitError; should return []."""
        import anthropic as anthropic_mod

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = [
                anthropic_mod.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                ),
                anthropic_mod.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                ),
                anthropic_mod.RateLimitError(
                    "rate limited", response=MagicMock(status_code=429), body={}
                ),
            ]
            with patch("faq_generator.generator.time.sleep"):
                result = generate_qa_pairs("chunk", "c1", "k")

        assert result == []

    def test_logs_error_on_exhausted_retries(self, caplog):
        import anthropic as anthropic_mod

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = anthropic_mod.RateLimitError(
                "rate limited", response=MagicMock(status_code=429), body={}
            )
            with patch("faq_generator.generator.time.sleep"):
                with caplog.at_level(logging.ERROR, logger="faq_generator.generator"):
                    generate_qa_pairs("chunk", "exhausted-chunk", "k")

        assert "exhausted-chunk" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)


# ---------------------------------------------------------------------------
# Other API errors
# ---------------------------------------------------------------------------

class TestAPIErrors:
    def test_returns_empty_on_api_error(self):
        import anthropic as anthropic_mod

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = anthropic_mod.APIError(
                message="server error", request=MagicMock(), body={}
            )
            result = generate_qa_pairs("chunk", "c1", "k")

        assert result == []

    def test_logs_error_on_api_error(self, caplog):
        import anthropic as anthropic_mod

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = anthropic_mod.APIError(
                message="server error", request=MagicMock(), body={}
            )
            with caplog.at_level(logging.ERROR, logger="faq_generator.generator"):
                generate_qa_pairs("chunk", "api-error-chunk", "k")

        assert "api-error-chunk" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_does_not_retry_on_non_429_api_error(self):
        import anthropic as anthropic_mod

        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            mock_cls.return_value.messages.create.side_effect = anthropic_mod.APIError(
                message="server error", request=MagicMock(), body={}
            )
            with patch("faq_generator.generator.time.sleep") as mock_sleep:
                generate_qa_pairs("chunk", "c1", "k")

        mock_sleep.assert_not_called()


# ---------------------------------------------------------------------------
# JSON parse errors
# ---------------------------------------------------------------------------

class TestJSONParseErrors:
    def test_returns_empty_on_invalid_json(self):
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            content_block = SimpleNamespace(text="not valid json {{{}}")
            mock_cls.return_value.messages.create.return_value.content = [content_block]
            result = generate_qa_pairs("chunk", "c1", "k")

        assert result == []

    def test_logs_error_on_json_parse_failure(self, caplog):
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            content_block = SimpleNamespace(text="this is not valid json at all {{{")
            mock_cls.return_value.messages.create.return_value.content = [content_block]
            with caplog.at_level(logging.ERROR, logger="faq_generator.generator"):
                generate_qa_pairs("chunk", "json-fail-chunk", "k")

        assert "json-fail-chunk" in caplog.text
        assert any(r.levelno == logging.ERROR for r in caplog.records)

    def test_returns_empty_when_response_is_object_not_array(self):
        """Top-level JSON object instead of array produces no pairs."""
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            content_block = SimpleNamespace(text=json.dumps({"question": "Q?", "answer": "A."}))
            mock_cls.return_value.messages.create.return_value.content = [content_block]
            result = generate_qa_pairs("chunk", "c1", "k")

        # No pairs because the top-level is not a list
        assert result == []

    def test_filters_non_string_question_and_answer(self):
        """Entries where question/answer are non-string types should be discarded (line 96)."""
        with patch("faq_generator.generator.anthropic.Anthropic") as mock_cls:
            content_block = SimpleNamespace(text=json.dumps([
                {"question": 42, "answer": "An answer."},          # int question
                {"question": "Good Q?", "answer": ["list answer"]}, # list answer
                {"question": "Real Q?", "answer": "Real A."},
                {"question": "Real Q2?", "answer": "Real A2."},
                {"question": "Real Q3?", "answer": "Real A3."},
            ]))
            mock_cls.return_value.messages.create.return_value.content = [content_block]
            result = generate_qa_pairs("chunk", "c1", "k")

        assert len(result) == 3
        assert all(isinstance(p.question, str) and isinstance(p.answer, str) for p in result)
