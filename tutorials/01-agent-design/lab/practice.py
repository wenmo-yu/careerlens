"""Rebuild selected CareerLens Agent functions in a separate teaching copy."""

from __future__ import annotations

import argparse
import ast
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from tempfile import NamedTemporaryFile

LAB = Path(__file__).resolve().parent
ROOT = LAB.parents[2]
BACKEND = ROOT / "backend"
DEFAULT_WORKSPACE = ROOT / ".cache" / "agent-practice"
MANIFEST = ".careerlens-agent-practice.json"
TOOL_TEST = "tests/test_tutorial_mcp_tool.py"
MODEL_FILE = ".env.model"
MODEL_SETTINGS = {
    "AI_PROVIDER",
    "AI_BASE_URL",
    "AI_API_KEY",
    "AI_MODEL",
    "AI_TIMEOUT_SECONDS",
    "AI_INPUT_PRICE_PER_MILLION",
    "AI_OUTPUT_PRICE_PER_MILLION",
    "MODEL_ROLE_BINDINGS",
}

CHAT_TEST = "tests/test_profile_jobs_chat.py::test_career_chat_returns_traceable_evidence"
JOB_CHAT_TEST = (
    "tests/test_job_intelligence.py::test_copilot_uses_saved_job_analysis_and_keeps_memory_update_confirmed"
)
LESSONS = {
    "state": {
        "files": {"app/graph/career.py": ("run_career_graph",)},
        "tests": (CHAT_TEST,),
    },
    "routing": {
        "files": {
            "app/graph/career.py": ("understand_intent", "route_intent", "route_answer"),
        },
        "tests": (CHAT_TEST, JOB_CHAT_TEST),
    },
    "retrieval": {
        "files": {
            "app/graph/career.py": ("retrieve_evidence",),
            "app/services/knowledge.py": ("search_knowledge",),
        },
        "tests": ("tests/test_knowledge_mode.py",),
    },
    "tools": {
        "files": {
            "app/mcp/server.py": ("get_evidence",),
            TOOL_TEST: ("build_evidence_tool",),
        },
        "tests": (
            TOOL_TEST,
            "tests/test_mcp.py::test_mcp_exposes_complete_contract",
        ),
    },
    "answer": {
        "files": {
            "app/graph/career.py": ("compose_answer",),
            "app/services/citations.py": ("validated_citations",),
        },
        "tests": (
            CHAT_TEST,
            "tests/test_job_intelligence.py::test_chat_rejects_fabricated_inline_evidence_citation",
            "tests/test_job_intelligence.py::test_chat_accepts_only_valid_inline_and_list_citations",
        ),
    },
    "conversation": {
        "files": {"app/api/routes/chat.py": ("_load_history", "chat")},
        "tests": (
            "tests/test_profile_jobs_chat.py",
            JOB_CHAT_TEST,
            "tests/test_job_intelligence.py::test_deleted_evidence_blocks_reuse_of_job_analysis",
        ),
    },
    "memory": {
        "files": {
            "app/services/profile_updates.py": ("create_proposal", "decide_proposal"),
        },
        "tests": ("tests/test_model_and_profile_updates.py", "tests/test_atomic_profile_update.py"),
    },
    "coordinator": {
        "files": {
            "app/runtime/agents.py": (
                "verification_task",
                "Coordinator.delegate",
                "Coordinator.verify",
            ),
        },
        "tests": (
            "tests/test_run_runtime.py::test_coordinator_projects_context_and_rejects_foreign_citations",
            "tests/test_run_runtime.py::test_report_result_and_business_write_commit_once",
        ),
    },
}

FUNCTION_HINTS = {
    "run_career_graph": (
        "先确定 selected_thread；没有 thread_id 就给这次会话生成编号。",
        "组装业务状态和 configurable 执行配置，分别作为 ainvoke 的两个参数。",
        "等待图返回后，把选中的 thread_id 和最终状态交回接口。",
    ),
    "understand_intent": (
        "从 state 取 message，再按修改画像、依据、缺口、方向的顺序检查。",
        "返回 intent，并把本轮的候选列表和检索诊断初始化为空。",
    ),
    "route_intent": (
        "读取 intent，只对 memory_update 返回 memory_guidance。",
        "其他意图都返回图里的 retrieve_evidence 节点名。",
    ),
    "route_answer": (
        "同时满足 skill_gap 和存在 job_analysis，才走 compose_gap_answer。",
        "其余情况返回 compose_answer。返回的是节点名字。",
    ),
    "retrieve_evidence": (
        "先从 configurable 取数据库会话，再从状态和配置选 mode。",
        "有会话就查 knowledge；单独运行节点时只查 state 里的原始证据。",
        "把候选和诊断分别写进 retrieved_evidence 和 retrieval_diagnostics。",
    ),
    "search_knowledge": (
        "先检查 mode，按模式决定要调用哪一路检索。",
        "hybrid 用 zip_longest 交错两组候选，去掉空位并限制条数。",
        "结果以列表返回，另带模式、两路计数和来源类型。",
    ),
    "get_evidence": (
        "先检查 read 授权，再按 evidence_id 从数据库读取。",
        "同时检查记录存在和归属，失败时抛 ToolError。",
        "写入读审计后，用 _evidence_payload 把 ORM 记录整理成字典。",
    ),
    "build_evidence_tool": (
        "定义只接收 evidence_id 的内部函数，用 @tool 装饰。",
        "内部函数使用现成客户端和外层的 user_id 调 get_evidence。",
        "返回原文 content；外层函数返回已经登记好的工具。",
    ),
    "compose_answer": (
        "先准备本地备用答复；Demo 提供器直接返回这个结果。",
        "把本轮问题、证据和最近历史打包，再调用 generate_json。",
        "检查正文与引用，生成失败时返回备用答复并说明异常类型。",
    ),
    "validated_citations": (
        "先从正文提取内联 ID；正文含未知 ID 时直接抛错。",
        "过滤另外提供的 ID，只保留允许值并按第一次出现的顺序去重。",
    ),
    "_load_history": (
        "没有 thread_id 就返回空列表。",
        "按 user_id 和 thread_id 一起查消息，并按时间与 ID 排序。",
    ),
    "chat": (
        "检查访问权限，再读当前用户画像、证据和可用的岗位分析。",
        "核对会话归属，加载旧消息，把本轮数据交给 run_career_graph。",
        "用同一 UTC 时点及其后一微秒保存一问一答，提交后读回会话并组装 ChatResponse。",
    ),
    "create_proposal": (
        "先生成候选变更；非 Demo 提供器可提供验证过的结构化候选。",
        "保存待确认的草案，再把草案交给调用方核对。",
    ),
    "decide_proposal": (
        "锁定用户范围和草案，确认它存在且状态还在 pending。",
        "批准时创建有出处的纠正证据，并按草案更新画像与抑制记录。",
        "提交草案结果；批准时再尝试更新证据索引。",
    ),
    "verification_task": (
        "把两组 ID 变成集合，检查候选集合是否为允许集合的子集。",
        "通过时返回不重复的引用数量和诊断。",
    ),
    "Coordinator.delegate": (
        "先检查剩余预算，再检查角色是否登记在 SPECIALISTS。",
        "通过检查后扣减一次预算。",
        "等待已有的 _run_role 执行子图，返回它给出的结果。",
    ),
    "Coordinator.verify": (
        "把允许的 ID 和候选 ID 交给 evidence_verifier。",
        "从角色结果取数量，用 TaskSummary 交回核验摘要。",
    ),
}


def write_text(path: Path, value: str) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def new_workspace(workspace: Path, *, with_tool_test: bool = True) -> None:
    if workspace.is_relative_to(BACKEND):
        raise ValueError("Choose a workspace outside the original backend.")
    if workspace.exists():
        raise ValueError(f"Workspace already exists: {workspace}")
    workspace.mkdir(parents=True)
    copied = workspace / "backend"
    ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".env", ".env.*", "*.db", "*.sqlite*")
    for folder in ("app", "tests"):
        shutil.copytree(BACKEND / folder, copied / folder, ignore=ignore)
    shutil.copy2(BACKEND / "pyproject.toml", copied / "pyproject.toml")
    if with_tool_test:
        shutil.copy2(LAB / "mcp_tool_check.py", copied / TOOL_TEST)
    write_text(workspace / MANIFEST, json.dumps({"source": str(BACKEND), "opened": []}))
    print(f"Created {copied}")


def function_body(text: str, qualified_name: str) -> tuple[int, int]:
    nodes = ast.parse(text).body
    owner, dot, name = qualified_name.partition(".")
    if dot:
        classes = [node for node in nodes if isinstance(node, ast.ClassDef) and node.name == owner]
        nodes = classes[0].body if len(classes) == 1 else []
    else:
        name = owner
    functions = [
        node for node in nodes
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(functions) != 1:
        raise ValueError(f"Expected one function definition for {qualified_name}.")
    function = functions[0]
    if function.end_lineno is None:
        raise ValueError(f"Could not locate the end of {qualified_name}.")
    first = function.body[0]
    decorators = getattr(first, "decorator_list", ())
    start = min([first.lineno, *(decorator.lineno for decorator in decorators)])
    return start - 1, function.end_lineno


def open_exercise(
    workspace: Path, lesson: str, manifest: dict, *, lessons=LESSONS, hints=FUNCTION_HINTS
) -> None:
    copied = (workspace / "backend").resolve()
    updates: dict[Path, str] = {}
    for filename, symbols in lessons[lesson]["files"].items():
        path = (copied / filename).resolve()
        if not path.is_relative_to(copied):
            raise ValueError(f"Exercise file is outside the workspace: {path}")
        print(f"{path} ({', '.join(symbols)})")
        if lesson in manifest["opened"]:
            continue
        source_path = LAB / "mcp_tool_check.py" if filename == TOOL_TEST else BACKEND / filename
        source = source_path.read_text(encoding="utf-8")
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        for symbol in symbols:
            start, end = function_body("".join(lines), symbol)
            source_start, source_end = function_body(source, symbol)
            indent = lines[start][: len(lines[start]) - len(lines[start].lstrip())]
            stub = f'{indent}raise NotImplementedError("TODO {lesson}: {symbol}")\n'
            if lines[start:end] == [stub]:
                continue
            if lines[start:end] != source.splitlines(keepends=True)[source_start:source_end]:
                raise ValueError(f"{symbol} has local edits. Its body was kept.")
            comments = [
                f"{indent}# {step}. {hint}\n"
                for step, hint in enumerate(hints[symbol], start=1)
            ]
            lines[start:end] = [*comments, stub]
        contents = "".join(lines)
        ast.parse(contents, filename=str(path))
        updates[path] = contents
    if lesson in manifest["opened"]:
        print("Already opened. Your work is ready to continue.")
        return
    for path, contents in updates.items():
        write_text(path, contents)
    manifest["opened"].append(lesson)
    write_text(workspace / MANIFEST, json.dumps(manifest))
    print(f"Ready: {lesson}")


def check_exercise(workspace: Path, lesson: str, *, lessons=LESSONS) -> int:
    selected = lessons.values() if lesson == "all" else (lessons[lesson],)
    targets = dict.fromkeys(test for group in selected for test in group["tests"])
    tests = [test for test in targets if "::" not in test or test.split("::")[0] not in targets]
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=workspace / "backend",
        env=practice_environment("sqlite+aiosqlite:///:memory:"),
        check=False,
    ).returncode


def practice_environment(
    database_url: str, *, model_file: Path | None = None
) -> dict[str, str]:
    inherited = {
        key: value for key, value in os.environ.items() if key.upper() not in MODEL_SETTINGS
    }
    settings = {
        **inherited,
        "AI_PROVIDER": "demo",
        "DATABASE_URL": database_url,
        "AUTH_MODE": "disabled",
        "MCP_AUTH_MODE": "disabled",
        "API_PREFIX": "/api/v1",
        "AUTO_CREATE_SCHEMA": "true",
        "RETRIEVAL_BACKEND": "local",
        "RETRIEVAL_PROVIDER": "hash",
        "CHECKPOINT_BACKEND": "memory",
        "OTEL_ENABLED": "false",
    }
    if model_file is not None:
        from dotenv import dotenv_values

        settings.update(
            {
                key.upper(): value
                for key, value in dotenv_values(model_file, interpolate=False).items()
                if key.upper() in MODEL_SETTINGS and value is not None
            }
        )
    return settings


def run_demo(
    workspace: Path, command: str, port: int = 8030, *, use_model_config: bool = False
) -> int:
    backend = workspace / "backend"
    database = "agent-practice.sqlite3"
    model_file = backend / MODEL_FILE if use_model_config else None
    if model_file is not None and not model_file.is_file():
        raise ValueError(f"Create the practice model configuration first: {model_file}")
    if command == "serve":
        call = ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    else:
        if not (backend / database).exists():
            raise ValueError("Start the practice API first so it creates the SQLite schema.")
        call = ["app.runtime.worker"]
    return subprocess.run(
        [sys.executable, "-m", *call],
        cwd=backend,
        env=practice_environment(
            f"sqlite+aiosqlite:///./{database}", model_file=model_file
        ),
        check=False,
    ).returncode


def main(
    *,
    description: str = __doc__,
    default_workspace: Path = DEFAULT_WORKSPACE,
    default_port: int = 8030,
    lessons=LESSONS,
    hints=FUNCTION_HINTS,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--workspace", type=Path, default=default_workspace)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("new", help="Create a fresh practice copy.")
    commands.add_parser("open", help="Prepare the selected functions for editing.").add_argument(
        "lesson", choices=lessons,
    )
    commands.add_parser("check", help="Run the relevant real tests on your copy.").add_argument(
        "lesson", choices=(*lessons, "all"),
    )
    serve = commands.add_parser("serve", help="Run the practice API on the loopback address.")
    serve.add_argument("--port", type=int, default=default_port)
    worker = commands.add_parser(
        "worker", help="Run a Worker against the same practice SQLite database."
    )
    for process in (serve, worker):
        process.add_argument(
            "--use-model-config",
            action="store_true",
            help=f"Read model settings from the practice backend's {MODEL_FILE} file.",
        )
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.command == "new":
            new_workspace(
                workspace,
                with_tool_test=any(TOOL_TEST in group["files"] for group in lessons.values()),
            )
            return 0
        manifest = json.loads((workspace / MANIFEST).read_text(encoding="utf-8"))
        copied = (workspace / "backend").resolve()
        if manifest["source"] != str(BACKEND) or not copied.is_relative_to(workspace):
            raise ValueError("This is not a practice copy created from this source checkout.")
        if copied == BACKEND:
            raise ValueError("The original backend cannot be used as a practice workspace.")
        if args.command == "open":
            open_exercise(workspace, args.lesson, manifest, lessons=lessons, hints=hints)
            return 0
        if args.command == "check":
            return check_exercise(workspace, args.lesson, lessons=lessons)
        return run_demo(
            workspace,
            args.command,
            getattr(args, "port", default_port),
            use_model_config=args.use_model_config,
        )
    except KeyboardInterrupt:
        return 130
    except (OSError, SyntaxError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
