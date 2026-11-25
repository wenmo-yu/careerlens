"""HY4-D: registry is honest; public-link cards never fetch the URL."""

from app.connectors.public_link import PublicLinkCard, build_public_link_items
from app.connectors.registry import list_sources


def test_registry_marks_oauth_as_unavailable():
    sources = {row["key"]: row for row in list_sources()}
    assert sources["official_oauth"]["available"] is False
    assert sources["official_oauth"]["auth_level"] == "C"
    assert sources["browser_capture"]["auth_level"] == "B"
    assert sources["documents"]["auth_level"] == "A"
    assert "html" in sources["html_export"]["formats"]
    assert "zip" in sources["html_export"]["formats"]


def test_public_link_requires_confirmation():
    cards = [PublicLinkCard(
        url="https://github.com/someone/project/pull/1",
        title="我的 PR", confirmed=False,
    )]
    items, skipped = build_public_link_items(cards)
    assert items == []
    assert skipped == 1


def test_public_link_does_not_fetch_and_marks_self_reported():
    card = PublicLinkCard(
        url="https://github.com/someone/project/pull/1?token=secret",
        title="我提交的检索 PR", note="本地测试通过", confirmed=True,
    )
    items, skipped = build_public_link_items([card])
    assert skipped == 0
    item = items[0]
    assert item.external_id == item.metadata["connector_item_id"]
    assert "token=secret" not in item.content
    assert item.metadata["claim_strength"] == "self_reported_published"
    assert item.metadata["source_url"] == "https://github.com/someone/project/pull/1"
    assert "未访问链接" in item.metadata["note"]


def test_public_link_rejects_unknown_host_and_duplicates():
    cards = [
        PublicLinkCard(url="https://unknown.example.com/x", title="X", confirmed=True),
        PublicLinkCard(url="https://juejin.cn/post/123", title="文章", confirmed=True),
        PublicLinkCard(url="https://juejin.cn/post/123?utm=a", title="文章重复", confirmed=True),
    ]
    items, skipped = build_public_link_items(cards)
    assert len(items) == 1
    assert skipped == 2


async def test_registry_endpoint(client):
    response = await client.get("/api/v1/connectors/registry")
    assert response.status_code == 200
    sources = {row["key"]: row for row in response.json()["sources"]}
    assert sources["public_link_card"]["available"] is True
    assert sources["official_oauth"]["endpoint"] is None


async def test_public_link_import_endpoint(client):
    response = await client.post(
        "/api/v1/connectors/public-link/import",
        json={
            "user_id": "link-user",
            "cards": [{
                "url": "https://github.com/me/project/pull/7",
                "title": "我的 RAG PR", "confirmed": True,
            }],
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["created_count"] == 1
    assert payload["connector"] == "public_link_card"


def test_browser_capture_accepts_new_platforms_and_kinds():
    from app.connectors.browser_capture import parse_browser_capture

    raw = """
    {
      "format": "careerlens-browser-capture-v1",
      "platform": "github", "kind": "merged",
      "source_url": "https://github.com/me/project/pulls",
      "captured_at": "2026-11-25T00:00:00Z",
      "items": [{
        "url": "https://github.com/me/project/pull/1",
        "title": "Add RAG search", "text": "实现混合检索并返回引用"
      }]
    }
    """.encode()
    items, skipped, platform = parse_browser_capture(raw)
    assert platform == "github"
    assert skipped == 0
    assert items[0].metadata["claim_strength"] == "self_reported_published"


def test_browser_capture_new_platform_interaction_is_preference():
    from app.connectors.browser_capture import parse_browser_capture

    raw = """
    {
      "format": "careerlens-browser-capture-v1",
      "platform": "juejin", "kind": "favorite",
      "source_url": "https://juejin.cn/user/1/favorites",
      "captured_at": "2026-11-25T00:00:00Z",
      "items": [{
        "url": "https://juejin.cn/post/123",
        "title": "LangGraph 入门", "text": "收藏的文章"
      }]
    }
    """.encode()
    items, _, _ = parse_browser_capture(raw)
    assert items[0].metadata["claim_strength"] == "preference_signal"
