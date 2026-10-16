import json
from typing import Any

from app.connectors.base import ConnectorItem


def _first(data: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = data.get(key)
        if value not in (None, "", []):
            return value
    return None


def _item_content(item: dict[str, Any]) -> str:
    title = str(_first(item, "title", "name") or "").strip()
    description = str(_first(item, "description", "desc", "intro") or "").strip()
    transcript = str(_first(item, "transcript", "subtitle", "content") or "").strip()
    tags = _first(item, "tags", "tag") or []
    if isinstance(tags, str):
        tags = [value.strip() for value in tags.split(",") if value.strip()]
    parts = []
    if title:
        parts.append(f"标题：{title}")
    if description:
        parts.append(f"简介：{description}")
    if transcript:
        parts.append(f"字幕：{transcript}")
    if tags:
        parts.append(f"标签：{'、'.join(map(str, tags))}")
    return "\n".join(parts)


def parse_bilibili_export(content: bytes) -> tuple[list[ConnectorItem], int]:
    try:
        payload = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Bilibili export must be a UTF-8 JSON file") from exc

    if isinstance(payload, list):
        raw_items = payload
    elif isinstance(payload, dict):
        raw_items = _first(payload, "items", "videos", "archives", "data")
        if isinstance(raw_items, dict):
            raw_items = _first(raw_items, "items", "list", "archives")
    else:
        raw_items = None
    if not isinstance(raw_items, list):
        raise ValueError("Export JSON must contain an items, videos, or archives array")

    parsed: list[ConnectorItem] = []
    skipped = 0
    for index, raw in enumerate(raw_items):
        if not isinstance(raw, dict):
            skipped += 1
            continue
        item_text = _item_content(raw)
        if not item_text.strip():
            skipped += 1
            continue
        external_id = str(_first(raw, "bvid", "aid", "id") or f"export-{index}")
        title = str(_first(raw, "title", "name") or external_id)
        metadata = {
            "connector": "bilibili_export",
            "connector_item_id": external_id,
            "url": _first(raw, "url", "link"),
            "published_at": _first(raw, "published_at", "pubdate", "created_at"),
            "content_kind": _first(raw, "type", "kind") or "video",
        }
        parsed.append(
            ConnectorItem(
                external_id=external_id,
                source_name=title[:255],
                content=item_text,
                metadata={key: value for key, value in metadata.items() if value is not None},
            )
        )
    if not parsed:
        raise ValueError("No readable Bilibili content was found in the export")
    return parsed, skipped
