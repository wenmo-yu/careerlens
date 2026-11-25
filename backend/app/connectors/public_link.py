"""HY4-D L2: turn a user-pasted public link into a reviewable evidence card.

The backend NEVER fetches the URL. It stores exactly what the user typed,
marks the claim as self-reported, and requires an explicit confirmation flag.
This makes code-platform URLs useful without OAuth, crawling or cookies.
"""

from urllib.parse import urlparse

from pydantic import BaseModel, Field

from app.connectors.base import ConnectorItem

_ALLOWED_HOSTS = {
    "github.com", "gitlab.com", "gitee.com",
    "juejin.cn", "csdn.net", "zhihu.com", "xiaohongshu.com",
}


class PublicLinkCard(BaseModel):
    url: str = Field(min_length=10, max_length=2048)
    title: str = Field(min_length=1, max_length=255)
    note: str = Field(default="", max_length=2000)
    confirmed: bool = False


def _allowed_host(url: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").casefold()
    return parsed.scheme == "https" and any(
        host == domain or host.endswith(f".{domain}") for domain in _ALLOWED_HOSTS
    )


def build_public_link_items(cards: list[PublicLinkCard]) -> tuple[list[ConnectorItem], int]:
    """Return (items, skipped). Unconfirmed cards are skipped by design."""
    items: list[ConnectorItem] = []
    skipped = 0
    seen: set[str] = set()
    for card in cards:
        if not card.confirmed:
            skipped += 1
            continue
        if not _allowed_host(card.url):
            skipped += 1
            continue
        parsed = urlparse(card.url)
        canonical = f"{parsed.scheme}://{parsed.netloc}{parsed.path}".rstrip("/")
        if canonical in seen:
            skipped += 1
            continue
        seen.add(canonical)
        content = f"{card.title}\n{canonical}\n{card.note}".strip()
        items.append(ConnectorItem(
            external_id=f"public-link:{canonical}",
            source_name=card.title[:255],
            content=content,
            metadata={
                "connector": "public_link_card",
                "connector_item_id": f"public-link:{canonical}",
                "source_url": canonical,
                "claim_strength": "self_reported_published",
                "host": parsed.hostname,
                "note": "用户粘贴并确认；系统未访问链接，不证明账号归属。",
            },
        ))
    return items, skipped
