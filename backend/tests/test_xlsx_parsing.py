"""XLSX ingestion via the standard library (no openpyxl dependency).

Builds a minimal but valid OOXML workbook in-memory and checks that sheets,
shared strings, inline strings and numeric cells become table blocks.
"""

import io
import zipfile

from app.ingestion.files import SUPPORTED_SUFFIXES, extract_text, parse_document

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_DOC = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _build_xlsx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(
            "[Content_Types].xml",
            '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>',
        )
        z.writestr(
            "xl/workbook.xml",
            f'<?xml version="1.0"?><workbook xmlns="{MAIN}" '
            f'xmlns:r="{REL_DOC}"><sheets>'
            f'<sheet name="技能" sheetId="1" r:id="rId1"/>'
            f'<sheet name="项目" sheetId="2" r:id="rId2"/>'
            f"</sheets></workbook>",
        )
        z.writestr(
            "xl/_rels/workbook.xml.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{REL_PKG}">'
            f'<Relationship Id="rId1" Target="worksheets/sheet1.xml" '
            f'Type="{REL_DOC}/worksheet"/>'
            f'<Relationship Id="rId2" Target="worksheets/sheet2.xml" '
            f'Type="{REL_DOC}/worksheet"/>'
            f"</Relationships>",
        )
        z.writestr(
            "xl/sharedStrings.xml",
            f'<?xml version="1.0"?><sst xmlns="{MAIN}">'
            f"<si><t>技能</t></si><si><t>级别</t></si><si><t>Python</t></si>"
            f"</sst>",
        )
        # Sheet 1: shared strings + a numeric cell
        z.writestr(
            "xl/worksheets/sheet1.xml",
            f'<?xml version="1.0"?><worksheet xmlns="{MAIN}"><sheetData>'
            f'<row r="1"><c r="A1" t="s"><v>0</v></c><c r="B1" t="s"><v>1</v></c></row>'
            f'<row r="2"><c r="A2" t="s"><v>2</v></c><c r="B2"><v>5</v></c></row>'
            f"</sheetData></worksheet>",
        )
        # Sheet 2: inline string
        z.writestr(
            "xl/worksheets/sheet2.xml",
            f'<?xml version="1.0"?><worksheet xmlns="{MAIN}"><sheetData>'
            f'<row r="1"><c r="A1" t="inlineStr"><is><t>项目经历</t></is></c></row>'
            f"</sheetData></worksheet>",
        )
    return buf.getvalue()


def test_xlsx_supported_and_parsed():
    assert ".xlsx" in SUPPORTED_SUFFIXES
    doc = parse_document("skills.xlsx", _build_xlsx())
    assert doc.source_type == "xlsx"
    assert doc.parse_status == "parsed"
    assert doc.metadata["sheet_count"] == 2
    assert doc.metadata["row_count"] == 3
    assert len(doc.blocks) == 2
    assert all(block.block_type == "table" for block in doc.blocks)
    assert doc.blocks[0].source_metadata["sheet"] == "sheet1"
    table = doc.blocks[0].content
    assert "Python" in table and "5" in table
    assert "技能" in table and "级别" in table
    assert "项目经历" in doc.blocks[1].content


def test_xlsx_extract_text_backward_compatible():
    text, meta = extract_text("skills.xlsx", _build_xlsx())
    assert "Python" in text
    assert meta["sheet_count"] == 2
