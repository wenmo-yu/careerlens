"""Phase 1/B: structure-aware parsing keeps locations and stays compatible."""

import io

import pymupdf
from docx import Document

from app.ingestion.files import (
    SUPPORTED_SUFFIXES,
    extract_text,
    parse_document,
)
from app.ingestion.media import MediaExtractor, OptionalMultimodalExtractor


def _build_pdf(pages_text: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages_text:
        page = document.new_page()
        page.insert_text((72, 72), text or " ", fontsize=12)
    data = document.tobytes()
    document.close()
    return data


def test_supported_suffixes_expanded():
    assert {".pdf", ".docx", ".txt", ".md", ".csv", ".tsv", ".markdown"} <= SUPPORTED_SUFFIXES


def test_pdf_parse_keeps_page_numbers_and_content():
    raw = _build_pdf(["第一页 Python 技能", "第二页 FastAPI 项目"])
    doc = parse_document("cv.pdf", raw)
    assert doc.source_type == "pdf"
    assert doc.metadata["page_count"] == 2
    assert doc.metadata["scanned_page_count"] == 0
    assert len(doc.blocks) == 2
    assert [b.page_no for b in doc.blocks] == [1, 2]
    assert all(b.bbox is not None for b in doc.blocks)
    assert "Python" in doc.blocks[0].content
    assert "FastAPI" in doc.blocks[1].content


def test_extract_text_backward_compatible_for_pdf():
    raw = _build_pdf(["Python 与 FastAPI"])
    text, meta = extract_text("cv.pdf", raw)
    assert "Python" in text
    assert meta["page_count"] == 1
    assert "block_count" in meta


def test_docx_parse_extracts_tables_as_markdown():
    document = Document()
    document.add_paragraph("个人技能", style="Heading 1")
    document.add_paragraph("熟悉 Python")
    table = document.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "技能"
    table.cell(0, 1).text = "级别"
    table.cell(1, 0).text = "Python"
    table.cell(1, 1).text = "5"
    buffer = io.BytesIO()
    document.save(buffer)

    doc = parse_document("cv.docx", buffer.getvalue())
    types = [b.block_type for b in doc.blocks]
    assert "heading" in types
    assert "table" in types
    table_block = next(b for b in doc.blocks if b.block_type == "table")
    assert "| Python | 5 |" in table_block.content
    table_text = extract_text("cv.docx", buffer.getvalue())[0]
    assert "| Python | 5 |" in table_text


def test_csv_parse_becomes_table_block():
    raw = "技能,级别\nPython,5\nFastAPI,4\n".encode()
    doc = parse_document("skills.csv", raw)
    assert len(doc.blocks) == 1
    assert doc.blocks[0].block_type == "table"
    assert "| Python | 5 |" in doc.blocks[0].content
    assert doc.metadata["row_count"] == 3


def test_text_and_markdown_parse():
    doc = parse_document("note.md", "## 目标\n做 Agent 开发".encode())
    assert doc.blocks[0].block_type == "text"
    assert "Agent" in doc.blocks[0].content


def test_unsupported_suffix_still_rejected():
    try:
        parse_document("bad.exe", b"x")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_media_extractor_default_extract_blocks_degrades_gracefully():
    class FakeExtractor(MediaExtractor):
        def extract(self, filename, content):
            return "OCR 文本", {"extractor": "fake"}

    blocks = FakeExtractor().extract_blocks("a.png", b"x")
    assert len(blocks) == 1
    assert blocks[0]["content"] == "OCR 文本"
    assert blocks[0]["source_metadata"]["extractor"] == "fake"


def test_optional_extractor_structure_dispatch_uses_extract_blocks():
    class SpyExtractor(OptionalMultimodalExtractor):
        def _ocr_blocks(self, content):
            return [
                {
                    "content": "行一",
                    "block_type": "ocr",
                    "source_type": "image_ocr",
                    "bbox": [0, 0, 10, 10],
                    "source_metadata": {"line_index": 0},
                }
            ]

        def _asr_blocks(self, filename, content):
            return [
                {
                    "content": "你好",
                    "block_type": "asr_segment",
                    "source_type": "asr",
                    "time_start": 0.5,
                    "time_end": 1.2,
                    "source_metadata": {"extractor": "faster-whisper"},
                }
            ]

    image_blocks = SpyExtractor().extract_blocks("a.png", b"x")
    assert image_blocks[0]["bbox"] == [0, 0, 10, 10]
    audio_blocks = SpyExtractor().extract_blocks("a.mp3", b"x")
    assert audio_blocks[0]["time_start"] == 0.5
    assert audio_blocks[0]["time_end"] == 1.2
