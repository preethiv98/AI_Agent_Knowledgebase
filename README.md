# doc-faq-generator

A Python CLI tool that reads a folder of documents (PDF, DOCX, and TXT files), sends their content to the Anthropic Claude API in manageable chunks, generates Q&A pairs from each chunk, merges and deduplicates results across all chunks and documents, and saves the final FAQ to `output/faq.md` in Markdown format.

---

## Prerequisites

- Python 3.11 or later
- pip

---

## Installation

Clone the repository and install in editable mode:

```bash
pip install -e .
```

This uses `pyproject.toml` to install the `faq-generator` command and all dependencies (`anthropic`, `python-dotenv`, `pdfplumber`, `python-docx`, `scikit-learn`).

---

## .env Setup

Create a `.env` file in the directory where you will run the tool and add your Anthropic API key:

```
ANTHROPIC_API_KEY=<your-key>
```

The tool looks for this file in the current working directory. It will exit with an error if the file is missing, the key is absent, or the key is empty.

---

## Usage

```bash
faq-generator <folder_path> [--yes] [--confirm-threshold N]
```

**Arguments**

| Argument | Description |
|---|---|
| `folder_path` | Path to the folder containing your PDF, DOCX, and/or TXT files |
| `--yes`, `-y` | Skip the confirmation prompt when the estimated API call count exceeds the threshold |
| `--confirm-threshold N` | Chunk count above which a confirmation prompt is shown (default: `50`) |

**Examples**

Run against a folder of docs, confirming when prompted:

```bash
faq-generator ./my-docs
```

Skip the confirmation prompt (useful in CI or scripts):

```bash
faq-generator ./my-docs --yes
```

Set a custom confirmation threshold:

```bash
faq-generator ./my-docs --confirm-threshold 20
```

---

## Output Location

The generated FAQ is written to:

```
output/faq.md
```

relative to the current working directory. The `output/` directory is created automatically if it does not exist. An existing `output/faq.md` is overwritten.

---

## Pipeline Stages

The tool processes documents through seven sequential stages:

1. **Discover** — Recursively scans the input folder (up to 10 levels deep) for `.pdf`, `.docx`, and `.txt` files. Results are sorted alphabetically by full path. Capped at 10,000 files.

2. **Read** — Extracts plain text from each discovered file. PDFs are processed with `pdfplumber`, DOCX files with `python-docx`, and TXT files are read as UTF-8. Files larger than 100 MB or that cannot be read are skipped with a warning.

3. **Chunk** — Splits each document's text into overlapping windows of at most 3,000 words. Splits prefer sentence boundaries (`.`, `!`, `?`) within the last 100 words of a window. Each chunk after the first includes the last 200 words of the preceding chunk as overlapping context.

4. **Generate** — Sends each chunk to the Anthropic Claude API (`claude-sonnet-4-5`) with a prompt requesting 3–10 Q&A pairs returned as a JSON array. Retries up to 3 times on rate-limit errors (HTTP 429), waiting 10 seconds between attempts.

5. **Merge** — Collects all Q&A pairs from every chunk across all documents into a single list, ordered by document name (alphabetical) then chunk index.

6. **Deduplicate** — Removes redundant questions in two passes: exact-match normalization (lowercase + collapsed whitespace), then TF-IDF cosine similarity clustering (threshold 0.85). The longest Q&A pair survives each cluster. At least one pair per source document is always preserved.

7. **Write** — Formats the surviving Q&A pairs as a Markdown file beginning with `# FAQ`, grouped by document under `###` headings, with each question as a `##` heading followed by its answer paragraph.
