from pathlib import Path

from faq_generator.chunker import chunk_text
from faq_generator.models import EstimateResult
from faq_generator.reader import read_document


def estimate_chunks(
    paths: list[Path],
    max_words: int = 3_000,
    overlap_words: int = 200,
) -> EstimateResult:
    """Read every document, count chunks, return estimate without making any API calls.

    If read_document returns None for a path (file unreadable), that path
    contributes 0 chunks to the total.
    """
    per_doc: dict[Path, int] = {}

    for path in paths:
        text = read_document(path)
        if text is None:
            per_doc[path] = 0
        else:
            chunks = chunk_text(text, max_words, overlap_words)
            per_doc[path] = len(chunks)

    total_chunks = sum(per_doc.values())
    return EstimateResult(total_chunks=total_chunks, per_doc=per_doc)
