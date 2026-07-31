"""Document reader: extract plain text from PDF, DOCX, and TXT files."""

import logging
from pathlib import Path

import docx
import pdfplumber

logger = logging.getLogger(__name__)

_MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB


def read_document(path: Path) -> str | None:
    """Extract text from a PDF, DOCX, or TXT file.

    Returns the extracted text as a string, or ``None`` and logs a WARNING on
    any error (file too large, encoding problem, parse failure, etc.).
    """
    try:
        size = path.stat().st_size
    except Exception as e:
        logger.warning("%s: %s", path, e)
        return None

    if size > _MAX_FILE_SIZE:
        logger.warning("%s: file size %d bytes exceeds 100 MB limit, skipping", path, size)
        return None

    ext = path.suffix.lower()

    if ext == ".txt":
        return _read_txt(path)
    elif ext == ".pdf":
        return _read_pdf(path)
    elif ext == ".docx":
        return _read_docx(path)
    else:
        logger.warning("%s: unsupported file extension '%s'", path, ext)
        return None


def _read_txt(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        logger.warning("%s: encoding failure", path)
        return None
    except Exception as e:
        logger.warning("%s: %s", path, e)
        return None


def _read_pdf(path: Path) -> str | None:
    try:
        with pdfplumber.open(path) as pdf:
            parts = []
            for page in pdf.pages:
                text = page.extract_text()
                if text is not None:
                    parts.append(text)
        return "\n".join(parts)
    except Exception as e:
        logger.warning("%s: %s", path, e)
        return None


def _read_docx(path: Path) -> str | None:
    try:
        doc = docx.Document(path)
        return "\n".join(para.text for para in doc.paragraphs)
    except Exception as e:
        logger.warning("%s: %s", path, e)
        return None
