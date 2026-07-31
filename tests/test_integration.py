"""Integration tests for the full doc-faq-generator pipeline.

Tests run against a temporary working directory with small fixture documents and a
mocked Anthropic API so no real network calls are made.

Each test:
  - changes CWD to `tmp_path` via `monkeypatch.chdir`
  - creates any needed fixture files inside `tmp_path`
  - patches `faq_generator.generator.anthropic.Anthropic` with a fixed response
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import main as main_module

# ---------------------------------------------------------------------------
# Fixed mock API response
# ---------------------------------------------------------------------------

_MOCK_QA_PAIRS = [
    {"question": "What is this?", "answer": "This is a test document."},
    {"question": "Why does it exist?", "answer": "For testing purposes."},
    {"question": "Who uses it?", "answer": "Developers testing the pipeline."},
]

_MOCK_RESPONSE_TEXT = json.dumps(_MOCK_QA_PAIRS)


def _make_mock_anthropic_client():
    """Return a mock Anthropic client whose messages.create() returns the fixed QA JSON."""
    content_block = SimpleNamespace(text=_MOCK_RESPONSE_TEXT)
    response = MagicMock()
    response.content = [content_block]

    mock_client = MagicMock()
    mock_client.messages.create.return_value = response
    return mock_client


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------

def _create_txt_file(directory: Path, name: str, content: str) -> Path:
    """Write a plain-text file under *directory* and return its path."""
    p = directory / name
    p.write_text(content, encoding="utf-8")
    return p


def _create_docx_file(directory: Path, name: str, content: str) -> Path:
    """Create a .docx file with a single paragraph using python-docx."""
    from docx import Document  # type: ignore

    doc = Document()
    doc.add_paragraph(content)
    p = directory / name
    doc.save(str(p))
    return p


def _create_env_file(directory: Path, api_key: str = "test-key-123") -> Path:
    """Write a minimal .env file with the given API key."""
    env = directory / ".env"
    env.write_text(f"ANTHROPIC_API_KEY={api_key}\n", encoding="utf-8")
    return env


def _create_fixture_docs(base: Path) -> list[Path]:
    """Create 3 small fixture documents (2 txt + 1 docx) and return their paths."""
    docs_dir = base / "docs"
    docs_dir.mkdir()

    files = [
        _create_txt_file(
            docs_dir,
            "intro.txt",
            "This document introduces the project. It explains what the project does "
            "and why it was created. The project aims to simplify FAQ generation.",
        ),
        _create_txt_file(
            docs_dir,
            "usage.txt",
            "To use the tool, install the dependencies and run the CLI. "
            "Point it at a folder containing your documents. "
            "The tool will generate a FAQ at output/faq.md.",
        ),
        _create_docx_file(
            docs_dir,
            "overview.docx",
            "This overview document covers the architecture of the system. "
            "The pipeline consists of several modular stages. "
            "Each stage can be tested in isolation.",
        ),
    ]
    return files


# ---------------------------------------------------------------------------
# Test 1: Full pipeline produces output/faq.md beginning with "# FAQ"
# ---------------------------------------------------------------------------

class TestFullPipelineOutput:
    def test_output_file_starts_with_faq_heading(self, tmp_path, monkeypatch):
        """End-to-end run should write output/faq.md that starts with '# FAQ'."""
        monkeypatch.chdir(tmp_path)

        docs = _create_fixture_docs(tmp_path)
        _create_env_file(tmp_path)

        # Ensure ANTHROPIC_API_KEY from the real .env (if present) doesn't bleed in
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_client = _make_mock_anthropic_client()

        with patch("faq_generator.generator.anthropic.Anthropic", return_value=mock_client):
            monkeypatch.setattr(
                sys, "argv",
                ["faq-generator", str(tmp_path / "docs"), "--yes"],
            )
            main_module.main()

        output = tmp_path / "output" / "faq.md"
        assert output.exists(), "output/faq.md was not created"
        content = output.read_text(encoding="utf-8")
        assert content.startswith("# FAQ"), (
            f"output/faq.md does not start with '# FAQ'.\nActual start: {content[:100]!r}"
        )


# ---------------------------------------------------------------------------
# Test 2: Every fixture document's basename appears as a ### heading
# ---------------------------------------------------------------------------

class TestDocumentHeadings:
    def test_each_doc_basename_appears_as_h3_heading(self, tmp_path, monkeypatch):
        """Each fixture file's basename should appear as a '### <name>' heading."""
        monkeypatch.chdir(tmp_path)

        docs = _create_fixture_docs(tmp_path)
        _create_env_file(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_client = _make_mock_anthropic_client()

        with patch("faq_generator.generator.anthropic.Anthropic", return_value=mock_client):
            monkeypatch.setattr(
                sys, "argv",
                ["faq-generator", str(tmp_path / "docs"), "--yes"],
            )
            main_module.main()

        output = tmp_path / "output" / "faq.md"
        content = output.read_text(encoding="utf-8")

        for doc_path in docs:
            basename = doc_path.name
            assert f"### {basename}" in content, (
                f"Expected '### {basename}' heading in output/faq.md but it was missing.\n"
                f"Content:\n{content}"
            )


# ---------------------------------------------------------------------------
# Test 3: Summary printed to stdout matches actual counts
# ---------------------------------------------------------------------------

class TestStdoutSummary:
    def test_done_and_summary_lines_appear_in_stdout(self, tmp_path, monkeypatch, capsys):
        """The final summary printed to stdout should include Done., Documents processed:, QA pairs generated:."""
        monkeypatch.chdir(tmp_path)

        _create_fixture_docs(tmp_path)
        _create_env_file(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        mock_client = _make_mock_anthropic_client()

        with patch("faq_generator.generator.anthropic.Anthropic", return_value=mock_client):
            monkeypatch.setattr(
                sys, "argv",
                ["faq-generator", str(tmp_path / "docs"), "--yes"],
            )
            main_module.main()

        captured = capsys.readouterr()
        stdout = captured.out

        assert "Done." in stdout, f"'Done.' not found in stdout.\nStdout:\n{stdout}"
        assert "Documents processed:" in stdout, (
            f"'Documents processed:' not found in stdout.\nStdout:\n{stdout}"
        )
        assert "QA pairs generated:" in stdout, (
            f"'QA pairs generated:' not found in stdout.\nStdout:\n{stdout}"
        )


# ---------------------------------------------------------------------------
# Test 4: Folder with no supported documents exits with code 1
# ---------------------------------------------------------------------------

class TestNoSupportedDocuments:
    def test_empty_folder_exits_with_code_1(self, tmp_path, monkeypatch, capsys):
        """An empty folder should cause the pipeline to exit with code 1."""
        monkeypatch.chdir(tmp_path)

        empty_dir = tmp_path / "empty"
        empty_dir.mkdir()
        _create_env_file(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        monkeypatch.setattr(
            sys, "argv",
            ["faq-generator", str(empty_dir), "--yes"],
        )

        with pytest.raises(SystemExit) as exc_info:
            main_module.main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No supported documents found" in captured.out, (
            f"Expected 'No supported documents found' in stdout.\nStdout:\n{captured.out}"
        )

    def test_folder_with_only_py_files_exits_with_code_1(self, tmp_path, monkeypatch, capsys):
        """A folder containing only .py files (unsupported) should exit with code 1."""
        monkeypatch.chdir(tmp_path)

        unsupported_dir = tmp_path / "unsupported"
        unsupported_dir.mkdir()
        (unsupported_dir / "script.py").write_text("print('hello')", encoding="utf-8")
        (unsupported_dir / "helper.py").write_text("x = 1", encoding="utf-8")
        _create_env_file(tmp_path)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        monkeypatch.setattr(
            sys, "argv",
            ["faq-generator", str(unsupported_dir), "--yes"],
        )

        with pytest.raises(SystemExit) as exc_info:
            main_module.main()

        assert exc_info.value.code == 1

        captured = capsys.readouterr()
        assert "No supported documents found" in captured.out


# ---------------------------------------------------------------------------
# Test 5: Missing .env exits with a non-zero code
# ---------------------------------------------------------------------------

class TestMissingEnv:
    def test_missing_env_file_exits_nonzero(self, tmp_path, monkeypatch, capsys):
        """If .env is absent, the tool should exit with a non-zero code."""
        monkeypatch.chdir(tmp_path)

        # Create documents but deliberately no .env
        _create_fixture_docs(tmp_path)

        # Remove key from environment in case it's inherited from the shell
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        monkeypatch.setattr(
            sys, "argv",
            ["faq-generator", str(tmp_path / "docs"), "--yes"],
        )

        with pytest.raises(SystemExit) as exc_info:
            main_module.main()

        assert exc_info.value.code != 0

        captured = capsys.readouterr()
        assert "Error: .env file not found" in captured.out, (
            f"Expected '.env file not found' error message.\nStdout:\n{captured.out}"
        )
