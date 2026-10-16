import csv
import hashlib
import html
import io
import json
import re
from pathlib import Path
from typing import Any

from app.connectors.base import ConnectorItem


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return None


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    return "\n".join(line.strip() for line in text.splitlines() if line.strip())


def _tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip("# ") for item in value if str(item).strip("# ")]
    if isinstance(value, str):
        explicit = re.findall(r"#([^#]+)#", value)
        if explicit:
            return [item.strip() for item in explicit if item.strip()]
        return [item.strip("# ") for item in value.split(",") if item.strip("# ")]
    return []


def _stable_id(item: dict[str, Any], text: str, created_at: Any) -> str:
    supplied = _first(item, "idstr", "mid", "id", "weibo_id", "status_id")
    if supplied is not None:
        return str(supplied)
    digest = hashlib.sha256(f"{created_at or ''}\n{text}".encode()).hexdigest()[:24]
    return f"content-{digest}"


def _normalize_item(raw: dict[str, Any]) -> ConnectorItem | None:
    text = _plain_text(_first(raw, "text_raw", "text", "content", "正文", "微博正文"))
    if not text:
        return None
    created_at = _first(raw, "created_at", "createdAt", "date", "发布时间", "时间")
    external_id = _stable_id(raw, text, created_at)
    topics = _tags(_first(raw, "topics", "hashtags", "tags", "话题"))
    parts = [f"正文：{text}"]
    if topics:
        parts.append(f"话题：{'、'.join(topics)}")

    repost = _first(raw, "retweeted_status", "repost", "转发内容")
    if isinstance(repost, dict):
        repost = _first(repost, "text_raw", "text", "content")
    repost_text = _plain_text(repost)
    if repost_text:
        parts.append(f"转发内容：{repost_text}")

    metadata = {
        "connector": "weibo_export",
        "connector_item_id": external_id,
        "url": _first(raw, "url", "link", "微博链接"),
        "published_at": created_at,
        "content_kind": _first(raw, "type", "kind") or "status",
        "topics": topics,
        "visibility": _first(raw, "visible", "visibility", "可见范围"),
    }
    compact = " ".join(text.split())
    source_name = str(_first(raw, "title") or compact[:48] or external_id)
    return ConnectorItem(
        external_id=external_id,
        source_name=source_name[:255],
        content="\n".join(parts),
        metadata={key: value for key, value in metadata.items() if value not in (None, [], "")},
    )


def _json_items(content: bytes) -> list[Any]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Weibo JSON export must be UTF-8 encoded") from exc
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        raise ValueError("Weibo JSON export must contain an array of posts")
    raw_items = _first(payload, "statuses", "posts", "weibo", "items", "data")
    if isinstance(raw_items, dict):
        raw_items = _first(raw_items, "statuses", "posts", "list", "items")
    if not isinstance(raw_items, list):
        raise ValueError("Weibo JSON must contain statuses, posts, weibo, or items")
    return raw_items


def _csv_items(content: bytes) -> list[dict[str, Any]]:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("Weibo CSV export must be UTF-8 encoded") from exc
    try:
        rows = list(csv.DictReader(io.StringIO(text)))
    except csv.Error as exc:
        raise ValueError("Weibo CSV export is malformed") from exc
    if not rows or not rows[0]:
        raise ValueError("Weibo CSV export must contain a header and at least one row")
    return rows


def parse_weibo_export(
    content: bytes, filename: str | None = None
) -> tuple[list[ConnectorItem], int]:
    suffix = Path(filename or "").suffix.lower()
    raw_items = _csv_items(content) if suffix == ".csv" else _json_items(content)
    parsed: list[ConnectorItem] = []
    skipped = 0
    for raw in raw_items:
        if not isinstance(raw, dict):
            skipped += 1
            continue
        item = _normalize_item(raw)
        if item is None:
            skipped += 1
            continue
        parsed.append(item)
    if not parsed:
        raise ValueError("No readable Weibo posts were found in the export")
    return parsed, skipped
