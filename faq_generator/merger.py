from faq_generator.models import DocChunkResult, QAPair


def merge_qa_pairs(doc_chunks: list[DocChunkResult]) -> list[QAPair]:
    """Flatten all QA pairs ordered by doc path (alphabetical) then chunk index."""
    sorted_chunks = sorted(doc_chunks, key=lambda r: (str(r.doc_path), r.chunk_index))
    result: list[QAPair] = []
    for chunk in sorted_chunks:
        result.extend(chunk.pairs)
    return result
