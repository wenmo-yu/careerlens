from io import BytesIO
from pathlib import Path

import pymupdf
from docx import Document

SUPPORTED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}


def extract_text(filename: str, content: bytes) -> tuple[str, dict]:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}")

    if suffix == ".pdf":
        with pymupdf.open(stream=content, filetype="pdf") as document:
            pages = [page.get_text("text") for page in document]
        return "\n\n".join(pages), {"page_count": len(pages)}

    if suffix == ".docx":
        document = Document(BytesIO(content))
        paragraphs = [paragraph.text for paragraph in document.paragraphs]
        return "\n".join(paragraphs), {"paragraph_count": len(paragraphs)}

    try:
        return content.decode("utf-8-sig"), {}
    except UnicodeDecodeError as exc:
        raise ValueError("Text files must use UTF-8 encoding") from exc

