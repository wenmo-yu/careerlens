"""File ingestion: plain-text view (backward compatible) + structured parsing.

``extract_text`` keeps its original ``(text, metadata)`` signature for every
existing caller. ``parse_document`` is the new structure-aware entry point that
emits the shared :class:`ParsedDocument` contract (see contract.py), preserving
page / bbox / table / timestamp locations needed by later phases.
"""

import csv
import io
import zipfile
from pathlib import Path
from xml.etree import ElementTree

import pymupdf
from docx import Document
from docx.table import Table

from app.ingestion.contract import ParsedBlock, ParsedDocument
from app.ingestion.html_export import parse_export_zip, parse_html_export

SUPPORTED_SUFFIXES = {
    ".pdf",
    ".docx",
    ".txt",
    ".md",
    ".markdown",
    ".csv",
    ".tsv",
    ".xlsx",
    # HY4-D: user-provided exports, parsed locally
    ".html",
    ".htm",
    ".zip",
}

# XLSX OOXML namespaces for the standard-library reader (no openpyxl needed).
_NS_MAIN = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
_NS_REL = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"

# A page whose image coverage exceeds this ratio is treated as scanned: its
# embedded OCR text layer (if any) is not trusted. Mirrors WeKnora's
# SCAN_IMAGE_AREA_RATIO heuristic (pdf_parser.py:82).
SCAN_IMAGE_AREA_RATIO = 0.5
LOW_TEXT_IMAGE_RATIO = 0.1
SCAN_MIN_CHARS_PER_PAGE = 10


def _docx_blocks(document: Document) -> list[tuple[str, str, dict]]:
    """Return ordered (text, block_type, extra) tuples from a DOCX body."""
    blocks: list[tuple[str, str, dict]] = []
    section_path: str | None = None
    for element in document.element.body.iterchildren():
        tag = element.tag.split("}")[-1]
        if tag == "p":
            from docx.text.paragraph import Paragraph

            paragraph = Paragraph(element, document)
            text = paragraph.text.strip()
            if not text:
                continue
            style = (paragraph.style.name or "").lower()
            if "heading" in style:
                section_path = text
                blocks.append((text, "heading", {"section_path": text}))
            else:
                blocks.append((text, "text", {"section_path": section_path}))
        elif tag == "tbl":
            table = Table(element, document)
            markdown = _table_to_markdown(table)
            if markdown:
                blocks.append((markdown, "table", {"section_path": section_path}))
    return blocks


def _table_to_markdown(table: Table) -> str:
    rows: list[list[str]] = []
    for row in table.rows:
        cells = [
            cell.text.strip().replace("\n", " ").replace("|", "\\|") for cell in row.cells
        ]
        rows.append(cells)
    return _render_table(rows)


def _render_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(row) for row in rows)
    rows = [row + [""] * (width - len(row)) for row in rows]
    lines = ["| " + " | ".join(rows[0]) + " |", "| " + " | ".join(["---"] * width) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in rows[1:])
    return "\n".join(lines)


def _csv_blocks(content: bytes, delimiter: str) -> tuple[list[tuple[str, str, dict]], dict]:
    text = content.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text), delimiter=delimiter))
    rows = [row for row in rows if any(cell.strip() for cell in row)]
    if not rows:
        return [], {"row_count": 0}
    escaped = [
        [cell.strip().replace("\r", "").replace("\n", " ").replace("|", "\\|") for cell in row]
        for row in rows
    ]
    return [(_render_table(escaped), "table", {})], {"row_count": len(rows)}


def _xlsx_shared_strings(archive: zipfile.ZipFile) -> list[str]:
    """Read the shared-string table from an XLSX package."""
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    strings: list[str] = []
    for item in root.findall(f"{_NS_MAIN}si"):
        # A shared string may be split across rich-text runs (<r><t>...).
        parts = [node.text or "" for node in item.iter(f"{_NS_MAIN}t")]
        strings.append("".join(parts))
    return strings


def _xlsx_sheet_paths(archive: zipfile.ZipFile) -> list[str]:
    """List worksheet parts in workbook order via workbook.xml.rels."""
    names = archive.namelist()
    paths: list[str] = []
    rels_path = "xl/_rels/workbook.xml.rels"
    if rels_path in names:
        root = ElementTree.fromstring(archive.read(rels_path))
        relation_targets = {
            rel.get("Id"): rel.get("Target")
            for rel in root
            if (rel.get("Type") or "").endswith("/worksheet")
        }
        if "xl/workbook.xml" in names:
            workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
            for sheet in workbook.iter(f"{_NS_MAIN}sheet"):
                rid = sheet.get(f"{_NS_REL}id")
                target = relation_targets.get(rid)
                if not target:
                    continue
                candidate = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
                if candidate in names:
                    paths.append(candidate)
    if not paths:
        paths = sorted(
            n for n in names
            if n.startswith("xl/worksheets/sheet") and n.endswith(".xml")
        )
    return paths


def _xlsx_blocks(content: bytes) -> tuple[list[tuple[str, str, dict]], dict]:
    """Parse XLSX with the standard library into table blocks.

    Handles shared strings, inline strings, numeric cells, and multiple
    worksheets. Circular references and formulas are read as their cached
    value when present (``<v>``), otherwise left empty.
    """
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        shared = _xlsx_shared_strings(archive)
        raw_blocks: list[tuple[str, str, dict]] = []
        total_rows = 0
        for sheet_path in _xlsx_sheet_paths(archive):
            root = ElementTree.fromstring(archive.read(sheet_path))
            rows: list[list[str]] = []
            for row in root.iter(f"{_NS_MAIN}row"):
                cells: list[str] = []
                for cell in row.findall(f"{_NS_MAIN}c"):
                    cell_type = cell.get("t")
                    if cell_type == "inlineStr":
                        node = cell.find(f"{_NS_MAIN}is")
                        value = "".join(
                            part.text or "" for part in node.iter(f"{_NS_MAIN}t")
                        ) if node is not None else ""
                    else:
                        value_node = cell.find(f"{_NS_MAIN}v")
                        value = (
                            value_node.text
                            if value_node is not None and value_node.text
                            else ""
                        )
                        if cell_type == "s" and value:
                            index = int(value)
                            value = shared[index] if index < len(shared) else ""
                    cells.append(
                        value.strip().replace("\r", "").replace("\n", " ").replace("|", "\\|")
                    )
                if any(cells):
                    rows.append(cells)
            if rows:
                width = max(len(row) for row in rows)
                padded = [row + [""] * (width - len(row)) for row in rows]
                raw_blocks.append(
                    (_render_table(padded), "table", {"sheet": Path(sheet_path).stem})
                )
                total_rows += len(rows)
        return raw_blocks, {"row_count": total_rows, "sheet_count": len(raw_blocks)}


def _page_is_scanned(page: pymupdf.Page) -> bool:
    """Classify a page by image area coverage, not by character count alone."""
    page_area = abs(page.rect.width * page.rect.height) or 1.0
    image_area = 0.0
    for image in page.get_images(full=True):
        for rect in page.get_image_rects(image[0]):
            image_area += abs(rect.width * rect.height)
    ratio = image_area / page_area
    text_len = len(page.get_text("text").strip())
    return ratio >= SCAN_IMAGE_AREA_RATIO or (
        text_len < SCAN_MIN_CHARS_PER_PAGE and ratio >= LOW_TEXT_IMAGE_RATIO
    )


def parse_document(filename: str, content: bytes) -> ParsedDocument:
    """Parse a file into the shared structured contract.

    PDF pages are classified as text or scanned. Text pages keep per-page
    content with a page-level bbox; scanned pages become explicit OCR-pending
    blocks so the caller can schedule OCR without inventing text.
    """
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        hint = (
            " 旧版 Word .doc 暂不支持，请另存为 .docx 或导出带文字层 PDF 后重试。"
            if suffix == ".doc"
            else " 支持 PDF / Word .docx / Excel .xlsx / TXT / Markdown / CSV / TSV。"
        )
        raise ValueError(f"Unsupported file type: {suffix or 'unknown'}.{hint}")

    if suffix == ".pdf":
        blocks: list[ParsedBlock] = []
        scanned_pages: list[int] = []
        with pymupdf.open(stream=content, filetype="pdf") as document:
            page_count = len(document)
            for index, page in enumerate(document):
                page_no = index + 1
                if _page_is_scanned(page):
                    scanned_pages.append(page_no)
                    rect = page.rect
                    blocks.append(
                        ParsedBlock(
                            content="",
                            block_type="image",
                            block_index=index,
                            page_no=page_no,
                            bbox={"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1},
                            source_type="scanned_pdf_ocr",
                            source_metadata={"page": page_no, "ocr_pending": True},
                        )
                    )
                    continue
                text = page.get_text("text").strip()
                rect = page.rect
                if text:
                    blocks.append(
                        ParsedBlock(
                            content=text,
                            block_type="text",
                            block_index=index,
                            page_no=page_no,
                            bbox={"x0": rect.x0, "y0": rect.y0, "x1": rect.x1, "y1": rect.y1},
                            source_type="pdf_text_layer",
                            source_metadata={"page": page_no},
                        )
                    )
        status = "partial" if scanned_pages else "parsed"
        return ParsedDocument(
            doc_id="",
            blocks=blocks,
            source_type="pdf",
            metadata={
                "page_count": page_count,
                "scanned_page_count": len(scanned_pages),
                "scanned_pages": scanned_pages,
            },
            parse_status=status,
        )

    if suffix == ".docx":
        document = Document(io.BytesIO(content))
        raw_blocks = _docx_blocks(document)
        blocks = [
            ParsedBlock(
                content=text,
                block_type=block_type,
                block_index=index,
                section_path=extra.get("section_path"),
                source_type="docx_table" if block_type == "table" else "docx",
            )
            for index, (text, block_type, extra) in enumerate(raw_blocks)
        ]
        return ParsedDocument(
            doc_id="",
            blocks=blocks,
            source_type="docx",
            metadata={"paragraph_count": len(blocks)},
        )

    if suffix in {".html", ".htm"}:
        return parse_html_export(filename, content)

    if suffix == ".zip":
        return parse_export_zip(content)

    if suffix in {".csv", ".tsv"}:
        raw, meta = _csv_blocks(content, "\t" if suffix == ".tsv" else ",")
        blocks = [
            ParsedBlock(
                content=text,
                block_type=block_type,
                block_index=index,
                source_type="csv",
            )
            for index, (text, block_type, _) in enumerate(raw)
        ]
        return ParsedDocument(doc_id="", blocks=blocks, source_type="csv", metadata=meta)

    if suffix == ".xlsx":
        raw, meta = _xlsx_blocks(content)
        blocks = [
            ParsedBlock(
                content=text,
                block_type=block_type,
                block_index=index,
                source_type="xlsx",
                source_metadata=extra,
            )
            for index, (text, block_type, extra) in enumerate(raw)
        ]
        return ParsedDocument(doc_id="", blocks=blocks, source_type="xlsx", metadata=meta)

    # .txt / .md / .markdown
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Text files must use UTF-8 encoding") from exc
    blocks = [
        ParsedBlock(content=text.strip(), block_type="text", block_index=0, source_type="text")
    ]
    return ParsedDocument(doc_id="", blocks=blocks, source_type="text")


def extract_text(filename: str, content: bytes) -> tuple[str, dict]:
    """Backward-compatible plain-text view over the structured parser."""
    document = parse_document(filename, content)
    text = document.markdown
    if not text.strip():
        # Scanned-only PDF with no OCR text yet: keep a non-empty marker so the
        # original empty-content guard still behaves consistently.
        if document.metadata.get("scanned_page_count"):
            text = ""
    return text, {**document.metadata, "block_count": len(document.blocks)}
