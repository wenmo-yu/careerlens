"""Local-only parsing of user-provided HTML exports and ZIP bundles.

HY4-D: platforms such as Zhihu expose a "download my data" bundle and online
documents export HTML. This module never contacts a platform. It only turns
files the user already has into the shared ParsedDocument contract.

No bs4/lxml dependency: the standard-library HTMLParser is enough for visible
text extraction. Scripts, styles and hidden nodes are skipped so a saved page
does not turn navigation chrome into fake evidence.
"""

import re
import stat
import unicodedata
import zlib
from html.parser import HTMLParser
from io import BytesIO
from zipfile import BadZipFile, ZipFile, ZipInfo

from app.ingestion.contract import ParsedBlock, ParsedDocument, source_fingerprint

_MAX_ZIP_BYTES = 25 * 1024 * 1024
_MAX_ZIP_ENTRIES = 1000
_MAX_FILES = 200
_MAX_HTML_BYTES = 2 * 1024 * 1024
_MAX_ZIP_EXPANDED_BYTES = 32 * 1024 * 1024
_MAX_COMPRESSION_RATIO = 200
_READ_CHUNK_BYTES = 64 * 1024
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


def _zip_members(archive: ZipFile) -> list[tuple[str, ZipInfo]]:
    entries = archive.infolist()
    if len(entries) > _MAX_ZIP_ENTRIES:
        raise ValueError(f"ZIP 包内条目过多（>{_MAX_ZIP_ENTRIES}）")
    if sum(entry.file_size for entry in entries) > _MAX_ZIP_EXPANDED_BYTES:
        raise ValueError("ZIP 包内解压总量超过限制")

    names: set[str] = set()
    selected: list[tuple[str, ZipInfo]] = []
    for entry in entries:
        original = unicodedata.normalize("NFC", entry.orig_filename.replace("\\", "/"))
        name = original.removesuffix("/")
        if (
            any(part in {"", ".", ".."} or ":" in part or "\x00" in part
                for part in name.split("/"))
            or stat.S_ISLNK(entry.external_attr >> 16)
        ):
            raise ValueError("ZIP 包含无效路径或符号链接")
        key = name.casefold()
        if key in names:
            raise ValueError("ZIP 包含重复路径")
        names.add(key)
        if entry.flag_bits & 1:
            raise ValueError("ZIP 包包含加密文件")
        if original.endswith("/") or not name.lower().endswith(tuple(_SUPPORTED)):
            continue
        if entry.file_size > _MAX_HTML_BYTES:
            raise ValueError("ZIP 包内单个可解析文件不能超过 2 MB")
        if (
            entry.file_size > _READ_CHUNK_BYTES
            and entry.file_size > _MAX_COMPRESSION_RATIO * max(1, entry.compress_size)
        ):
            raise ValueError("ZIP 包内文件压缩比超过限制")
        selected.append((name, entry))
    if len(selected) > _MAX_FILES:
        raise ValueError(f"ZIP 包内可解析文件过多（>{_MAX_FILES}）")
    return sorted(selected)


def _read_zip_member(archive: ZipFile, entry: ZipInfo, remaining: int) -> bytes:
    limit = min(_MAX_HTML_BYTES, remaining)
    data = bytearray()
    with archive.open(entry) as stream:
        while chunk := stream.read(min(_READ_CHUNK_BYTES, limit - len(data) + 1)):
            data.extend(chunk)
            if len(data) > limit:
                raise ValueError("ZIP 包读取的解压数据超过限制")
    if len(data) != entry.file_size:
        raise ValueError("ZIP 文件的实际大小与目录记录不一致")
    return bytes(data)


def parse_export_zip(content: bytes) -> ParsedDocument:
    """Parse a user-downloaded ZIP bundle into one ParsedDocument.

    All entries count toward the archive limits. Unsupported attachments are
    ignored. Invalid input fails before any parsed evidence is persisted.
    """
    if len(content) > _MAX_ZIP_BYTES:
        raise ValueError("ZIP 导出包不能超过 25 MB")
    blocks: list[ParsedBlock] = []
    remaining = _MAX_ZIP_EXPANDED_BYTES
    try:
        with ZipFile(BytesIO(content)) as archive:
            members = _zip_members(archive)
            if not members:
                raise ValueError("ZIP 包内没有可解析的 HTML/JSON/CSV/TXT/Markdown 文件")
            for name, entry in members:
                raw = _read_zip_member(archive, entry, remaining)
                remaining -= len(raw)
                blocks.extend(_member_blocks(name, raw, start=len(blocks)))
    except (BadZipFile, EOFError, NotImplementedError, zlib.error) as exc:
        raise ValueError("文件不是有效的 ZIP 导出包") from exc

    return ParsedDocument(
        doc_id="",
        blocks=blocks,
        source_type="export_zip",
        metadata={"member_count": len(members), "fingerprint": source_fingerprint(content)},
        parse_status="parsed" if blocks else "empty",
    )


def _member_blocks(name: str, raw: bytes, *, start: int) -> list[ParsedBlock]:
    if name.lower().endswith((".html", ".htm")):
        blocks = parse_html_export(name, raw).blocks
    else:
        text = raw.decode("utf-8", errors="replace").strip()
        blocks = [
            ParsedBlock(
                content=text, block_index=0, source_type="text",
                source_metadata={"filename": name},
            )
        ] if text else []
    for offset, block in enumerate(blocks):
        block.block_index = start + offset
        block.source_metadata = {
            **block.source_metadata, "archive_member": name, "member_index": offset,
        }
    return blocks
