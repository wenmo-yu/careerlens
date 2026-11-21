"""极简 HTTP 客户端：只用 Python 标准库，请求本机 CareerLens Demo API。

不是生产代码，仅供教学脚本复用。不导入 backend/app 的任何模块。
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any

DEFAULT_BASE = "http://localhost:8000"


def base_url() -> str:
    """从命令行第一个参数取服务地址，否则用默认值。"""
    return (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")


def tutorial_user(name: str) -> str:
    """冒烟测试用独立命名空间；普通读者使用固定的教学账号。"""
    namespace = os.environ.get("CAREERLENS_TUTORIAL_NAMESPACE", "")
    if not namespace:
        return name
    check(bool(re.fullmatch(r"[a-z0-9-]{1,40}", namespace)), "无效的教学账号后缀")
    return f"{name}-{namespace}"


def request(
    method: str,
    path: str,
    *,
    body: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    base: str | None = None,
    timeout: float = 30,
) -> tuple[int, Any]:
    """返回 (HTTP 状态码, 已解析的 JSON)。失败抛 RuntimeError。"""
    url = (base or base_url()) + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Accept": "application/json"}
    if data is not None:
        hdrs["Content-Type"] = "application/json"
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"{method} {path} 返回 HTTP {exc.code}: {raw}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"连不上 {url}。确认服务已启动（docker compose ps）且地址正确。原因：{exc.reason}"
        ) from exc


def check(condition: bool, message: str) -> None:
    """断言helper：失败时退出码非 0。"""
    if not condition:
        raise AssertionError(message)


def prepare_profile(user_id: str, *, base: str | None = None) -> str:
    """写入合成证据并重建画像，供对话或岗位分析使用。"""
    status, evidence = request(
        "POST",
        "/api/v1/evidence/text",
        body={
            "user_id": user_id,
            "source_type": "self_statement",
            "source_name": "practice-note",
            "content": "我用 Python 和 FastAPI 做过一个课程项目，只在本机演示。",
        },
        base=base,
    )
    check(status == 201 and bool(evidence["items"]), "写入合成证据失败")
    evidence_id = evidence["items"][0]["id"]
    check(bool(evidence_id), "没有拿到 Evidence ID")
    status, profile = request("POST", f"/api/v1/profiles/{user_id}/rebuild", base=base)
    check(status == 200 and profile["count"] > 0, "画像为空，无法继续练习")
    return evidence_id
