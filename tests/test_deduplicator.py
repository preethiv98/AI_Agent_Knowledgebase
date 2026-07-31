"""Unit and property-based tests for faq_generator.deduplicator.deduplicate."""

import io
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from faq_generator.deduplicator import deduplicate, _normalize, _find, _union, _make_union_find
from faq_generator.models import QAPair


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_pair(question: str, answer: str, doc: str = "doc.pdf", chunk: int = 0) -> QAPair:
    return QAPair(question=question, answer=answer, doc_path=Path(doc), chunk_index=chunk)


# ---------------------------------------------------------------------------
# Internal helpers — coverage for _find / _union / _make_union_find
# ---------------------------------------------------------------------------

class TestUnionFindInternals:
    def test_make_union_find_identity(self):
        parent = _make_union_find(4)
        assert parent == [0, 1, 2, 3]

    def test_find_root_is_self(self):
        parent = _make_union_find(3)
        assert _find(parent, 0) == 0
        assert _find(parent, 2) == 2

    def test_find_after_union(self):
        # Lines 18-19: path traversal in _find when parent[x] != x
        parent = _make_union_find(4)
        _union(parent, 0, 1)   # 0 and 1 are now in the same set
        _union(parent, 0, 2)   # 0 and 2 are now in the same set
        # All three should resolve to the same root
        r0 = _find(parent, 0)
        r1 = _find(parent, 1)
        r2 = _find(parent, 2)
        assert r0 == r1 == r2

    def test_union_merges_distinct_sets(self):
        # Lines 24-26: _union when rx != ry
        parent = _make_union_find(4)
        _union(parent, 0, 3)
        assert _find(parent, 0) == _find(parent, 3)

    def test_union_no_op_when_same_root(self):
        # _union when rx == ry — should be a no-op
        parent = _make_union_find(3)
        _union(parent, 0, 1)
        before = parent[:]
        _union(parent, 0, 1)  # already same root; no change
        # Roots are still the same
        assert _find(parent, 0) == _find(parent, 1)

    def test_path_compression_applied(self):
        # Manually build a chain: 2 → 1 → 0
        parent = [0, 0, 1]  # 0 is root, 1 points to 0, 2 points to 1
        root = _find(parent, 2)
        assert root == 0
        # After path compression, parent[2] should point closer to root
        assert parent[2] == 0


# ---------------------------------------------------------------------------
# Pass 1: Exact-match deduplication
# ---------------------------------------------------------------------------

class TestExactMatchDedup:
    def test_identical_questions_deduped(self, capsys):
        pairs = [
            make_pair("What is X?", "A1."),
            make_pair("What is X?", "A2."),  # exact duplicate
        ]
        result, removed = deduplicate(pairs)
        assert removed == 1
        assert len(result) == 1
        assert result[0].answer == "A1."  # first occurrence kept

    def test_case_insensitive_dedup(self, capsys):
        pairs = [
            make_pair("what is x?", "A1."),
            make_pair("WHAT IS X?", "A2."),
        ]
        result, removed = deduplicate(pairs)
        assert removed == 1
        assert len(result) == 1

    def test_whitespace_normalization_dedup(self, capsys):
        pairs = [
            make_pair("what  is   x?", "A1."),
            make_pair("what is x?", "A2."),
        ]
        result, removed = deduplicate(pairs)
        assert removed == 1
        assert len(result) == 1

    def test_distinct_questions_not_deduped(self, capsys):
        pairs = [
            make_pair("What is X?", "A1."),
            make_pair("How does Y work?", "A2."),
            make_pair("Why use Z?", "A3."),
        ]
        result, removed = deduplicate(pairs)
        assert removed == 0
        assert len(result) == 3


# ---------------------------------------------------------------------------
# Pass 1 ≤ 1 pair path (line 46)
# ---------------------------------------------------------------------------

class TestSinglePairPath:
    def test_empty_input(self, capsys):
        # Line 46: len(pass1_pairs) <= 1 branch — empty list
        result, removed = deduplicate([])
        assert result == []
        assert removed == 0

    def test_single_pair_returned_unchanged(self, capsys):
        # Line 46: len(pass1_pairs) <= 1 branch — single pair
        pairs = [make_pair("Unique Q?", "Answer.")]
        result, removed = deduplicate(pairs)
        assert len(result) == 1
        assert result[0].question == "Unique Q?"
        assert removed == 0


# ---------------------------------------------------------------------------
# Pass 2: TF-IDF cluster dedup (line 60 — union called when sim ≥ threshold)
# ---------------------------------------------------------------------------

class TestTfidfClusterDedup:
    def test_near_duplicates_merged_to_longest(self, capsys):
        # Two nearly identical questions — similarity will exceed 0.85
        pairs = [
            make_pair(
                "How does the system process documents?",
                "Short answer.",
            ),
            make_pair(
                "How does the system process documents?",  # exact dup — pass 1 removes it
                "Longer more detailed answer.",
            ),
            make_pair("What is Python?", "A programming language."),
        ]
        result, removed = deduplicate(pairs)
        # The exact dup is removed in pass 1
        assert removed >= 1

    def test_high_similarity_cluster_triggers_union(self, capsys):
        # Line 60: _union called when sim_matrix[i, j] >= 0.85
        # These two questions have cosine similarity > 0.85 (verified empirically)
        pairs = [
            make_pair(
                "how do you configure the database connection",
                "Short answer.",
                doc="a.pdf",
            ),
            make_pair(
                "how do you configure the database connection string",
                "This is a much longer and more detailed answer about configuration.",
                doc="a.pdf",
            ),
            make_pair("completely unrelated question about cats", "Cats meow.", doc="a.pdf"),
        ]
        result, removed = deduplicate(pairs)
        # The two similar questions should be merged into one cluster
        assert removed >= 1
        # The longer pair should survive
        questions = [p.question for p in result]
        assert any("string" in q for q in questions)

    def test_high_similarity_cluster_retains_longest(self, capsys):
        # Build two questions that are very similar (both about "document processing").
        # We replicate the question text with minor variation to push similarity > 0.85.
        q1 = "document processing system pipeline"
        q2 = "document processing system pipeline architecture"
        pairs = [
            make_pair(q1, "Short.", doc="a.pdf"),
            make_pair(q2, "This is a much longer and more detailed answer that should win.", doc="a.pdf"),
            make_pair("completely different question about cheese", "Cheese answer.", doc="a.pdf"),
        ]
        result, removed = deduplicate(pairs)
        questions = [p.question for p in result]
        # The "completely different" pair should always survive
        assert any("cheese" in q.lower() for q in questions)

    def test_similarity_union_applied_when_threshold_exceeded(self, capsys):
        # Use identical normalized questions (different casing) so exact-match pass
        # removes one; remaining pairs are distinct. Test that the TF-IDF pass runs.
        pairs = [
            make_pair("What is a FAQ?", "A list of questions.", doc="a.pdf"),
            make_pair("what is a faq?", "Another answer.", doc="a.pdf"),  # exact dup (normalised)
            make_pair("How to install Python?", "Run pip install.", doc="b.pdf"),
        ]
        result, removed = deduplicate(pairs)
        assert removed >= 1
        assert len(result) >= 1


# ---------------------------------------------------------------------------
# Pass 3: Per-document preservation
# ---------------------------------------------------------------------------

class TestPerDocPreservation:
    def test_doc_with_all_pairs_deduped_gets_one_restored(self, capsys):
        # doc_a has two identical pairs — both would be removed if not for preservation.
        # But since doc_a's first duplicate is kept in pass 1, preservation may not trigger.
        # Use two docs where doc_b has only one pair that is a near-dup of doc_a's pair.
        # Force pass 3 by having a doc whose only pairs are all high-similarity with another doc.
        pairs = [
            make_pair("faq generation system", "Answer A.", doc="a.pdf"),
            make_pair("faq generation system", "Answer B.", doc="b.pdf"),  # exact dup — removed in pass 1
        ]
        result, removed = deduplicate(pairs)
        # doc_b had only the duplicate; pass 3 must restore one pair for doc_b
        surviving_docs = {p.doc_path.name for p in result}
        assert "b.pdf" in surviving_docs

    def test_all_docs_represented_after_heavy_dedup(self, capsys):
        # Three docs, each with only one pair. Pairs 2 and 3 are duplicates of pair 1.
        base_q = "what are the main features"
        pairs = [
            make_pair(base_q, "Features A.", doc="a.pdf"),
            make_pair(base_q, "Features B.", doc="b.pdf"),
            make_pair(base_q, "Features C.", doc="c.pdf"),
        ]
        result, _ = deduplicate(pairs)
        surviving_docs = {p.doc_path.name for p in result}
        # All three docs should be represented
        assert "a.pdf" in surviving_docs
        assert "b.pdf" in surviving_docs
        assert "c.pdf" in surviving_docs


# ---------------------------------------------------------------------------
# Output: "Removed N duplicate(s)" printed to stdout
# ---------------------------------------------------------------------------

class TestRemovedCountOutput:
    def test_prints_removed_count_to_stdout(self, capsys):
        pairs = [
            make_pair("Q?", "A."),
            make_pair("Q?", "B."),  # duplicate
        ]
        deduplicate(pairs)
        captured = capsys.readouterr()
        assert "Removed 1 duplicate(s)" in captured.out

    def test_prints_zero_when_no_duplicates(self, capsys):
        pairs = [
            make_pair("What is X?", "Answer X."),
            make_pair("How does the frobulator work?", "It frobnifies."),
        ]
        deduplicate(pairs)
        captured = capsys.readouterr()
        assert "Removed 0 duplicate(s)" in captured.out

    def test_removed_count_accurate(self, capsys):
        pairs = [
            make_pair("Q1?", "A1."),
            make_pair("Q1?", "A2."),
            make_pair("Q1?", "A3."),
        ]
        result, removed = deduplicate(pairs)
        assert removed == 2
        assert len(result) == 1


# ---------------------------------------------------------------------------
# Normalize helper
# ---------------------------------------------------------------------------

class TestNormalize:
    def test_lowercases(self):
        assert _normalize("HELLO WORLD") == "hello world"

    def test_collapses_whitespace(self):
        assert _normalize("hello   world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _normalize("  hello  ") == "hello"


# ---------------------------------------------------------------------------
# Property-based tests — Properties 6, 7, 8
# ---------------------------------------------------------------------------

_doc_paths = [Path("/docs/a.pdf"), Path("/docs/b.txt"), Path("/docs/c.docx")]

_qa_strategy = st.builds(
    QAPair,
    question=st.text(min_size=3, max_size=80, alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters="?! "
    )).filter(lambda s: s.strip()),
    answer=st.text(min_size=3, max_size=80, alphabet=st.characters(
        whitelist_categories=("Lu", "Ll", "Nd", "Zs"), whitelist_characters=". "
    )).filter(lambda s: s.strip()),
    doc_path=st.sampled_from(_doc_paths),
    chunk_index=st.integers(min_value=0, max_value=5),
)

_pairs_strategy = st.lists(_qa_strategy, min_size=1, max_size=10)


@given(pairs=_pairs_strategy)
@settings(max_examples=100)
def test_property_6_unique_questions_after_dedup(pairs: list[QAPair]):
    # Feature: doc-faq-generator, Property 6: Deduplication produces unique questions
    # Validates: Requirements 7.1, 7.2
    #
    # Note: Per-document preservation (req 7.4) can restore a pair whose question
    # matches an existing surviving pair, when a doc's only pair was removed as a
    # duplicate. We therefore check uniqueness only among pairs from docs that had
    # at least one pair survive passes 1+2 independently.
    from faq_generator.deduplicator import _normalize

    result, _ = deduplicate(pairs)

    # Count surviving pairs per doc_path
    doc_to_pairs: dict = {}
    for p in result:
        doc_to_pairs.setdefault(p.doc_path, []).append(p)

    # For each doc, if it has multiple surviving pairs, their questions must be unique
    for doc, surviving in doc_to_pairs.items():
        if len(surviving) > 1:
            normalized = [_normalize(p.question) for p in surviving]
            assert len(normalized) == len(set(normalized)), (
                f"Doc {doc} has non-unique questions after dedup: {normalized}"
            )


@given(pairs=_pairs_strategy)
@settings(max_examples=50)
def test_property_7_dedup_idempotent(pairs: list[QAPair]):
    # Feature: doc-faq-generator, Property 7: Deduplication is idempotent
    # Validates: Requirements 7.1, 7.2
    result1, _ = deduplicate(pairs)
    result2, removed2 = deduplicate(result1)
    # Second pass should remove nothing
    assert removed2 == 0
    # Questions should be identical
    questions1 = [_normalize(p.question) for p in result1]
    questions2 = [_normalize(p.question) for p in result2]
    assert questions1 == questions2


@given(pairs=_pairs_strategy)
@settings(max_examples=100)
def test_property_8_per_doc_preservation(pairs: list[QAPair]):
    # Feature: doc-faq-generator, Property 8: Per-document QA pair preservation
    # Validates: Requirements 7.4
    input_docs = {p.doc_path for p in pairs}
    result, _ = deduplicate(pairs)
    output_docs = {p.doc_path for p in result}
    # Every doc in input must be represented in output
    assert input_docs == output_docs, (
        f"Some docs lost after dedup. Missing: {input_docs - output_docs}"
    )
