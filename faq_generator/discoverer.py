"""Document discoverer — recursive folder scan with extension filter and depth/count caps."""

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt"}


def discover_documents(
    folder: Path,
    max_depth: int = 10,
    max_files: int = 10_000,
) -> list[Path]:
    """Return paths to all .pdf/.docx/.txt files under `folder`, alphabetically sorted.

    Parameters
    ----------
    folder:
        Root directory to search (must be an existing directory).
    max_depth:
        Maximum recursion depth relative to *folder* (default 10).
        Files at exactly ``max_depth`` levels below *folder* are included;
        deeper directories are skipped.
    max_files:
        If the total number of matching files exceeds this value, a WARNING is
        logged and only the first ``max_files`` paths (in alphabetical order)
        are returned.

    Returns
    -------
    list[Path]
        Sorted list of matching file paths.
    """
    collected: list[Path] = []
    root_parts = len(folder.parts)

    for dirpath, dirnames, filenames in os.walk(folder):
        current_depth = len(Path(dirpath).parts) - root_parts

        # Prune descent beyond max_depth by clearing dirnames in-place
        if current_depth >= max_depth:
            dirnames.clear()

        for filename in filenames:
            if filename.lower().endswith(tuple(_SUPPORTED_EXTENSIONS)):
                # Double-check extension properly (handles multi-dot names)
                ext = Path(filename).suffix.lower()
                if ext in _SUPPORTED_EXTENSIONS:
                    collected.append(Path(dirpath) / filename)

    collected.sort(key=str)

    if len(collected) > max_files:
        logger.warning(
            "Discovered %d files, which exceeds the limit of %d. "
            "Only the first %d files (alphabetical order) will be processed.",
            len(collected),
            max_files,
            max_files,
        )
        collected = collected[:max_files]

    return collected
