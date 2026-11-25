"""HY4-A: import result cards must tell the user what was actually read.

A successful HTTP task is not the same as readable text. These tests pin the
result-card fields and the unified claim-strength judgement for pasted text.
"""

import io

import pymupdf
from docx import Document

from app.ingestion.claim_strength import classify_claim_strength
from app.models.evidence import Evidence
from app.profile.extractor import extract_profile_items


def test_classify_claim_strength_pasted_interaction_is_preference_signal():
    for text in (
        "我收藏了一份 Kubernetes 教程",
        "收藏了 Kubernetes 部署教程",
        "收藏了《Kubernetes，部署教程》",
        "关注了 Kubernetes 部署与运行教程",
        "点赞了 LangGraph 入门文章",
        "关注了 RAG 相关账号",
    ):
        assert classify_claim_strength(text, {})["claim_strength"] == "preference_signal"


def test_classify_claim_strength_action_claim_is_self_reported():
    for text in (
        "在本地 Kubernetes 集群部署 API 并通过探针",
        "我用 FastAPI 构建过多轮 Agent",
        "我写了 RAG 检索Demo",
        "我在练习集群部署了 Kubernetes 并收藏了教程",
        "我收藏了教程，也在练习集群部署了 Kubernetes",
    ):
        assert classify_claim_strength(text, {})["claim_strength"] == "self_reported_published"


def test_classify_claim_strength_keeps_explicit_metadata():
    metadata = {"claim_strength": "preference_signal", "source": "browser_capture_v1"}
    assert classify_claim_strength("我部署了服务", metadata) == metadata
    assert metadata["claim_strength"] == "preference_signal"


async def test_text_import_marks_pasted_favourite(client):
    response = await client.post(
        "/api/v1/evidence/text",
        json={"user_id": "hy4-a-text", "content": "我收藏了一份 Kubernetes 部署教程"},
    )
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["source_metadata"]["claim_strength"] == "preference_signal"
    profile = await client.post("/api/v1/profiles/hy4-a-text/rebuild")
    assert profile.status_code == 200
    assert all(item["name"] != "Kubernetes" for item in profile.json()["items"])


def test_rebuild_ignores_legacy_pasted_bookmark_metadata():
    evidence = Evidence(
        id="legacy-bookmark", source_type="self_statement",
        content="收藏了 Kubernetes 部署教程",
        source_metadata={"claim_strength": "self_reported_published"},
    )
    assert extract_profile_items([evidence]) == []


def _opaque_image() -> bytes:
    rect = pymupdf.IRect(0, 0, 600, 800)
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, rect)
    pixmap.clear_with(0)
    return pixmap.tobytes("png")


def _pdf_with_image_only() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_image(page.rect, stream=_opaque_image())
    data = document.tobytes()
    document.close()
    return data


def _pdf_with_text_and_image() -> bytes:
    document = pymupdf.open()
    text_page = document.new_page()
    text_page.insert_text((72, 72), "Python 与 FastAPI 项目经验", fontsize=12)
    image_page = document.new_page()
    image_page.insert_image(image_page.rect, stream=_opaque_image())
    data = document.tobytes()
    document.close()
    return data


async def test_file_result_card_reports_pending_ocr(client):
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "hy4-a-scan"},
        files={"upload": ("scan.pdf", _pdf_with_image_only(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["parse_status"] == "partial"
    assert payload["source_document_id"]
    assert payload["ocr_pending_count"] >= 1
    assert payload["readable_count"] == 0
    assert payload["count"] == 0
    assert any("OCR" in warning for warning in payload["warnings"])
    assert any("尚未生成可读证据" in warning for warning in payload["warnings"])


async def test_mixed_pdf_result_card_reports_both(client):
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "hy4-a-mixed"},
        files={"upload": ("mixed.pdf", _pdf_with_text_and_image(), "application/pdf")},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["parse_status"] == "partial"
    assert payload["readable_count"] >= 1
    assert payload["ocr_pending_count"] >= 1
    assert payload["count"] >= 1
    assert any("待 OCR" in warning for warning in payload["warnings"])


async def test_text_pdf_result_card_is_parsed(client):
    document = Document()
    document.add_heading("个人技能", level=1)
    document.add_paragraph("熟悉 Python 与 FastAPI")
    buffer = io.BytesIO()
    document.save(buffer)
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "hy4-a-docx"},
        files={"upload": (
            "skills.docx", buffer.getvalue(),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )},
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["parse_status"] in {"parsed", "partial"}
    assert payload["readable_count"] >= 2
    assert payload["ocr_pending_count"] == 0


async def test_legacy_doc_error_gives_conversion_hint(client):
    response = await client.post(
        "/api/v1/evidence/file",
        data={"user_id": "hy4-a-doc"},
        files={"upload": ("resume.doc", b"old binary", "application/msword")},
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert ".docx" in detail
    assert "带文字层 PDF" in detail


async def test_duplicate_upload_result_is_still_explainable(client):
    content = "我用 Python 做过一个项目。"
    payload = None
    for _ in range(2):
        response = await client.post(
            "/api/v1/evidence/file",
            data={"user_id": "hy4-a-dup"},
            files={"upload": ("cv.txt", content.encode("utf-8"), "text/plain")},
        )
        assert response.status_code == 201
        payload = response.json()
    assert payload["count"] == 1
    assert payload["source_document_id"]
    assert payload["readable_count"] == 1
    assert payload["ocr_pending_count"] == 0
