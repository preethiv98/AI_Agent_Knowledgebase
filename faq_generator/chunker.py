def chunk_text(text: str, max_words: int = 3_000, overlap_words: int = 200) -> list[str]:
    """Split text into overlapping, sentence-boundary-aware chunks.

    Algorithm:
    1. Tokenize by whitespace.
    2. Empty word list → return [].
    3. Word count ≤ max_words → return [text] unchanged (no overlap).
    4. Otherwise build chunks iteratively:
       - Start at word index 0.
       - Accumulate up to max_words words.
       - Scan the last 100 words of that window for the rightmost sentence
         boundary (word ending with '.', '!', or '?'); split after it if
         found, else split at exactly max_words.
       - Next chunk starts overlap_words words back from the split point.
       - Repeat until all words are consumed.
    5. Return list[str] where each chunk is ' '.join(words[start:end]).
    """
    words = text.split()

    if len(words) == 0:
        return []

    if len(words) <= max_words:
        return [text]

    chunks: list[str] = []
    start = 0

    while start < len(words):
        end = min(start + max_words, len(words))

        # If this window reaches the end of the word list, emit the final chunk
        # and stop — no need to search for a boundary.
        if end == len(words):
            chunks.append(" ".join(words[start:end]))
            break

        # Scan the last 100 words of the [start, end) window for the rightmost
        # sentence-boundary word (ending with '.', '!', or '?').
        scan_start = max(0, end - 100)
        boundary = -1
        for i in range(scan_start, end):
            if words[i][-1] in ".!?":
                boundary = i  # keep updating to get the rightmost occurrence

        if boundary != -1:
            split_point = boundary + 1  # split *after* the boundary word
        else:
            split_point = end  # hard split at max_words

        chunks.append(" ".join(words[start:split_point]))

        # Next chunk overlaps by prepending the last overlap_words words of
        # the current chunk.
        next_start = split_point - overlap_words
        # Guard against degenerate cases where overlap would push us backwards
        # past 'start' (can happen if overlap_words >= split_point - start).
        if next_start <= start:
            next_start = split_point  # no overlap; advance unconditionally

        start = next_start

    return chunks
