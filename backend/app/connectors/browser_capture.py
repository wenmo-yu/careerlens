"""Import a user-reviewed snapshot exported by the local browser helper."""

import hashlib
import json
from typing import Any, Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError

from app.connectors.base import ConnectorItem

Platform = Literal["bilibili", "weibo", "douyin"]
Kind = Literal["published", "liked", "favorite", "following"]

_HOSTS = {
    "bilibili": ("bilibili.com",),
    "weibo": ("weibo.com", "weibo.cn"),
    "douyin": ("douyin.com",),
}


class CapturedItem(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    title: str = Field(default="", max_length=500)
    text: str = Field(default="", max_length=4000)


class BrowserCapture(BaseModel):
    format: Literal["careerlens-browser-capture-v1"]
    platform: Platform
    kind: Kind
    source_url: str = Field(min_length=10, max_length=2048)
    captured_at: str = Field(min_length=1, max_length=64)
    items: list[CapturedItem] = Field(min_length=1, max_length=200)


def _allowed_url(value: str, platform: Platform) -> bool:
    parsed = urlparse(value)
    hostname = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        hostname == domain or hostname.endswith(f".{domain}")
        for domain in _HOSTS[platform]
    )


def _canonical_url(value: str) -> str:
    return urlparse(value)._replace(params="", query="", fragment="").geturl()


def parse_browser_capture(content: bytes) -> tuple[list[ConnectorItem], int, Platform]:
    if len(content) > 2_000_000:
        raise ValueError("Browser capture is too large")
    try:
        payload: Any = json.loads(content.decode("utf-8-sig"))
        capture = BrowserCapture.model_validate(payload)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("Invalid CareerLens browser capture JSON") from exc
    if not _allowed_url(capture.source_url, capture.platform):
        raise ValueError("Capture source URL does not match its platform")
    source_url = _canonical_url(capture.source_url)

    parsed: list[ConnectorItem] = []
    seen: set[str] = set()
    skipped = 0
    for item in capture.items:
        if not _allowed_url(item.url, capture.platform):
            skipped += 1
            continue
        item_url = _canonical_url(item.url)
        title = " ".join(item.title.split())[:300]
        excerpt = " ".join(item.text.split())[:1200]
        if not title and not excerpt:
            skipped += 1
            continue
        digest = hashlib.sha256(item_url.encode("utf-8")).hexdigest()[:24]
        external_id = f"{capture.platform}:{capture.kind}:{digest}"
        if external_id in seen:
            skipped += 1
            continue
        seen.add(external_id)
        label = "页面发布记录（用户自报）" if capture.kind == "published" else "浏览互动线索"
        text = f"{label}：{title or excerpt}"
        if excerpt and excerpt != title:
            text += f"\n页面摘要：{excerpt}"
        parsed.append(
            ConnectorItem(
                external_id=external_id,
                source_name=(title or excerpt[:80])[:255],
                content=text,
                metadata={
                    "connector": "browser_capture_v1",
                    "connector_item_id": external_id,
                    "platform": capture.platform,
                    "interaction_kind": capture.kind,
                    "claim_strength": (
                        "self_reported_published"
                        if capture.kind == "published"
                        else "preference_signal"
                    ),
                    "url": item_url,
                    "source_url": source_url,
                    "captured_at": capture.captured_at,
                },
            )
        )
    if not parsed:
        raise ValueError("No readable platform items were found in the capture")
    return parsed, skipped, capture.platform
