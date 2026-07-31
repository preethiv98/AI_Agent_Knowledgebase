"""Unit and property-based tests for faq_generator.writer.write_faq."""

from pathlib import Path

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from faq_generator.models import QAPair
from faq_generator.writer import write_faq


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pair(question: str, answer: str, doc_path: Path, chunk_index: int = 0) -> QAPair:
    return QAPair(question=question, answer=answer, doc_path=doc_path, chunk_index=chunk_index)


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------

class TestWriteFaqStructure:
    def test_creates_output_file(self, tmp_path: Path):
        out = tmp_path / "output" / "faq.md"
        pairs = [make_pair("What is X?", "X is a thing.", tmp_path / "doc1.pdf")]
        write_faq(pairs, out)
        assert out.exists()

    def test_creates_parent_directories(self, tmp_path: Path):
        out = tmp_path / "deep" / "nested" / "dir" / "faq.md"
        pairs = [make_pair("Q?", "A.", tmp_path / "doc.txt")]
        write_faq(pairs, out)
        assert out.exists()

    def test_opens_heading(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        pairs = [make_pair("Q?", "A.", tmp_path / "doc.txt")]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert content.startswith("# FAQ\n\n")

    def test_writes_doc_heading_for_single_doc(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc = tmp_path / "document1.pdf"
        pairs = [make_pair("What is X?", "X is a thing.", doc)]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "### document1.pdf\n\n" in content

    def test_writes_question_as_h2(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        pairs = [make_pair("What is X?", "X is a thing.", tmp_path / "doc.pdf")]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "## What is X?\n\n" in content

    def test_writes_answer_after_question(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        pairs = [make_pair("What is X?", "X is a thing.", tmp_path / "doc.pdf")]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "## What is X?\n\nX is a thing.\n\n" in content

    def test_full_structure_single_doc(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc = tmp_path / "document1.pdf"
        pairs = [
            make_pair("What is X?", "X is a thing.", doc),
            make_pair("How does Y work?", "Y works by Z.", doc, chunk_index=1),
        ]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        expected = (
            "# FAQ\n\n"
            "### document1.pdf\n\n"
            "## What is X?\n\nX is a thing.\n\n"
            "## How does Y work?\n\nY works by Z.\n\n"
        )
        assert content == expected

    def test_multiple_docs_each_get_heading(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc1 = tmp_path / "document1.pdf"
        doc2 = tmp_path / "document2.txt"
        pairs = [
            make_pair("What is X?", "X is a thing.", doc1),
            make_pair("How do I Y?", "You Y by doing Z.", doc2),
        ]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "### document1.pdf\n\n" in content
        assert "### document2.txt\n\n" in content

    def test_doc_heading_not_repeated_for_same_doc(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc = tmp_path / "doc.pdf"
        pairs = [
            make_pair("Q1?", "A1.", doc),
            make_pair("Q2?", "A2.", doc),
            make_pair("Q3?", "A3.", doc),
        ]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert content.count("### doc.pdf") == 1

    def test_doc_heading_inserted_on_transition(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc1 = tmp_path / "a.pdf"
        doc2 = tmp_path / "b.pdf"
        pairs = [
            make_pair("Q1?", "A1.", doc1),
            make_pair("Q2?", "A2.", doc1),
            make_pair("Q3?", "A3.", doc2),
        ]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert content.count("### a.pdf") == 1
        assert content.count("### b.pdf") == 1
        # b.pdf heading should come after a.pdf heading
        assert content.index("### a.pdf") < content.index("### b.pdf")

    def test_empty_pairs_writes_only_heading(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        write_faq([], out)
        content = out.read_text(encoding="utf-8")
        assert content == "# FAQ\n\n"

    def test_overwrites_existing_file(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        out.write_text("old content", encoding="utf-8")
        pairs = [make_pair("Q?", "A.", tmp_path / "doc.txt")]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "old content" not in content
        assert content.startswith("# FAQ\n\n")

    def test_utf8_encoding_used(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc = tmp_path / "doc.txt"
        pairs = [make_pair("What is café?", "It's a café.", doc)]
        write_faq(pairs, out)
        # Reading back as bytes and decoding as UTF-8 must not raise
        raw = out.read_bytes()
        content = raw.decode("utf-8")
        assert "café" in content

    def test_uses_basename_not_full_path_for_heading(self, tmp_path: Path):
        out = tmp_path / "faq.md"
        doc = tmp_path / "subdir" / "myfile.pdf"
        pairs = [make_pair("Q?", "A.", doc)]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        assert "### myfile.pdf\n\n" in content
        # The full path should NOT appear as the heading
        assert f"### {doc}\n\n" not in content

    def test_full_multi_doc_structure(self, tmp_path: Path):
        """Verify the exact Markdown structure from the design document example."""
        out = tmp_path / "faq.md"
        doc1 = tmp_path / "document1.pdf"
        doc2 = tmp_path / "document2.txt"
        pairs = [
            make_pair("What is X?", "X is a thing.", doc1),
            make_pair("How do I Y?", "You Y by doing Z.", doc2),
        ]
        write_faq(pairs, out)
        content = out.read_text(encoding="utf-8")
        expected = (
            "# FAQ\n\n"
            "### document1.pdf\n\n"
            "## What is X?\n\nX is a thing.\n\n"
            "### document2.txt\n\n"
            "## How do I Y?\n\nYou Y by doing Z.\n\n"
        )
        assert content == expected


class TestWriteFaqErrors:
    def test_raises_oserror_on_unwritable_path(self, tmp_path: Path):
        # Point output at a path where parent is a file (cannot be a dir)
        blocker = tmp_path / "blocker"
        blocker.write_text("I am a file", encoding="utf-8")
        out = blocker / "faq.md"  # blocker is a file, not a dir
        with pytest.raises(OSError):
            write_faq([], out)


# ---------------------------------------------------------------------------
# Property-based tests — Property 9
# ---------------------------------------------------------------------------

# Strategy to generate a non-empty, non-whitespace text string
_text = st.text(
    alphabet=st.characters(blacklist_categories=("Cs",), blacklist_characters="\x00\r"),
    min_size=1,
).filter(lambda s: s.strip())

# Strategy to generate a list of QAPair objects for one or more docs
_qa_pair_list = st.lists(
    st.builds(
        QAPair,
        question=_text,
        answer=_text,
        doc_path=st.sampled_from([
            Path("/docs/alpha.pdf"),
            Path("/docs/beta.txt"),
            Path("/docs/gamma.docx"),
        ]),
        chunk_index=st.integers(min_value=0, max_value=10),
    ),
    min_size=1,
    max_size=20,
)


@given(pairs=_qa_pair_list)
@settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
def test_property_9_output_completeness(pairs: list[QAPair], tmp_path: Path):
    # Feature: doc-faq-generator, Property 9: Output Markdown contains every surviving QA pair
    # Validates: Requirements 8.3, 8.4, 8.5
    out = tmp_path / "faq.md"
    write_faq(pairs, out)
    content = out.read_text(encoding="utf-8")

    # Every question and answer must appear in the output
    for pair in pairs:
        assert pair.question in content, f"Question missing: {pair.question!r}"
        assert pair.answer in content, f"Answer missing: {pair.answer!r}"

    # Every distinct doc basename must appear as a ### heading
    seen_docs = set()
    for pair in pairs:
        seen_docs.add(pair.doc_path.name)
    for basename in seen_docs:
        assert f"### {basename}\n\n" in content, (
            f"Missing ### heading for {basename!r}"
        )
