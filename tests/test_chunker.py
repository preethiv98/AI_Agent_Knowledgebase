"""Unit and property-based tests for faq_generator.chunker.chunk_text."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from faq_generator.chunker import chunk_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_words(n: int, sentence_every: int = 0) -> str:
    """Return a string of *n* whitespace-separated tokens.

    If sentence_every > 0, every sentence_every-th word ends with '.'.
    """
    words = []
    for i in range(n):
        if sentence_every > 0 and (i + 1) % sentence_every == 0:
            words.append(f"word{i}.")
        else:
            words.append(f"word{i}")
    return " ".join(words)


# ---------------------------------------------------------------------------
# Unit tests — Task 5.5
# ---------------------------------------------------------------------------

class TestChunkTextEdgeCases:
    def test_empty_string_returns_empty_list(self):
        assert chunk_text("") == []

    def test_whitespace_only_returns_empty_list(self):
        assert chunk_text("   \t\n  ") == []

    def test_single_word_returns_single_chunk(self):
        result = chunk_text("hello")
        assert result == ["hello"]

    def test_exactly_max_words_returns_single_chunk(self):
        text = make_words(3_000)
        result = chunk_text(text)
        assert len(result) == 1
        assert result[0] == text

    def test_one_word_under_max_returns_single_chunk(self):
        text = make_words(2_999)
        result = chunk_text(text)
        assert len(result) == 1
        assert result[0] == text


class TestChunkTextSplit:
    def test_text_over_max_produces_multiple_chunks(self):
        text = make_words(6_000)
        result = chunk_text(text)
        assert len(result) >= 2

    def test_each_chunk_has_at_most_max_words(self):
        text = make_words(9_000)
        for chunk in chunk_text(text):
            assert len(chunk.split()) <= 3_000

    def test_hard_split_at_max_words_when_no_boundary(self):
        # All words are plain tokens — no sentence boundary anywhere.
        text = " ".join(["word"] * 3_500)
        chunks = chunk_text(text)
        # First chunk must contain at most 3000 words.
        assert len(chunks[0].split()) <= 3_000

    def test_sentence_boundary_split_respected(self):
        # Build a 3100-word string where word 2990 ends with '.'
        words = [f"w{i}" for i in range(3_100)]
        words[2_989] = "boundary."
        text = " ".join(words)
        chunks = chunk_text(text)
        first_chunk_words = chunks[0].split()
        # The split should occur at or after the boundary word (index 2989),
        # so the first chunk should end with "boundary."
        assert first_chunk_words[-1] == "boundary."
        # And should be ≤ 3000 words.
        assert len(first_chunk_words) <= 3_000

    def test_rightmost_boundary_used_in_last_100_words(self):
        # Place two boundaries in the last 100 words of a 3000-word window.
        words = [f"w{i}" for i in range(3_050)]
        words[2_940] = "first."   # earlier boundary in scan window
        words[2_980] = "second."  # later (rightmost) boundary
        text = " ".join(words)
        chunks = chunk_text(text)
        first_chunk_words = chunks[0].split()
        # Rightmost boundary should be used — chunk ends with "second."
        assert first_chunk_words[-1] == "second."


class TestChunkTextOverlap:
    def test_overlap_prepended_to_subsequent_chunks(self):
        # 4000 words, no sentence boundaries → hard split at 3000, then
        # the second chunk starts overlap_words=200 before split point.
        text = make_words(4_000)
        words = text.split()
        chunks = chunk_text(text, max_words=3_000, overlap_words=200)
        assert len(chunks) >= 2
        # Last 200 words of chunk 0 must equal first 200 words of chunk 1.
        chunk0_words = chunks[0].split()
        chunk1_words = chunks[1].split()
        assert chunk0_words[-200:] == chunk1_words[:200]

    def test_overlap_correctness_with_custom_params(self):
        # Small max_words / overlap for easy inspection.
        text = make_words(500)
        words = text.split()
        chunks = chunk_text(text, max_words=100, overlap_words=20)
        assert len(chunks) >= 2
        chunk0_words = chunks[0].split()
        chunk1_words = chunks[1].split()
        assert chunk0_words[-20:] == chunk1_words[:20]

    def test_no_overlap_on_single_chunk(self):
        text = make_words(100)
        result = chunk_text(text, max_words=3_000, overlap_words=200)
        assert len(result) == 1
        assert result[0] == text


class TestChunkTextDegenerate:
    def test_overlap_larger_than_chunk_advances_past_split(self):
        # Line 59: guard where next_start <= start — happens when overlap_words >= split_point.
        # Use max_words=5, overlap_words=10 (overlap > window). After the first split at
        # position 5, next_start = 5 - 10 = -5, which is <= start(0), so we advance to split_point.
        text = " ".join(f"w{i}" for i in range(20))
        chunks = chunk_text(text, max_words=5, overlap_words=10)
        # Should still produce all words without infinite looping
        assert len(chunks) >= 2
        # Reconstruct: the guard fires, so each chunk starts fresh (no overlap)
        # but all words must be covered
        all_chunk_words = set()
        for chunk in chunks:
            all_chunk_words.update(chunk.split())
        original_words = set(text.split())
        assert original_words.issubset(all_chunk_words)


class TestChunkTextLossless:
    def test_all_words_present_across_chunks(self):
        """Reconstructing words by removing overlap prefixes yields the original."""
        text = make_words(7_500)
        original_words = text.split()
        chunks = chunk_text(text, max_words=3_000, overlap_words=200)

        reconstructed: list[str] = chunks[0].split()
        for chunk in chunks[1:]:
            reconstructed.extend(chunk.split()[200:])

        assert reconstructed == original_words


# ---------------------------------------------------------------------------
# Property-based tests — Tasks 5.2, 5.3, 5.4
# ---------------------------------------------------------------------------

# Strategy: generate non-empty strings by picking a word count and building
# the text deterministically, avoiding the entropy overhead of generating
# thousands of individual word strings.
_words_strategy = st.integers(min_value=1, max_value=6_000).map(
    lambda n: " ".join(f"word{i}" for i in range(n))
)


@given(text=_words_strategy)
@settings(max_examples=100)
def test_property_1_chunk_size_bounded(text: str):
    # Feature: doc-faq-generator, Property 1: Chunk size bounded
    # Validates: Requirements 4.1, 4.2
    for chunk in chunk_text(text):
        assert len(chunk.split()) <= 3_000, (
            f"Chunk has {len(chunk.split())} words, expected ≤ 3000"
        )


@given(text=_words_strategy)
@settings(max_examples=100)
def test_property_2_chunking_is_lossless(text: str):
    # Feature: doc-faq-generator, Property 2: Chunking is lossless
    # Validates: Requirements 4.1, 4.2, 4.3, 4.4
    original_words = text.split()
    chunks = chunk_text(text)

    if not chunks:
        assert original_words == []
        return

    reconstructed = chunks[0].split()
    for chunk in chunks[1:]:
        chunk_words = chunk.split()
        reconstructed.extend(chunk_words[200:])

    assert reconstructed == original_words, (
        "Reconstructed words differ from original"
    )


# Strategy for short text (≤ 3000 words)
_short_text = st.integers(min_value=1, max_value=3_000).map(
    lambda n: " ".join(f"w{i}" for i in range(n))
)

# Strategy for long text (> 3000 words).
# Build it from an integer "word count" so Hypothesis doesn't have to
# generate thousands of individual word strings (which is too slow).
_long_text = st.integers(min_value=3_001, max_value=6_000).map(
    lambda n: " ".join(f"w{i}" for i in range(n))
)


@given(text=_short_text)
@settings(max_examples=100)
def test_property_3a_short_text_single_chunk(text: str):
    # Feature: doc-faq-generator, Property 3: Chunk structural invariants (short path)
    # Validates: Requirements 4.3, 4.4
    result = chunk_text(text)
    assert len(result) == 1
    assert result[0] == text


@given(text=_long_text)
@settings(max_examples=100)
def test_property_3b_long_text_overlap_invariant(text: str):
    # Feature: doc-faq-generator, Property 3: Chunk structural invariants (long path)
    # Validates: Requirements 4.3, 4.4
    chunks = chunk_text(text)
    assert len(chunks) >= 2, "Long text should produce at least 2 chunks"

    for i in range(1, len(chunks)):
        prev_words = chunks[i - 1].split()
        curr_words = chunks[i].split()
        overlap = 200
        if len(prev_words) >= overlap and len(curr_words) >= overlap:
            assert prev_words[-overlap:] == curr_words[:overlap], (
                f"Overlap mismatch between chunk {i-1} and chunk {i}"
            )
