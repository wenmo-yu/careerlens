"""Local-only parsing of user-provided HTML exports and ZIP bundles.

HY4-D: platforms such as Zhihu expose a "download my data" bundle and online
documents export HTML. This module never contacts a platform. It only turns
files the user already has into the shared ParsedDocument contract.

No bs4/lxml dependency: the standard-library HTMLParser is enough for visible
text extraction. Scripts, styles and hidden nodes are skipped so a saved page
does not turn navigation chrome into fake evidence.
"""

import re
from html.parser import HTMLParser
from io import BytesIO
from zipfile import BadZipFile, ZipFile

from app.ingestion.contract import ParsedBlock, ParsedDocument, source_fingerprint

_MAX_ZIP_BYTES = 25 * 1024 * 1024
_MAX_FILES = 200
_MAX_HTML_BYTES = 2 * 1024 * 1024
_SUPPORTED = {".html", ".htm", ".json", ".csv", ".tsv", ".txt", ".md", ".markdown"}
_SKIP_TAGS = {"script", "style", "noscript", "svg", "iframe"}
_BLOCK_TAGS = {"p", "div", "article", "section", "li", "h1", "h2", "h3", "h4", "blockquote", "tr"}


class _VisibleText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.skip_depth = 0
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.in_title = False

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self.skip_depth += 1
        elif tag == "title":
            self.in_title = True
        elif tag in _BLOCK_TAGS and self.skip_depth == 0:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self.skip_depth:
            self.skip_depth -= 1
        elif tag == "title":
            self.in_title = False

    def handle_data(self, data: str) -> None:
        if self.skip_depth:
            return
        text = data.strip()
        if not text:
            return
        if self.in_title:
            self.title_parts.append(text)
        self.parts.append(text)

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def parse_html_export(filename: str, content: bytes) -> ParsedDocument:
    """Parse one HTML file. Returns empty blocks rather than inventing text."""
    if len(content) > _MAX_HTML_BYTES:
        raise ValueError("HTML 导出文件不能超过 2 MB")
    parser = _VisibleText()
    parser.feed(content.decode("utf-8", errors="replace"))
    text = parser.text()
    blocks = [
        ParsedBlock(
            content=text,
            block_type="text",
            block_index=0,
            source_type="html_export",
            source_metadata={
                "title": " ".join(parser.title_parts),
                "filename": filename,
            },
        )
    ] if text else []
    return ParsedDocument(
        doc_id="",
        blocks=blocks,
        source_type="html_export",
        metadata={"title": " ".join(parser.title_parts), "block_count": len(blocks)},
        parse_status="parsed" if text else "empty",
    )


def _safe_member(name: str) -> bool:
    """Reject absolute paths, traversal and nested archives."""
    parts = name.replace("\\", "/").split("/")
    return (
        bool(name)
        and not name.startswith(("/", "\\"))
        and all(part not in {"..", ""} for part in parts)
        and name.lower().endswith(tuple(_SUPPORTED))
    )


def parse_export_zip(content: bytes) -> ParsedDocument:
    """Parse a user-downloaded ZIP bundle into one ParsedDocument.

    Every member is checked before reading; traversal, unsupported suffixes,
    oversized files and too many members are rejected. Order is deterministic
    so re-uploading the same bundle produces the same result.
    """
    if len(content) > _MAX_ZIP_BYTES:
        raise ValueError("ZIP 导出包不能超过 25 MB")
    try:
        archive = ZipFile(BytesIO(content))
    except BadZipFile as exc:
        raise ValueError("文件不是有效的 ZIP 导出包") from exc
    with archive:
        names = [name for name in archive.namelist() if _safe_member(name)]
        if not names:
            raise ValueError("ZIP 包内没有可解析的 HTML/JSON/CSV/TXT/Markdown 文件")
        if len(names) > _MAX_FILES:
            raise ValueError(f"ZIP 包内文件过多（>{_MAX_FILES}）")
        blocks: list[ParsedBlock] = []
        for name in sorted(names):
            raw = archive.read(name)
            if len(raw) > _MAX_HTML_BYTES:
                continue
            suffix = name.rsplit(".", 1)[-1].lower()
            if suffix in {"html", "htm"}:
                member = parse_html_export(name, raw)
            else:
                text = raw.decode("utf-8", errors="replace").strip()
                member = ParsedDocument(
                    doc_id="", source_type="text",
                    blocks=[ParsedBlock(
                        content=text, block_index=0, source_type="text",
                        source_metadata={"filename": name},
                    )] if text else [],
                )
            for offset, block in enumerate(member.blocks):
                block.block_index = len(blocks)
                block.source_metadata = {
                    **block.source_metadata,
                    "archive_member": name,
                    "member_index": offset,
                }
                blocks.append(block)
        return ParsedDocument(
            doc_id="",
            blocks=blocks,
            source_type="export_zip",
            metadata={
                "member_count": len(names),
                "fingerprint": source_fingerprint(content),
            },
            parse_status="parsed" if blocks else "empty",
        )
