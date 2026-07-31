from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class QAPair:
    question: str          # non-empty question string
    answer: str            # non-empty answer string
    doc_path: Path         # originating document path (absolute)
    chunk_index: int       # 0-based chunk index within the document


@dataclass
class DocChunkResult:
    doc_path: Path         # originating document path
    chunk_index: int       # 0-based position within the document
    pairs: list[QAPair]    # QA pairs generated from this chunk (may be empty)


@dataclass
class ProcessingStats:
    documents_processed: int = 0
    qa_pairs_generated: int  = 0
    duplicates_removed: int  = 0


@dataclass
class EstimateResult:
    total_chunks: int          # total API calls that will be made
    per_doc: dict[Path, int]   # chunk count keyed by document path
