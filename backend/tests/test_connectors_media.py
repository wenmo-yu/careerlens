import json

from app.api.routes import evidence as evidence_routes
from app.connectors.bilibili import parse_bilibili_export
from app.connectors.weibo import parse_weibo_export


def test_parse_bilibili_export_normalizes_content():
    items, skipped = parse_bilibili_export(
        json.dumps(
            {
                "videos": [
                    {
                        "bvid": "BV1TEST",
                        "title": "LangGraph 项目复盘",
                        "desc": "介绍职业 Agent",
                        "subtitle": "使用 FastAPI 和 Qdrant 构建系统",
                        "tags": ["AI", "Agent"],
                        "pubdate": 1700000000,
                    },
                    {"title": ""},
                ]
            },
            ensure_ascii=False,
        ).encode()
    )
    assert skipped == 1
    assert len(items) == 1
    assert items[0].external_id == "BV1TEST"
    assert "字幕：使用 FastAPI 和 Qdrant 构建系统" in items[0].content
    assert items[0].metadata["connector"] == "bilibili_export"


async def test_bilibili_import_is_idempotent(client):
    payload = json.dumps(
        {
            "items": [
                {
                    "bvid": "BV1CAREER",
                    "title": "AI Agent 开发记录",
                    "description": "使用 Python、FastAPI 与 LangGraph",
                }
            ]
        },
        ensure_ascii=False,
    ).encode()
    first = await client.post(
        "/api/v1/connectors/bilibili/import",
        data={"user_id": "connector-user"},
        files={"upload": ("bilibili.json", payload, "application/json")},
    )
    assert first.status_code == 201
    assert first.json()["created_count"] == 1
    assert first.json()["duplicate_count"] == 0

    second = await client.post(
        "/api/v1/connectors/bilibili/import",
        data={"user_id": "connector-user"},
        files={"upload": ("bilibili.json", payload, "application/json")},
    )
    assert second.status_code == 201
    assert second.json()["created_count"] == 0
    assert second.json()["duplicate_count"] == 1


def test_parse_weibo_json_normalizes_html_topics_and_repost():
    items, skipped = parse_weibo_export(
        json.dumps(
            {
                "statuses": [
                    {
                        "idstr": "WB1001",
                        "text_raw": "复盘 <b>CareerLens</b><br>使用 LangGraph。",
                        "topics": ["AI Agent", "项目复盘"],
                        "created_at": "2026-10-15T12:00:00+08:00",
                        "retweeted_status": {"text": "原文包含 FastAPI 与 Qdrant"},
                    },
                    {"idstr": "empty", "text": ""},
                ]
            },
            ensure_ascii=False,
        ).encode(),
        "weibo.json",
    )
    assert skipped == 1
    assert items[0].external_id == "WB1001"
    assert "正文：复盘 CareerLens\n使用 LangGraph。" in items[0].content
    assert "话题：AI Agent、项目复盘" in items[0].content
    assert "转发内容：原文包含 FastAPI 与 Qdrant" in items[0].content
    assert items[0].metadata["connector"] == "weibo_export"


def test_parse_weibo_csv_uses_stable_content_id():
    payload = (
        "微博正文,发布时间,话题,微博链接\n"
        '"实现了 FastAPI Agent 服务","2026-10-15","#Agent#","https://weibo.com/1"\n'
    ).encode()
    first, _ = parse_weibo_export(payload, "weibo.csv")
    second, _ = parse_weibo_export(payload, "weibo.csv")
    assert first[0].external_id.startswith("content-")
    assert first[0].external_id == second[0].external_id
    assert first[0].metadata["topics"] == ["Agent"]


async def test_weibo_import_is_idempotent(client):
    payload = json.dumps(
        {
            "posts": [
                {
                    "mid": "WBCAREER",
                    "text": "用 Python 和 LangGraph 实现个人职业画像 Agent",
                    "created_at": "2026-10-15",
                    "url": "https://weibo.com/status/WBCAREER",
                }
            ]
        },
        ensure_ascii=False,
    ).encode()
    first = await client.post(
        "/api/v1/connectors/weibo/import",
        data={"user_id": "weibo-user"},
        files={"upload": ("weibo.json", payload, "application/json")},
    )
    assert first.status_code == 201
    assert first.json()["created_count"] == 1
    assert first.json()["connector"] == "weibo_export"
    item = first.json()["items"][0]
    assert item["source_type"] == "weibo"
    assert item["source_metadata"]["connector_item_id"] == "WBCAREER"

    second = await client.post(
        "/api/v1/connectors/weibo/import",
        data={"user_id": "weibo-user"},
        files={"upload": ("weibo.json", payload, "application/json")},
    )
    assert second.status_code == 201
    assert second.json()["created_count"] == 0
    assert second.json()["duplicate_count"] == 1


async def test_media_upload_uses_extracted_text(client, monkeypatch):
    class FakeExtractor:
        def extract(self, filename: str, content: bytes):
            assert filename == "demo.png"
            assert content == b"fake-image"
            return "OCR 识别到 Python 与 FastAPI 项目经验", {"extractor": "fake-ocr"}

    monkeypatch.setattr(evidence_routes, "get_media_extractor", lambda: FakeExtractor())
    response = await client.post(
        "/api/v1/evidence/media",
        data={"user_id": "media-user", "source_type": "personal_media"},
        files={"upload": ("demo.png", b"fake-image", "image/png")},
    )
    assert response.status_code == 201
    item = response.json()["items"][0]
    assert item["content"] == "OCR 识别到 Python 与 FastAPI 项目经验"
    assert item["source_metadata"]["extractor"] == "fake-ocr"


async def test_media_upload_reports_missing_optional_runtime(client, monkeypatch):
    class MissingExtractor:
        def extract(self, filename: str, content: bytes):
            raise RuntimeError("ASR runtime is unavailable")

    monkeypatch.setattr(evidence_routes, "get_media_extractor", lambda: MissingExtractor())
    response = await client.post(
        "/api/v1/evidence/media",
        data={"user_id": "media-user"},
        files={"upload": ("demo.mp3", b"audio", "audio/mpeg")},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == "ASR runtime is unavailable"
