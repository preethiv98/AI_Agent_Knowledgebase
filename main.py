"""main.py — CLI entry point and orchestrator for doc-faq-generator."""

import argparse
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from faq_generator.chunker import chunk_text
from faq_generator.deduplicator import deduplicate
from faq_generator.discoverer import discover_documents
from faq_generator.estimator import estimate_chunks
from faq_generator.generator import generate_qa_pairs
from faq_generator.merger import merge_qa_pairs
from faq_generator.models import DocChunkResult, QAPair
from faq_generator.reader import read_document
from faq_generator.writer import write_faq

# ---------------------------------------------------------------------------
# Logging — configured at module level so it is active before main() runs.
# Progress messages go to stdout via print(); log records go to stderr.
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    """Return the configured argument parser."""
    parser = argparse.ArgumentParser(
        prog="faq-generator",
        description="Generate a FAQ from a folder of documents using the Anthropic Claude API.",
        # Suppress the default usage so we can print our own on missing args.
        add_help=True,
    )
    parser.add_argument(
        "folder_path",
        metavar="folder_path",
        help="Path to the folder containing PDF, DOCX, and/or TXT files.",
    )
    parser.add_argument(
        "--yes", "-y",
        action="store_true",
        default=False,
        help="Skip the confirmation prompt when the estimated API call count exceeds the threshold.",
    )
    parser.add_argument(
        "--confirm-threshold",
        metavar="N",
        type=int,
        default=50,
        help="Chunk count above which confirmation is required (default: 50).",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate CLI arguments.

    Exits with code 2 if no folder_path is provided, or code 1 if the path
    does not exist or is not a directory.
    """
    parser = build_parser()

    # If no positional argument given, print custom usage and exit 2
    # argparse would normally exit with code 2 on its own, but we want a
    # specific message format.
    if argv is not None:
        args_to_parse = argv
    else:
        args_to_parse = sys.argv[1:]

    if not any(a for a in args_to_parse if not a.startswith("-")):
        print("Usage: faq-generator <folder_path>")
        sys.exit(2)

    args = parser.parse_args(args_to_parse)

    folder = Path(args.folder_path)

    if not folder.exists():
        print(f"Error: path '{folder}' not found")
        sys.exit(1)

    if not folder.is_dir():
        print(f"Error: '{folder}' is not a directory")
        sys.exit(1)

    return args


# ---------------------------------------------------------------------------
# .env loading and API key validation
# ---------------------------------------------------------------------------

def load_api_key() -> str:
    """Load the Anthropic API key from a .env file in the current working directory.

    Validation rules (Requirements 3.1 – 3.5):
    - If .env is absent            → print error and exit non-zero
    - If key absent in .env        → print error and exit non-zero
    - If key is present but empty  → print error and exit non-zero
    - The key is read from os.environ AFTER load_dotenv(); it is never
      accepted as a CLI argument.

    Returns
    -------
    str
        The non-empty API key string.
    """
    env_file = Path.cwd() / ".env"

    # Requirement 3.2: .env file must exist in the working directory
    if not env_file.exists():
        print("Error: .env file not found in working directory")
        sys.exit(1)

    # Load variables from .env into the environment without overriding any
    # values that may already be set (override=False per the design).
    load_dotenv(dotenv_path=env_file, override=False)

    api_key = os.environ.get("ANTHROPIC_API_KEY")

    # Requirement 3.3: key must be present in .env
    if api_key is None:
        print("Error: ANTHROPIC_API_KEY not found in .env file")
        sys.exit(1)

    # Requirement 3.4: key must not be an empty string
    if api_key == "":
        print("Error: ANTHROPIC_API_KEY is empty")
        sys.exit(1)

    return api_key


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def main() -> None:
    """Entry point. Exits with code 1 on validation errors, 2 on missing args."""
    # 12.1 — argument parsing and path validation
    args = parse_args()
    folder_path = Path(args.folder_path)

    # 12.2 — .env loading and API key validation
    api_key = load_api_key()

    # --- Step 1: Document discovery ---
    paths = discover_documents(folder_path)
    if not paths:
        print(f"No supported documents found in '{folder_path}'")
        sys.exit(1)

    # --- Step 2: Pre-flight estimate ---
    estimate = estimate_chunks(paths)
    breakdown = ", ".join(
        f"{path.name} \u2192 {count}"
        for path, count in estimate.per_doc.items()
    )
    print(f"Estimated API calls: {estimate.total_chunks}  ({breakdown})")

    # --- Step 3: Confirmation prompt ---
    if estimate.total_chunks > args.confirm_threshold and not args.yes:
        answer = input(f"This will make {estimate.total_chunks} API calls. Continue? [y/N]: ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            sys.exit(3)

    # --- Step 4: Processing loop ---
    doc_chunk_results: list[DocChunkResult] = []
    documents_processed = 0
    qa_pairs_generated = 0

    for path in paths:
        print(f"Processing: {path.name}")

        text = read_document(path)
        if text is None:
            continue

        chunks = chunk_text(text)
        if not chunks:
            continue

        n = len(chunks)
        for i, chunk in enumerate(chunks, start=1):
            pairs: list[QAPair] = generate_qa_pairs(
                chunk,
                chunk_id=f"{path.name}:chunk{i}",
                api_key=api_key,
            )
            # Set doc_path and chunk_index on each returned pair
            for pair in pairs:
                pair.doc_path = path
                pair.chunk_index = i - 1

            print(f"  Chunk {i}/{n} done")

            doc_chunk_results.append(
                DocChunkResult(
                    doc_path=path,
                    chunk_index=i - 1,
                    pairs=pairs,
                )
            )
            qa_pairs_generated += len(pairs)

        documents_processed += 1

    # --- Step 5: Merge + deduplicate ---
    merged = merge_qa_pairs(doc_chunk_results)
    deduped, duplicates_removed = deduplicate(merged)

    # --- Step 6: Write output ---
    output_path = Path("output/faq.md")
    try:
        write_faq(deduped, output_path)
    except OSError as exc:
        print(f"Error: could not write output file '{output_path}': {exc.strerror}")
        sys.exit(1)

    # --- Step 7: Final summary ---
    print("Done.")
    print(f"Documents processed: {documents_processed}")
    print(f"QA pairs generated:  {qa_pairs_generated}")
    print(f"Duplicates removed:  {duplicates_removed}")
    print(f"Output:              output/faq.md")


if __name__ == "__main__":
    main()
