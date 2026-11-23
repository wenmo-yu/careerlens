"""生成 02/03 教程用的合成 DOCX 样本（只用 Python 标准库）。

DOCX 本质是 OOXML 的 ZIP 包，这里用 zipfile + ElementTree 手搓一个最小、
能被 python-docx 解析的 .docx，因此**生成端零依赖**。注意：服务端解析 DOCX
仍依赖 python-docx（backend/pyproject.toml），生成端不需要只是本项目打包的便利。

运行（仓库根目录）：
    python3 examples/tutorials/fixtures/make_docx.py

产出：同目录下的 demo-a.docx 与 demo-b.docx。两份用 Heading 1 写不同标题
（演示 A / 演示 B），正文含逐字节相同的 A 卡段落。因为 SourceDocument 按
文件字节 hash 判重、Evidence 按段落文本 hash 判重，所以：
  - 两个不同的 SourceDocument（字节不同）
  - 共享一条 Evidence（A 卡正文文本相同），sources[] 有两条来源
"""
from __future__ import annotations

import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
# 两份文档固定使用同一段正文，方便跟做时定位共享证据。
SHARED_PARAGRAPH = "我用 Python 做过一个课程项目，只在本机演示。"
W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

_DOC_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"
_STYLES_CT = "application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"
_OFFICE_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument"
_STYLES_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles"

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    f'<Override PartName="/word/document.xml" ContentType="{_DOC_CT}"/>'
    f'<Override PartName="/word/styles.xml" ContentType="{_STYLES_CT}"/>'
    '</Types>'
)

RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{_OFFICE_REL}" Target="word/document.xml"/>'
    '</Relationships>'
)

DOCUMENT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Id="rId1" Type="{_STYLES_REL}" Target="styles.xml"/>'
    '</Relationships>'
)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def paragraph(text: str, heading: bool = False) -> str:
    ppr = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if heading else ""
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{esc(text)}</w:t></w:r></w:p>'


def document_xml(title: str) -> str:
    body = paragraph(title, heading=True) + paragraph(SHARED_PARAGRAPH)
    styles = (
        '<w:styles xmlns:w="' + W + '">'
        '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
        '<w:name w:val="Normal"/></w:style>'
        '<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>'
        '</w:styles>'
    )
    doc = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}"><w:body>{body}<w:sectPr/></w:body></w:document>'
    )
    return doc, styles


def write_docx(path: Path, title: str) -> None:
    doc, styles = document_xml(title)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/_rels/document.xml.rels", DOCUMENT_RELS)
        z.writestr("word/styles.xml", styles)


def main() -> None:
    a = HERE / "demo-a.docx"
    b = HERE / "demo-b.docx"
    write_docx(a, "演示 A")
    write_docx(b, "演示 B")
    print("生成：", a.name, a.stat().st_size, "bytes")
    print("生成：", b.name, b.stat().st_size, "bytes")
    print("两份字节不同：", a.read_bytes() != b.read_bytes())
    print("共享正文：", SHARED_PARAGRAPH)


if __name__ == "__main__":
    main()
