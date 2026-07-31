"""Unit tests for faq_generator.reader.read_document."""

import logging
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest

from faq_generator.reader import read_document, _MAX_FILE_SIZE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_stat(size: int):
    stat = MagicMock()
    stat.st_size = size
    return stat


# ---------------------------------------------------------------------------
# File-size guard
# ---------------------------------------------------------------------------

class TestFileSizeGuard:
    def test_skips_file_exceeding_100mb(self, tmp_path, caplog):
        f = tmp_path / "big.txt"
        f.write_bytes(b"x")  # actual content doesn't matter; we mock stat
        with patch.object(Path, "stat", return_value=_make_stat(_MAX_FILE_SIZE + 1)):
            with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
                result = read_document(f)
        assert result is None
        assert any("exceeds 100 MB" in m for m in caplog.messages)

    def test_accepts_file_exactly_at_100mb(self, tmp_path, caplog):
        f = tmp_path / "limit.txt"
        f.write_text("hello world", encoding="utf-8")
        with patch.object(Path, "stat", return_value=_make_stat(_MAX_FILE_SIZE)):
            # read_text will actually read the real (tiny) file — that's fine
            result = read_document(f)
        assert result == "hello world"

    def test_stat_failure_returns_none(self, tmp_path, caplog):
        f = tmp_path / "ghost.txt"
        with patch.object(Path, "stat", side_effect=OSError("no such file")):
            with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
                result = read_document(f)
        assert result is None
        assert any("no such file" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# TXT dispatch
# ---------------------------------------------------------------------------

class TestTxtFiles:
    def test_reads_utf8_text(self, tmp_path):
        f = tmp_path / "doc.txt"
        f.write_text("Hello, world!", encoding="utf-8")
        assert read_document(f) == "Hello, world!"

    def test_unicode_decode_error_returns_none(self, tmp_path, caplog):
        f = tmp_path / "bad.txt"
        # Write bytes that are not valid UTF-8
        f.write_bytes(b"\xff\xfe invalid")
        with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
            result = read_document(f)
        assert result is None
        assert any("encoding failure" in m for m in caplog.messages)

    def test_os_error_returns_none(self, tmp_path, caplog):
        f = tmp_path / "unreadable.txt"
        f.write_text("content", encoding="utf-8")
        with patch.object(Path, "read_text", side_effect=OSError("permission denied")):
            with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
                result = read_document(f)
        assert result is None
        assert any("permission denied" in m for m in caplog.messages)

    def test_empty_file_returns_empty_string(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("", encoding="utf-8")
        assert read_document(f) == ""


# ---------------------------------------------------------------------------
# PDF dispatch
# ---------------------------------------------------------------------------

class TestPdfFiles:
    def _mock_pdfplumber(self, pages_text: list):
        """Return a context-manager mock for pdfplumber.open()."""
        pages = []
        for text in pages_text:
            page = MagicMock()
            page.extract_text.return_value = text
            pages.append(page)

        pdf_mock = MagicMock()
        pdf_mock.__enter__ = MagicMock(return_value=pdf_mock)
        pdf_mock.__exit__ = MagicMock(return_value=False)
        pdf_mock.pages = pages
        return pdf_mock

    def test_joins_page_text_with_newlines(self, tmp_path):
        f = tmp_path / "doc.pdf"
        f.write_bytes(b"%PDF-1.4")  # minimal placeholder content
        pdf_mock = self._mock_pdfplumber(["Page one", "Page two"])
        with patch("faq_generator.reader.pdfplumber.open", return_value=pdf_mock):
            result = read_document(f)
        assert result == "Page one\nPage two"

    def test_skips_none_page_text(self, tmp_path):
        f = tmp_path / "partial.pdf"
        f.write_bytes(b"%PDF-1.4")
        pdf_mock = self._mock_pdfplumber(["First page", None, "Third page"])
        with patch("faq_generator.reader.pdfplumber.open", return_value=pdf_mock):
            result = read_document(f)
        assert result == "First page\nThird page"

    def test_empty_pdf_returns_empty_string(self, tmp_path):
        f = tmp_path / "empty.pdf"
        f.write_bytes(b"%PDF-1.4")
        pdf_mock = self._mock_pdfplumber([])
        with patch("faq_generator.reader.pdfplumber.open", return_value=pdf_mock):
            result = read_document(f)
        assert result == ""

    def test_pdfplumber_exception_returns_none(self, tmp_path, caplog):
        f = tmp_path / "corrupt.pdf"
        f.write_bytes(b"not a pdf")
        with patch("faq_generator.reader.pdfplumber.open", side_effect=Exception("parse error")):
            with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
                result = read_document(f)
        assert result is None
        assert any("parse error" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# DOCX dispatch
# ---------------------------------------------------------------------------

class TestDocxFiles:
    def _mock_docx(self, paragraph_texts: list[str]):
        paragraphs = []
        for text in paragraph_texts:
            p = MagicMock()
            p.text = text
            paragraphs.append(p)

        doc_mock = MagicMock()
        doc_mock.paragraphs = paragraphs
        return doc_mock

    def test_joins_paragraphs_with_newlines(self, tmp_path):
        f = tmp_path / "doc.docx"
        f.write_bytes(b"PK")  # placeholder; stat size is small enough
        doc_mock = self._mock_docx(["Para one", "Para two", "Para three"])
        with patch("faq_generator.reader.docx.Document", return_value=doc_mock):
            result = read_document(f)
        assert result == "Para one\nPara two\nPara three"

    def test_empty_docx_returns_empty_string(self, tmp_path):
        f = tmp_path / "empty.docx"
        f.write_bytes(b"PK")
        doc_mock = self._mock_docx([])
        with patch("faq_generator.reader.docx.Document", return_value=doc_mock):
            result = read_document(f)
        assert result == ""

    def test_docx_exception_returns_none(self, tmp_path, caplog):
        f = tmp_path / "corrupt.docx"
        f.write_bytes(b"not a docx")
        with patch("faq_generator.reader.docx.Document", side_effect=Exception("bad zip")):
            with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
                result = read_document(f)
        assert result is None
        assert any("bad zip" in m for m in caplog.messages)


# ---------------------------------------------------------------------------
# Unsupported extension
# ---------------------------------------------------------------------------

class TestUnsupportedExtension:
    def test_returns_none_for_unknown_extension(self, tmp_path, caplog):
        f = tmp_path / "file.csv"
        f.write_text("a,b,c", encoding="utf-8")
        with caplog.at_level(logging.WARNING, logger="faq_generator.reader"):
            result = read_document(f)
        assert result is None
        assert any("unsupported file extension" in m for m in caplog.messages)
