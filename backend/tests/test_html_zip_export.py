"""HY4-D: user-provided HTML exports and ZIP bundles parse locally.

No network, no bs4/lxml, no platform credentials. Traversal and oversized
members are rejected so a downloaded bundle cannot smuggle unexpected files.
"""

from io import BytesIO
from zipfile import ZipFile

import pytest

from app.ingestion import html_export
from app.ingestion.files import parse_document
from app.ingestion.html_export import parse_export_zip, parse_html_export


def test_html_export_skips_scripts_and_keeps_visible_text():
    raw = """
    <html><head><title>My answers</title><script>secretToken=123</script></head>
    <body><div>我用 Python 做过检索项目</div><p>熟悉 FastAPI 与 RAG</p>
    <style>.hidden{display:none}</style></body></html>
    """.encode()
    parsed = parse_html_export("answers.html", raw)
    text = "\n".join(block.content for block in parsed.blocks)
    assert "Python" in text
    assert "FastAPI" in text
    assert "secretToken" not in text
    assert parsed.metadata["title"] == "My answers"


def test_html_export_empty_page_has_no_blocks():
    parsed = parse_html_export("empty.html", b"<html><script>x()</script></html>")
    assert parsed.blocks == []
    assert parsed.parse_status == "empty"


def test_zip_bundle_members_become_blocks_in_stable_order():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("b.md", "熟悉 Docker 与 PostgreSQL".encode())
        archive.writestr(
            "a.html", "<html><body><p>我用 Python 做过 Agent</p></body></html>".encode()
        )
        archive.writestr("skip.exe", b"binary")
    parsed = parse_export_zip(buffer.getvalue())
    assert parsed.metadata["member_count"] == 2
    assert [block.source_metadata["archive_member"] for block in parsed.blocks] == [
        "a.html", "b.md",
    ]
    assert "Python" in parsed.blocks[0].content
    assert "Docker" in parsed.blocks[1].content


def test_zip_rejects_path_traversal():
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.md", "should not be read")
    try:
        parse_export_zip(buffer.getvalue())
    except ValueError as exc:
        assert "无效路径" in str(exc)
    else:
        raise AssertionError("traversal member was accepted")


def test_zip_budget_includes_ignored_attachments(monkeypatch):
    monkeypatch.setattr(html_export, "_MAX_ZIP_EXPANDED_BYTES", 12)
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("results/readme.md", "results")
        archive.writestr("results/tiny.png", b"details")
    with pytest.raises(ValueError, match="解压总量超过限制"):
        parse_export_zip(buffer.getvalue())


def test_parse_document_dispatches_html_and_zip():
    html = parse_document(
        "cv.html", "<html><body><p>熟悉 Python</p></body></html>".encode()
    )
    assert html.source_type == "html_export"
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        archive.writestr("note.md", "我用 FastAPI 做过服务".encode())
    zipped = parse_document("export.zip", buffer.getvalue())
    assert zipped.source_type == "export_zip"


async def test_upload_html_export_creates_evidence(client):
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "html-user", "source_type": "export"},
        files={"upload": (
            "answers.html",
            "<html><body><div>我用 Python 做过检索项目</div></body></html>".encode(),
            "text/html",
        )},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["count"] == 1
    assert "Python" in payload["items"][0]["content"]
