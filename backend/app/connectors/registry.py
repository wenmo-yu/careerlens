"""HY4-D: declarative source registry for the Import Hub.

This is a catalogue of what the system supports, not an executor. Parsing stays
in each connector module; adding a platform here does not grant network access.
The UI uses ``auth_level`` to label sources honestly.

Auth levels:
  A - user-provided file (upload a file the user already has)
  B - browser current-page capture, user ticks each item
  T - user-supplied read-only token (no OAuth app, no callback URL)
  C - official API/OAuth — NOT IMPLEMENTED, shown as unavailable
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    key: str
    label: str
    auth_level: str
    formats: tuple[str, ...]
    endpoint: str | None
    available: bool
    evidence_kind: str
    note: str


SOURCES: tuple[SourceSpec, ...] = (
    SourceSpec(
        key="text", label="文本直录", auth_level="A",
        formats=("text",), endpoint="/api/v1/evidence/text", available=True,
        evidence_kind="self_report",
        note="自述内容；收藏/点赞类语句标记为兴趣线索。",
    ),
    SourceSpec(
        key="documents", label="文档 · PDF / Word .docx / 表格", auth_level="A",
        formats=("pdf", "docx", "xlsx", "txt", "md", "csv", "tsv"),
        endpoint="/api/v1/evidence/file", available=True,
        evidence_kind="self_report",
        note="旧 .doc 请另存为 .docx；扫描页需 OCR，不伪造文字。",
    ),
    SourceSpec(
        key="html_export", label="网页另存为 HTML / 数据导出 ZIP", auth_level="A",
        formats=("html", "htm", "zip"), endpoint="/api/v1/evidence/file", available=True,
        evidence_kind="self_report",
        note="只解析用户已有的文件；不联网、不登录平台；ZIP 内路径穿越会被拒绝。",
    ),
    SourceSpec(
        key="media", label="图片 / 音视频（OCR / ASR）", auth_level="A",
        formats=("png", "jpg", "mp3", "wav", "mp4", "webm"),
        endpoint="/api/v1/evidence/media", available=True,
        evidence_kind="self_report",
        note="需可选解析依赖；缺失时返回 503，不会假装读到文字。",
    ),
    SourceSpec(
        key="bilibili_export", label="B站导出 JSON", auth_level="A",
        formats=("json",), endpoint="/api/v1/connectors/bilibili/import", available=True,
        evidence_kind="self_reported_published",
        note="用户主动上传平台导出文件；按 external_id 去重。",
    ),
    SourceSpec(
        key="weibo_export", label="微博导出 JSON / CSV", auth_level="A",
        formats=("json", "csv"), endpoint="/api/v1/connectors/weibo/import", available=True,
        evidence_kind="self_reported_published",
        note="用户主动上传平台导出文件；按 external_id 去重。",
    ),
    SourceSpec(
        key="browser_capture", label="浏览器当前页采集", auth_level="B",
        formats=("json",), endpoint="/api/v1/connectors/browser/import", available=True,
        evidence_kind="published_or_preference",
        note="手动勾选可见内容；发布=自报，点赞/收藏/关注=兴趣线索；不读 Cookie、不自动翻页。",
    ),
    SourceSpec(
        key="public_link_card", label="公开链接证据卡（粘贴文本）", auth_level="A",
        formats=("text",), endpoint="/api/v1/connectors/public-link/import", available=True,
        evidence_kind="self_reported_published",
        note="只保存用户粘贴的链接与描述，不访问链接、不证明账号归属。",
    ),
    SourceSpec(
        key="github_token", label="GitHub 仓库（自备只读令牌）", auth_level="T",
        formats=("api",), endpoint="/api/v1/connectors/github/import", available=True,
        evidence_kind="self_reported_published",
        note=(
            "用户自建只读令牌，读仓库元数据与 README；"
            "令牌只在本次请求使用、不落库；不读 issues/PR。"
        ),
    ),
    SourceSpec(
        key="official_oauth", label="平台授权只读同步", auth_level="C",
        formats=(), endpoint=None, available=False,
        evidence_kind="verified_public",
        note="GitHub 已改走自备令牌；其他平台仍需注册应用与回调，未实现，不声称可用。",
    ),
)


def list_sources() -> list[dict]:
    return [
        {
            "key": source.key,
            "label": source.label,
            "auth_level": source.auth_level,
            "auth_label": {
                "A": "用户导出 / 粘贴", "B": "当前页采集",
                "T": "自备只读令牌", "C": "需平台授权",
            }[source.auth_level],
            "formats": list(source.formats),
            "endpoint": source.endpoint,
            "available": source.available,
            "evidence_kind": source.evidence_kind,
            "note": source.note,
        }
        for source in SOURCES
    ]
