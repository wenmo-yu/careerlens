import json

from app.api.routes import evidence as evidence_routes
from app.connectors.bilibili import parse_bilibili_export
from app.connectors.browser_capture import parse_browser_capture
from app.connectors.weibo import parse_weibo_export
from app.models.evidence import Evidence
from app.profile.extractor import extract_profile_items
from app.profile.llm_extractor import extract_profile_with_fallback


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


def _capture(platform: str, kind: str, url: str) -> bytes:
    return json.dumps(
        {
            "format": "careerlens-browser-capture-v1",
            "platform": platform,
            "kind": kind,
            "source_url": url,
            "captured_at": "2026-10-25T10:00:00.000Z",
            "items": [
                {"url": url, "title": "Python 项目记录", "text": "使用 Python 构建服务"},
                {"url": url, "title": "重复项", "text": "同一个链接"},
                {"url": "https://example.com/other", "title": "异站项", "text": "不应导入"},
            ],
            "cookie": "must-not-be-stored",
        },
        ensure_ascii=False,
    ).encode()


def test_browser_capture_supports_three_platforms_and_discards_foreign_urls():
    cases = [
        ("bilibili", "https://www.bilibili.com/video/BV1CAREER"),
        ("weibo", "https://weibo.com/status/CAREER123"),
        ("douyin", "https://www.douyin.com/video/123456"),
    ]
    for platform, url in cases:
        items, skipped, selected = parse_browser_capture(_capture(platform, "liked", url))
        assert selected == platform
        assert len(items) == 1
        assert skipped == 2
        assert items[0].metadata["claim_strength"] == "preference_signal"
        assert "cookie" not in str(items[0].metadata).lower()


def test_browser_capture_rejects_mismatched_source_and_unusable_items():
    payload = _capture("bilibili", "published", "https://www.douyin.com/video/123456")
    try:
        parse_browser_capture(payload)
    except ValueError as exc:
        assert "source URL" in str(exc)
    else:
        raise AssertionError("Mismatched platform should be rejected")


def test_browser_capture_does_not_store_url_query_tokens():
    url = "https://www.bilibili.com/video/BV1CAREER?token=secret"
    items, _, _ = parse_browser_capture(_capture("bilibili", "published", url))
    assert items[0].metadata["url"] == "https://www.bilibili.com/video/BV1CAREER"
    assert items[0].metadata["source_url"] == "https://www.bilibili.com/video/BV1CAREER"


async def test_browser_capture_import_deduplicates_and_does_not_promote_likes_to_skill(client):
    url = "https://www.douyin.com/video/123456"
    payload = _capture("douyin", "liked", url)
    first = await client.post(
        "/api/v1/connectors/browser/import",
        data={"user_id": "browser-user"},
        files={"upload": ("capture.json", payload, "application/json")},
    )
    assert first.status_code == 201
    assert first.json()["created_count"] == 1
    assert first.json()["skipped_count"] == 2
    evidence = first.json()["items"][0]
    assert evidence["source_type"] == "douyin_browser"
    assert evidence["source_metadata"]["claim_strength"] == "preference_signal"
    record = Evidence(**{key: value for key, value in evidence.items() if key != "created_at"})
    assert extract_profile_items([record]) == []

    second = await client.post(
        "/api/v1/connectors/browser/import",
        data={"user_id": "browser-user"},
        files={"upload": ("capture.json", payload, "application/json")},
    )
    assert second.status_code == 201
    assert second.json()["duplicate_count"] == 1


async def test_model_cannot_promote_liked_content_to_skill():
    class Provider:
        diagnostics = {"provider": "stub", "model": "test"}

        async def generate_json(self, **_):
            return {
                "items": [
                    {
                        "category": "skill",
                        "name": "Python",
                        "level": 3,
                        "confidence": 0.9,
                        "evidence_ids": ["liked-1"],
                    },
                    {
                        "category": "interest",
                        "name": "Python 教程",
                        "level": 1,
                        "confidence": 0.6,
                        "evidence_ids": ["liked-1"],
                    },
                ]
            }

    evidence = Evidence(
        id="liked-1",
        user_id="user",
        source_type="douyin_browser",
        source_name="Python 教程",
        content="浏览互动线索：Python 教程",
        chunk_index=0,
        source_metadata={"claim_strength": "preference_signal"},
    )
    items = await extract_profile_with_fallback([evidence], Provider())
    assert [(item["category"], item["name"]) for item in items] == [
        ("interest", "Python 教程")
    ]


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
