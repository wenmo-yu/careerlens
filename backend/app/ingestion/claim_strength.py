import re
from typing import Any

_PREFERENCE_CUES = ("收藏", "点赞", "喜欢", "关注", "订阅", "标记", "稍后看", "想看", "马住")
_ACTION_CUES = (
    "部署", "实现", "完成", "通过", "构建", "搭建", "运行", "开发", "写了", "写过",
    "做过", "参与", "负责", "发布", "提交", "交付", "设计", "测试", "使用", "熟悉", "掌握",
)
_CLAUSE_BOUNDARY = re.compile(
    r"[，,。；;！!？?\r\n]+|(?:并且|并)(?=(?:我|还|也)*(?:"
    + "|".join((*_PREFERENCE_CUES, *_ACTION_CUES))
    + "))"
)
_QUOTED_TITLE = re.compile(r"《[^》]*》|「[^」]*」|“[^”]*”")


def classify_claim_strength(content: str, metadata: dict[str, Any]) -> dict[str, Any]:
    """Label claims without replacing an explicit source label."""
    result = dict(metadata)
    if result.get("claim_strength"):
        return result

    # Separators inside a quoted course title stay in the enclosing statement.
    text = _QUOTED_TITLE.sub(lambda title: _CLAUSE_BOUNDARY.sub(" ", title.group()), content)
    has_interaction = False
    for clause in _CLAUSE_BOUNDARY.split(text):
        if any(cue in clause for cue in _PREFERENCE_CUES):
            # An action word inside a bookmarked title is still part of that interaction.
            has_interaction = True
        elif any(cue in clause for cue in _ACTION_CUES):
            return {**result, "claim_strength": "self_reported_published"}
    if has_interaction:
        result["claim_strength"] = "preference_signal"
    return result


def is_preference_claim(content: str, source_type: str, metadata: dict[str, Any]) -> bool:
    if metadata.get("claim_strength") == "preference_signal":
        return True
    # Older pasted statements may carry the previous heuristic's fact label.
    return (
        source_type == "self_statement"
        and classify_claim_strength(content, {}).get("claim_strength") == "preference_signal"
    )
