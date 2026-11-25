"""GitHub import with a user-supplied read-only token.

The user creates a fine-grained personal access token themselves (Contents:
read, Metadata: read) and pastes it into the app. No OAuth app, no client
secret, no callback URL. The token is used for the duration of one request and
is never written to the database, logs or evidence metadata.

This reads public or private repository metadata and README text only. It does
not read issues, pull requests, commits, emails or anything outside the repos
the token is scoped to.
"""

import re
from datetime import UTC, datetime
from typing import Any

import httpx

from app.connectors.base import ConnectorItem

API_ROOT = "https://api.github.com"
MAX_REPOS = 10
README_LIMIT = 6000
_REF_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


class GitHubImportError(ValueError):
    """User-facing import error; never contains the token."""


def normalise_repo_refs(raw: list[str]) -> list[str]:
    """Accept ``owner/name`` or a GitHub URL; keep order and drop duplicates."""
    refs: list[str] = []
    for entry in raw:
        text = (entry or "").strip()
        if not text:
            continue
        for prefix in ("https://github.com/", "http://github.com/", "github.com/"):
            if text.casefold().startswith(prefix):
                text = text[len(prefix):]
                break
        text = text.split("?", 1)[0].split("#", 1)[0].strip("/")
        if text.endswith(".git"):
            text = text[:-4]
        parts = [part for part in text.split("/") if part]
        if len(parts) > 2:
            parts = parts[:2]
        text = "/".join(parts)
        if not _REF_PATTERN.match(text):
            raise GitHubImportError(f"仓库名格式应为 owner/name：{entry}")
        if text not in refs:
            refs.append(text)
    if len(refs) > MAX_REPOS:
        raise GitHubImportError(f"一次最多导入 {MAX_REPOS} 个仓库")
    return refs


def _headers(token: str, accept: str = "application/vnd.github+json") -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": accept,
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "CareerLens-GitHub-Import",
    }


def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.status_code < 400:
        return
    if response.status_code == 429 or (
        response.status_code == 403
        and response.headers.get("x-ratelimit-remaining") == "0"
    ):
        raise GitHubImportError("GitHub 接口限流了，请稍后再试，或换一个只读令牌。")
    if response.status_code == 401:
        raise GitHubImportError("令牌无效或已过期，请重新生成一个只读令牌。")
    if response.status_code in {403, 404}:
        raise GitHubImportError(f"{context}不存在，或该令牌没有访问权限。")
    raise GitHubImportError(f"GitHub 返回了 {response.status_code}，本次导入未完成。")


def _content(repo: dict[str, Any], readme: str, fetched_at: str) -> str:
    topics = "、".join(repo.get("topics") or []) or "（无）"
    lines = [
        f"项目：{repo.get('full_name', '')}",
        f"简介：{repo.get('description') or '（作者未填写简介）'}",
        f"主要语言：{repo.get('language') or '未标注'}",
        f"主题：{topics}",
        f"Star：{repo.get('stargazers_count', 0)} · Fork：{repo.get('forks_count', 0)}",
        f"最近推送：{repo.get('pushed_at') or '未知'} · 采集时间：{fetched_at}",
    ]
    excerpt = readme.strip()[:README_LIMIT]
    if excerpt:
        lines.extend(["", "README 摘录：", excerpt])
    return "\n".join(lines)


async def fetch_github_items(
    *,
    token: str,
    repos: list[str] | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
    timeout: float = 10.0,
) -> tuple[list[ConnectorItem], int]:
    """Return (items, skipped). The token lives only inside this call."""
    token = (token or "").strip()
    if len(token) < 20 or any(char.isspace() for char in token):
        raise GitHubImportError(
            "令牌格式不正确，请粘贴完整令牌（通常以 github_pat_ 或 ghp_ 开头）。"
        )
    refs = normalise_repo_refs(repos or [])
    fetched_at = datetime.now(UTC).isoformat(timespec="seconds")

    async with httpx.AsyncClient(
        base_url=API_ROOT,
        headers=_headers(token),
        timeout=timeout,
        transport=transport,
        follow_redirects=True,
    ) as client:
        user_response = await client.get("/user")
        _raise_for_status(user_response, "令牌对应的账号")
        login = str(user_response.json().get("login") or "")

        if not refs:
            list_response = await client.get(
                "/user/repos",
                params={
                    "per_page": MAX_REPOS,
                    "sort": "pushed",
                    "direction": "desc",
                    "affiliation": "owner",
                },
            )
            _raise_for_status(list_response, "仓库列表")
            refs = [
                row["full_name"]
                for row in list_response.json()
                if isinstance(row, dict) and row.get("full_name")
            ][:MAX_REPOS]

        items: list[ConnectorItem] = []
        skipped = 0
        for ref in refs:
            repo_response = await client.get(f"/repos/{ref}")
            _raise_for_status(repo_response, f"仓库 {ref}")
            repo = repo_response.json()

            readme_text = ""
            readme_response = await client.get(
                f"/repos/{ref}/readme", headers=_headers(token, "application/vnd.github.raw")
            )
            if readme_response.status_code == 200:
                readme_text = readme_response.text
            elif readme_response.status_code not in {404}:
                _raise_for_status(readme_response, f"仓库 {ref} 的 README")

            if not readme_text.strip() and not repo.get("description"):
                skipped += 1
                continue

            full_name = repo.get("full_name", ref)
            pushed_at = repo.get("pushed_at") or "unknown"
            external_id = f"github:{full_name}@{pushed_at}"
            items.append(ConnectorItem(
                external_id=external_id,
                source_name=str(repo.get("full_name") or ref)[:255],
                content=_content(repo, readme_text, fetched_at),
                metadata={
                    "connector": "github_token",
                    "connector_item_id": external_id,
                    "source_url": repo.get("html_url") or f"https://github.com/{ref}",
                    "platform": "github",
                    "account_login": login,
                    "claim_strength": "self_reported_published",
                    "language": repo.get("language"),
                    "topics": list(repo.get("topics") or [])[:20],
                    "stars": int(repo.get("stargazers_count") or 0),
                    "forks": int(repo.get("forks_count") or 0),
                    "visibility": repo.get("visibility")
                    or ("private" if repo.get("private") else "public"),
                    "pushed_at": repo.get("pushed_at"),
                    "fetched_at": fetched_at,
                    "note": (
                        "用户自备只读令牌读取仓库信息与 README；令牌未落库；"
                        "账号归属由令牌验证，但仓库内容仍按自报处理。"
                    ),
                },
            ))
        return items, skipped


__all__ = ["GitHubImportError", "fetch_github_items", "normalise_repo_refs"]
