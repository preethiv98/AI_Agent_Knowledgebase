from pathlib import Path

from faq_generator.models import QAPair


def write_faq(pairs: list[QAPair], output_path: Path) -> None:
    """Write the FAQ Markdown file. Raises OSError on write failure."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write("# FAQ\n\n")

        current_doc: Path | None = None
        for pair in pairs:
            if pair.doc_path != current_doc:
                current_doc = pair.doc_path
                f.write(f"### {pair.doc_path.name}\n\n")
            f.write(f"## {pair.question}\n\n{pair.answer}\n\n")
