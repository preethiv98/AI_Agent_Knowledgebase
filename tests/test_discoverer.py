"""Unit tests for faq_generator.discoverer.discover_documents."""

import logging
from pathlib import Path

import pytest

from faq_generator.discoverer import discover_documents


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path: Path) -> Path:
    """Create an empty file at *path*, creating parent dirs as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()
    return path


# ---------------------------------------------------------------------------
# Basic discovery
# ---------------------------------------------------------------------------

class TestExtensionFiltering:
    def test_returns_pdf_files(self, tmp_path):
        _touch(tmp_path / "doc.pdf")
        result = discover_documents(tmp_path)
        assert result == [tmp_path / "doc.pdf"]

    def test_returns_docx_files(self, tmp_path):
        _touch(tmp_path / "doc.docx")
        result = discover_documents(tmp_path)
        assert result == [tmp_path / "doc.docx"]

    def test_returns_txt_files(self, tmp_path):
        _touch(tmp_path / "doc.txt")
        result = discover_documents(tmp_path)
        assert result == [tmp_path / "doc.txt"]

    def test_ignores_unsupported_extensions(self, tmp_path):
        _touch(tmp_path / "image.png")
        _touch(tmp_path / "data.csv")
        _touch(tmp_path / "archive.zip")
        result = discover_documents(tmp_path)
        assert result == []

    def test_case_insensitive_extensions(self, tmp_path):
        _touch(tmp_path / "upper.PDF")
        _touch(tmp_path / "mixed.Docx")
        _touch(tmp_path / "caps.TXT")
        result = discover_documents(tmp_path)
        assert len(result) == 3

    def test_empty_folder_returns_empty_list(self, tmp_path):
        result = discover_documents(tmp_path)
        assert result == []

    def test_mixed_supported_and_unsupported(self, tmp_path):
        _touch(tmp_path / "a.pdf")
        _touch(tmp_path / "b.md")
        _touch(tmp_path / "c.txt")
        result = discover_documents(tmp_path)
        assert len(result) == 2
        assert tmp_path / "b.md" not in result


# ---------------------------------------------------------------------------
# Sorting
# ---------------------------------------------------------------------------

class TestSorting:
    def test_alphabetically_sorted(self, tmp_path):
        _touch(tmp_path / "zebra.txt")
        _touch(tmp_path / "alpha.txt")
        _touch(tmp_path / "middle.pdf")
        result = discover_documents(tmp_path)
        assert result == sorted(result, key=str)

    def test_sorting_across_subdirectories(self, tmp_path):
        _touch(tmp_path / "b" / "file.txt")
        _touch(tmp_path / "a" / "file.txt")
        result = discover_documents(tmp_path)
        assert result == sorted(result, key=str)


# ---------------------------------------------------------------------------
# Depth limiting
# ---------------------------------------------------------------------------

class TestDepthLimiting:
    def test_files_at_root_included(self, tmp_path):
        _touch(tmp_path / "root.txt")
        result = discover_documents(tmp_path, max_depth=1)
        assert tmp_path / "root.txt" in result

    def test_files_at_max_depth_included(self, tmp_path):
        # depth 1 means one level of subdirectory
        _touch(tmp_path / "sub" / "file.txt")
        result = discover_documents(tmp_path, max_depth=1)
        assert tmp_path / "sub" / "file.txt" in result

    def test_files_beyond_max_depth_excluded(self, tmp_path):
        # depth 2 is beyond max_depth=1
        _touch(tmp_path / "sub" / "deep" / "file.txt")
        result = discover_documents(tmp_path, max_depth=1)
        assert tmp_path / "sub" / "deep" / "file.txt" not in result

    def test_default_max_depth_is_ten(self, tmp_path):
        # Build a 10-level deep path
        deep = tmp_path
        for i in range(10):
            deep = deep / f"d{i}"
        _touch(deep / "file.txt")
        result = discover_documents(tmp_path)  # default max_depth=10
        assert deep / "file.txt" in result

    def test_depth_zero_only_root_files(self, tmp_path):
        _touch(tmp_path / "root.txt")
        _touch(tmp_path / "sub" / "nested.txt")
        result = discover_documents(tmp_path, max_depth=0)
        assert tmp_path / "root.txt" in result
        assert tmp_path / "sub" / "nested.txt" not in result


# ---------------------------------------------------------------------------
# max_files cap
# ---------------------------------------------------------------------------

class TestMaxFilesCap:
    def test_no_warning_under_limit(self, tmp_path, caplog):
        for i in range(3):
            _touch(tmp_path / f"file{i}.txt")
        with caplog.at_level(logging.WARNING, logger="faq_generator.discoverer"):
            result = discover_documents(tmp_path, max_files=10)
        assert len(result) == 3
        assert not caplog.records

    def test_truncates_to_max_files(self, tmp_path):
        for i in range(5):
            _touch(tmp_path / f"file{i}.txt")
        result = discover_documents(tmp_path, max_files=3)
        assert len(result) == 3

    def test_logs_warning_when_limit_exceeded(self, tmp_path, caplog):
        for i in range(5):
            _touch(tmp_path / f"file{i}.txt")
        with caplog.at_level(logging.WARNING, logger="faq_generator.discoverer"):
            discover_documents(tmp_path, max_files=3)
        assert any("limit" in r.message.lower() or "exceed" in r.message.lower()
                   for r in caplog.records)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    def test_truncated_result_is_alphabetically_first(self, tmp_path):
        # Files: a.txt, b.txt, c.txt, d.txt, e.txt — limit 2 → a.txt, b.txt
        for ch in "abcde":
            _touch(tmp_path / f"{ch}.txt")
        result = discover_documents(tmp_path, max_files=2)
        assert result == [tmp_path / "a.txt", tmp_path / "b.txt"]

    def test_exact_max_files_no_truncation(self, tmp_path, caplog):
        for i in range(5):
            _touch(tmp_path / f"file{i}.txt")
        with caplog.at_level(logging.WARNING, logger="faq_generator.discoverer"):
            result = discover_documents(tmp_path, max_files=5)
        assert len(result) == 5
        assert not caplog.records


# ---------------------------------------------------------------------------
# Recursive discovery
# ---------------------------------------------------------------------------

class TestRecursiveDiscovery:
    def test_discovers_files_in_subdirectories(self, tmp_path):
        _touch(tmp_path / "sub1" / "a.pdf")
        _touch(tmp_path / "sub2" / "b.docx")
        result = discover_documents(tmp_path)
        assert len(result) == 2

    def test_mixed_depth_files(self, tmp_path):
        _touch(tmp_path / "top.txt")
        _touch(tmp_path / "sub" / "mid.pdf")
        _touch(tmp_path / "sub" / "deep" / "bottom.docx")
        result = discover_documents(tmp_path)
        assert len(result) == 3
