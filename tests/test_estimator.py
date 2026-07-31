"""Unit tests for faq_generator.estimator.estimate_chunks."""

from pathlib import Path
from unittest.mock import patch

import pytest

from faq_generator.estimator import estimate_chunks
from faq_generator.models import EstimateResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(n_words: int) -> str:
    return " ".join(f"word{i}" for i in range(n_words))


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestEstimateChunks:
    def test_single_readable_file_contributes_chunks(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text(_text(100), encoding="utf-8")
        result = estimate_chunks([f])
        assert isinstance(result, EstimateResult)
        assert result.total_chunks == 1
        assert result.per_doc[f] == 1

    def test_unreadable_file_contributes_zero(self, tmp_path):
        # Line 23: per_doc[path] = 0 when read_document returns None
        f = tmp_path / "bad.pdf"
        f.write_bytes(b"not a pdf")
        with patch("faq_generator.estimator.read_document", return_value=None):
            result = estimate_chunks([f])
        assert result.per_doc[f] == 0
        assert result.total_chunks == 0

    def test_mix_of_readable_and_unreadable(self, tmp_path):
        good = tmp_path / "good.txt"
        bad = tmp_path / "bad.txt"
        good.write_text(_text(100), encoding="utf-8")
        bad.write_text("content", encoding="utf-8")

        def mock_read(path: Path):
            if path == bad:
                return None
            return path.read_text(encoding="utf-8")

        with patch("faq_generator.estimator.read_document", side_effect=mock_read):
            result = estimate_chunks([good, bad])

        assert result.per_doc[good] == 1
        assert result.per_doc[bad] == 0
        assert result.total_chunks == 1

    def test_total_is_sum_of_per_doc_counts(self, tmp_path):
        files = []
        for i in range(3):
            f = tmp_path / f"doc{i}.txt"
            f.write_text(_text(100), encoding="utf-8")
            files.append(f)

        result = estimate_chunks(files)
        assert result.total_chunks == sum(result.per_doc.values())

    def test_per_doc_keys_match_input_paths(self, tmp_path):
        files = []
        for i in range(4):
            f = tmp_path / f"file{i}.txt"
            f.write_text(_text(50), encoding="utf-8")
            files.append(f)

        result = estimate_chunks(files)
        assert set(result.per_doc.keys()) == set(files)

    def test_empty_text_gives_zero_chunks(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        result = estimate_chunks([f])
        assert result.per_doc[f] == 0
        assert result.total_chunks == 0

    def test_empty_path_list(self):
        result = estimate_chunks([])
        assert result.total_chunks == 0
        assert result.per_doc == {}

    def test_large_document_produces_multiple_chunks(self, tmp_path):
        f = tmp_path / "big.txt"
        f.write_text(_text(9_000), encoding="utf-8")
        result = estimate_chunks([f])
        assert result.per_doc[f] >= 2
        assert result.total_chunks >= 2
