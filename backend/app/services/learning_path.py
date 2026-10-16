"""A bounded, explainable plan derived from actual JD gaps and profile levels."""

from math import ceil

PRACTICE_TASKS: dict[str, tuple[str, str]] = {
    "MCP": ("实现一个带权限校验的 MCP Tool", "工具调用记录与鉴权测试"),
    "Kubernetes": ("把现有服务部署到本地 Kubernetes 集群", "部署清单与健康检查截图"),
    "RAG": ("构建小型检索评测集并比较召回结果", "召回指标与错例复盘"),
    "LangGraph": ("实现包含条件分支的状态图", "流程图与分支测试"),
    "FastAPI": ("实现一个带鉴权和测试的异步接口", "接口测试与运行说明"),
    "Docker": ("把项目打包成可复现的容器服务", "Dockerfile 与启动记录"),
    "PostgreSQL": ("为项目设计表结构、迁移与查询", "迁移文件与查询计划"),
}


def build_learning_path(matches: list[dict], *, title: str, weekly_hours: int) -> list[dict]:
    """Prioritize uncovered skills, then weakly supported required skills; cap scope."""
    candidates = [item for item in matches if item["status"] in {"gap", "partial"}]
    candidates.sort(
        key=lambda item: (
            0
            if item["status"] == "gap" and item["priority"] == "required"
            else 1
            if item["status"] == "gap"
            else 2
            if item["priority"] == "required"
            else 3,
            item.get("level", 0),
            item["name"],
        )
    )
    path: list[dict] = []
    next_week = 1
    for index, item in enumerate(candidates[:4], start=1):
        level = item.get("level", 0)
        hours = (
            (18 if item["priority"] == "required" else 10)
            if level == 0
            else (6 + max(0, 3 - level) * 3)
        )
        weeks = max(1, ceil(hours / weekly_hours))
        practice, artifact = PRACTICE_TASKS.get(
            item["name"],
            (f"围绕 {item['name']} 完成一个与目标岗位相关的最小实践", "项目说明与结果复盘"),
        )
        action = "从基础补齐" if level == 0 else f"从现有 Level {level} 继续加强"
        path.append(
            {
                "stage": index,
                "skill": item["name"],
                "priority": item["priority"],
                "current_level": level,
                "estimated_hours": hours,
                "start_week": next_week,
                "weeks": weeks,
                "goal": f"面向 {title}，{action} {item['name']}：{practice}，并形成可核验成果。",
                "deliverables": [artifact, "可引用的项目 Evidence"],
                "source_evidence_ids": item.get("evidence_ids", []),
            }
        )
        next_week += weeks
    return path
