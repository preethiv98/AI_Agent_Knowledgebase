# Implementation Plan: doc-faq-generator

## Overview

Implement a Python CLI tool that discovers documents in a folder, extracts text, splits it into overlapping chunks, generates Q&A pairs via the Anthropic Claude API, deduplicates the results, and writes the final FAQ to `output/faq.md`. The pipeline is built as a `faq_generator/` package with a `main.py` orchestrator.

## Tasks

- [x] 1. Scaffold project structure and shared data models
  - Create the `faq_generator/` package directory with `__init__.py`
  - Create `faq_generator/models.py` defining the `QAPair`, `DocChunkResult`, and `ProcessingStats` dataclasses exactly as specified in the design
  - Create `pyproject.toml` (or `setup.py`) declaring the package entry point `faq-generator = main:main` and listing all dependencies: `anthropic`, `python-dotenv`, `pdfplumber`, `python-docx`, `scikit-learn`, `pytest`, `hypothesis`, `pytest-cov`
  - Create a `tests/` directory with an empty `__init__.py` and a `conftest.py` placeholder
  - _Requirements: 1.1_

- [x] 2. Implement `faq_generator/estimator.py`
  - [x] 2.1 Implement the `EstimateResult` dataclass in `faq_generator/models.py`
    - Add `EstimateResult(total_chunks: int, per_doc: dict[Path, int])` to the existing models file
  - [x] 2.2 Implement `estimate_chunks(paths: list[Path], max_words: int = 3_000, overlap_words: int = 200) -> EstimateResult`
    - For each path, call `read_document(path)` then `chunk_text(text)` to get the actual chunk list
    - If `read_document` returns `None`, contribute 0 to the total for that path
    - Return `EstimateResult(total_chunks=sum, per_doc={path: count, ...})`
    - _Requirements: (new pre-flight requirement — see design)_

  - [ ]* 2.3 Write unit tests for `estimate_chunks`
    - Mock `read_document` and `chunk_text`; test: single readable file, mix of readable and unreadable files (None return), zero-chunk file (empty text), total_chunks is sum of per-doc counts, per_doc keys match input paths

- [x] 3. Implement `faq_generator/discoverer.py`
  - [x] 3.1 Implement `discover_documents(folder, max_depth=10, max_files=10_000) -> list[Path]`
    - Use `os.walk` with a depth counter derived from the root path to enforce max depth
    - Filter for `.pdf`, `.docx`, `.txt` extensions (case-insensitive)
    - Collect all matching paths, sort alphabetically by full string path
    - If total count exceeds `max_files`, log a `WARNING` and truncate to the first `max_files`
    - _Requirements: 2.1, 2.7_

  - [ ]* 3.2 Write unit tests for `discover_documents`
    - Use `tmp_path` pytest fixture to create real directory trees
    - Test: correct extensions found, non-matching skipped, depth limit enforced at exactly 10, depth limit enforced at depth 11, 10k cap triggers warning and truncation, alphabetical sort order
    - _Requirements: 2.1, 2.7_

- [x] 4. Implement `faq_generator/reader.py`
  - [x] 4.1 Implement `read_document(path: Path) -> str | None`
    - Check `path.stat().st_size` and skip with a `WARNING` log if > 100 MB
    - Dispatch by extension: `.txt` → `open(path, encoding='utf-8')`, `.pdf` → `pdfplumber`, `.docx` → `python-docx` paragraph join
    - Catch `UnicodeDecodeError` on `.txt` files: log warning with path + "encoding failure", return `None`
    - Catch all other `Exception` on any file: log warning with path + reason, return `None`
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

  - [ ]* 4.2 Write unit tests for `read_document`
    - Use `tmp_path` and mock/fixture files; mock `pdfplumber` and `python-docx` for PDF/DOCX paths
    - Test: TXT happy path, TXT UTF-8 error returns None + warning, PDF happy path, DOCX happy path, file > 100 MB skipped + warning, filesystem error returns None + warning
    - _Requirements: 2.2, 2.3, 2.4, 2.5, 2.6_

- [x] 5. Implement `faq_generator/chunker.py`
  - [x] 5.1 Implement `chunk_text(text: str, max_words: int = 3_000, overlap_words: int = 200) -> list[str]`
    - Tokenize by `text.split()` to get word list
    - If `len(words) == 0`, return `[]`
    - If `len(words) <= max_words`, return `[text]` (single chunk, no overlap)
    - Otherwise: accumulate up to `max_words` words, scan the last 100 words for a sentence-boundary word (ends with `.`, `!`, or `?`); split there if found, else split at exactly `max_words`; prepend `overlap_words` words from the prior chunk to each subsequent chunk; repeat until exhausted
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

  - [ ]* 5.2 Write property test for `chunk_text` — Property 1: Chunk size bounded
    - **Property 1: Chunk size bounded**
    - **Validates: Requirements 4.1, 4.2**
    - Use `hypothesis.strategies.text()` to generate random non-empty strings; assert every chunk has `len(chunk.split()) <= 3000`

  - [ ]* 5.3 Write property test for `chunk_text` — Property 2: Chunking is lossless
    - **Property 2: Chunking is lossless**
    - **Validates: Requirements 4.1, 4.2, 4.3, 4.4**
    - Generate random text; reconstruct original word sequence by taking all words from chunk 0 and appending the non-overlap portion (words from index `overlap_words` onward) of each subsequent chunk; assert reconstructed words equal original `text.split()`

  - [ ]* 5.4 Write property test for `chunk_text` — Property 3: Chunk structural invariants
    - **Property 3: Chunk structural invariants**
    - **Validates: Requirements 4.3, 4.4**
    - Generate short texts (≤ 3,000 words): assert result is a single-element list containing the unmodified original text
    - Generate long texts (> 3,000 words): assert the first `overlap_words` words of chunk `i` (`i > 0`) equal the last `overlap_words` words of chunk `i − 1`

  - [ ]* 5.5 Write unit tests for `chunk_text`
    - Test: empty/whitespace-only input returns `[]`, text ≤ 3000 words returns single chunk, sentence-boundary split is respected, fallback hard-split at 3000 words when no boundary in last 100, overlap prepend correctness
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_

- [x] 6. Checkpoint — Core pipeline data layer complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Implement `faq_generator/generator.py`
  - [x] 7.1 Implement `generate_qa_pairs(chunk: str, chunk_id: str, api_key: str) -> list[QAPair]`
    - Instantiate `anthropic.Anthropic(api_key=api_key)`
    - Build the prompt as specified in the design (system message + user message embedding chunk text)
    - Call `client.messages.create(model="claude-sonnet-4-5", ...)` and capture the text response
    - Parse response with `json.loads()`; filter out entries missing `question`/`answer` or where either is empty/whitespace
    - On HTTP 429: sleep 10 s, retry up to 3 times; after exhaustion log error with `chunk_id` and return `[]`
    - On any other `anthropic.APIError` or `json.JSONDecodeError`: log error with `chunk_id`, return `[]`
    - If fewer than 3 valid pairs extracted: log a warning with `chunk_id` and count
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

  - [ ]* 7.2 Write property test for `generate_qa_pairs` — Property 4: QA pair fields non-empty
    - **Property 4: QA pair fields non-empty after parsing**
    - **Validates: Requirements 5.2, 5.3**
    - Generate plausible JSON arrays mixing valid entries and malformed entries (missing keys, empty strings, whitespace-only values) using `hypothesis`; mock the Anthropic client to return these arrays; assert every `QAPair` in output has non-empty `.question` and `.answer`

  - [ ]* 7.3 Write unit tests for `generate_qa_pairs`
    - Mock `anthropic.Anthropic`; test: successful parse returns correct `QAPair` list, malformed entries discarded, retry on 429 (sleep called, retried 3 times then returns `[]`), non-429 API error returns `[]` + logs, JSON parse error returns `[]` + logs, fewer than 3 pairs logs warning
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

- [x] 8. Implement `faq_generator/merger.py`
  - [x] 8.1 Implement `merge_qa_pairs(doc_chunks: list[DocChunkResult]) -> list[QAPair]`
    - Sort input by `(str(result.doc_path), result.chunk_index)`
    - Concatenate all `result.pairs` lists in sorted order and return the flat list
    - _Requirements: 6.1, 6.2, 6.3_

  - [ ]* 8.2 Write property test for `merge_qa_pairs` — Property 5: Merger preserves all pairs in deterministic order
    - **Property 5: Merger preserves all pairs in deterministic order**
    - **Validates: Requirements 6.1, 6.2, 6.3**
    - Generate lists of `DocChunkResult` objects using `hypothesis` (random doc paths, chunk indices, QA pairs); shuffle the list; assert output contains all pairs and is ordered by `(str(doc_path), chunk_index)` regardless of input permutation

  - [ ]* 8.3 Write unit tests for `merge_qa_pairs`
    - Test: single document single chunk, multiple documents multiple chunks ordered correctly, input already in order unchanged, reverse-order input reordered, empty input returns empty list
    - _Requirements: 6.1, 6.2, 6.3_

- [x] 9. Implement `faq_generator/deduplicator.py`
  - [x] 9.1 Implement `deduplicate(pairs: list[QAPair], similarity_threshold: float = 0.85) -> tuple[list[QAPair], int]`
    - **Pass 1 — Exact match**: normalize each question (lowercase + collapse whitespace); keep only the first occurrence using a `seen: set[str]`
    - **Pass 2 — TF-IDF cluster pass**: fit `TfidfVectorizer` on all remaining normalized questions; compute the full pairwise `cosine_similarity` matrix; use union-find (or equivalent) to group all pairs whose pairwise similarity ≥ `threshold` into clusters — collecting the entire cluster before any selection; from each cluster retain the single `QAPair` with the greatest `len(question) + len(answer)`, breaking ties by earliest position in the merged input order
    - **Pass 3 — Per-document preservation**: identify source `doc_path` values with no surviving pairs; for each, restore the `QAPair` with the greatest `len(question) + len(answer)` from the original input, breaking ties by earliest position in the merged input order
    - Return `(surviving_pairs, removed_count)` and print `Removed N duplicate(s)` to stdout
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

  - [ ]* 9.2 Write property test for `deduplicate` — Property 6: Deduplication produces unique questions
    - **Property 6: Deduplication produces unique questions**
    - **Validates: Requirements 7.1, 7.2**
    - Generate lists of `QAPair` objects with varying questions (including intentional exact and near-duplicates); assert no two output questions are identical after normalization, and no two output questions have TF-IDF cosine similarity > 0.85

  - [ ]* 9.3 Write property test for `deduplicate` — Property 7: Deduplication is idempotent
    - **Property 7: Deduplication is idempotent**
    - **Validates: Requirements 7.1, 7.2**
    - Generate lists of `QAPair` objects; apply `deduplicate` twice; assert questions in second output equal questions in first output and `removed_count` on second call is 0

  - [ ]* 9.4 Write property test for `deduplicate` — Property 8: Per-document QA pair preservation
    - **Property 8: Per-document QA pair preservation**
    - **Validates: Requirements 7.4**
    - Generate lists of `QAPair` objects with at least one pair per distinct `doc_path`; assert every `doc_path` present in the input has at least one `QAPair` in the output

  - [ ]* 9.5 Write unit tests for `deduplicate`
    - Test: exact-match duplicates removed (first occurrence kept), full cluster formed before selection (a later longer pair beats an earlier shorter one), near-duplicate cluster retains the longest pair across the whole cluster, per-document preservation restores a pair when all are deduped, `removed_count` is accurate, `Removed N duplicate(s)` printed to stdout, empty input returns empty list
    - _Requirements: 7.1, 7.2, 7.3, 7.4_

- [x] 10. Checkpoint — Pipeline stages complete
  - Ensure all tests pass, ask the user if questions arise.

- [x] 11. Implement `faq_generator/writer.py`
  - [x] 11.1 Implement `write_faq(pairs: list[QAPair], output_path: Path) -> None`
    - Create parent directories with `output_path.parent.mkdir(parents=True, exist_ok=True)`
    - Open output file for writing (overwrite if exists)
    - Write `# FAQ\n\n` as the opening heading
    - Iterate pairs, inserting a `### <basename>\n\n` heading whenever `pair.doc_path` changes
    - Write each pair as `## <question>\n\n<answer>\n\n`
    - Raise `OSError` on write failure (let `main.py` catch and handle it)
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

  - [ ]* 11.2 Write property test for `write_faq` — Property 9: Output Markdown contains every surviving QA pair
    - **Property 9: Output Markdown contains every surviving QA pair**
    - **Validates: Requirements 8.3, 8.4, 8.5**
    - Generate lists of `QAPair` objects using `hypothesis`; call `write_faq` to a temp path; read the output and assert every `question` and `answer` appears in the text, and every document `basename` appears as a `###` heading preceding its pairs

  - [ ]* 11.3 Write unit tests for `write_faq`
    - Test: `# FAQ` heading present, `###` headings group by document basename, group heading inserted only on doc change, `##` question headings and answer paragraphs formatted correctly, `output/` directory created if absent, existing file overwritten, `OSError` propagated
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 8.7_

- [x] 12. Implement `main.py` — CLI entry point and orchestrator
  - [x] 12.1 Implement argument parsing and validation
    - Use `argparse` with `folder_path` as a required positional argument, `--yes` / `-y` boolean flag, and `--confirm-threshold N` (default 50) integer option
    - If missing: print `Usage: faq-generator <folder_path>` and exit with code 2
    - Validate that the path exists (exit code 1 with `Error: path '<path>' not found`) and is a directory (exit code 1 with `Error: '<path>' is not a directory`)
    - _Requirements: 1.1, 1.2, 1.3, 1.4_

  - [x] 12.2 Implement `.env` loading and API key validation
    - Call `load_dotenv()` (with `override=False`) and then read `os.environ.get("ANTHROPIC_API_KEY")`
    - If `.env` file absent: print `Error: .env file not found in working directory` and exit non-zero
    - If key absent in `.env`: print `Error: ANTHROPIC_API_KEY not found in .env file` and exit non-zero
    - If key is empty string: print `Error: ANTHROPIC_API_KEY is empty` and exit non-zero
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [x] 12.3 Implement orchestration loop and progress reporting
    - Call `discover_documents`; if result is empty, print `No supported documents found in '<path>'` and exit code 1
    - Call `estimate_chunks(paths)` and print: `Estimated API calls: <N>  (<file1 → k, file2 → k, ...>)`
    - If `total_chunks > confirm_threshold` and `--yes` not set: prompt `This will make <N> API calls. Continue? [y/N]:`, read stdin; if answer is not `y`/`yes` (case-insensitive), print `Aborted.` and exit 3
    - For each document: print `Processing: <filename>`, call `read_document`, skip if `None`, call `chunk_text`, skip if empty chunks
    - For each chunk: call `generate_qa_pairs`, print `  Chunk <i>/<n> done`, accumulate `DocChunkResult`
    - Call `merge_qa_pairs`, then `deduplicate` (which prints `Removed N duplicate(s)`)
    - Call `write_faq`; catch `OSError`, print error with path + reason, exit non-zero
    - Print final summary:
      ```
      Done.
      Documents processed: <N>
      QA pairs generated:  <N>
      Duplicates removed:  <N>
      Output:              output/faq.md
      ```
    - _Requirements: 1.5, 9.1, 9.2, 9.3_

  - [ ]* 12.4 Write unit tests for `main.py` validation paths
    - Mock filesystem and `load_dotenv`; test each exit-code path: missing arg (exit 2), path not found (exit 1), path is file (exit 1), no documents found (exit 1), missing `.env` (non-zero exit), missing API key (non-zero exit), empty API key (non-zero exit), user declines confirmation (exit 3), --yes flag bypasses prompt, estimate below threshold proceeds without prompt
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 13. Write integration tests
  - [x] 13.1 Write integration tests for the full pipeline
    - Create a `tests/fixtures/` directory with 3–5 small real `.txt` and `.docx` files
    - Mock the Anthropic API with `unittest.mock.patch` returning a fixed valid JSON array of QA pairs
    - Test 1: full pipeline produces `output/faq.md` beginning with `# FAQ`
    - Test 2: every fixture document's basename appears as a `###` heading in the output
    - Test 3: summary printed to stdout matches the actual QA pair and duplicate counts
    - Test 4: folder with no supported documents exits with code 1
    - Test 5: missing `.env` exits with a non-zero code
    - _Requirements: 1.3, 1.5, 3.2, 8.1, 8.3, 8.4, 9.3_

- [x] 14. Final checkpoint — All tests pass and coverage target met
  - Run `pytest --cov=faq_generator --cov-report=term-missing` and confirm ≥ 90% line coverage across all non-entry-point modules
  - Ensure all tests pass, ask the user if questions arise.

- [x] 15. Write README
  - Create `README.md` documenting: prerequisites, installation (`pip install -e .`), `.env` setup, usage (`faq-generator <folder_path>`), output location, and a short description of the pipeline stages

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP delivery
- Each task references specific requirements for traceability
- Property-based tests use Hypothesis with `settings(max_examples=100)` and a comment referencing the design property number
- Unit tests use `pytest` with `tmp_path` and `unittest.mock` for isolation
- The `faq_generator/models.py` module is shared by all other modules — scaffold it first
- Checkpoints at tasks 6, 10, and 14 ensure incremental validation before moving to the next stage
- `main.py` is at the repository root; all other source files are under `faq_generator/`

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1"] },
    { "id": 1, "tasks": ["2.2", "3.1", "4.1", "5.1"] },
    { "id": 2, "tasks": ["2.3", "3.2", "4.2", "5.2", "5.3", "5.4", "5.5"] },
    { "id": 3, "tasks": ["7.1", "8.1", "9.1", "11.1"] },
    { "id": 4, "tasks": ["7.2", "7.3", "8.2", "8.3", "9.2", "9.3", "9.4", "9.5", "11.2", "11.3"] },
    { "id": 5, "tasks": ["12.1", "12.2"] },
    { "id": 6, "tasks": ["12.3"] },
    { "id": 7, "tasks": ["12.4"] },
    { "id": 8, "tasks": ["13.1"] }
  ]
}
```
