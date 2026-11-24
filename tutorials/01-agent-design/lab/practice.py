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


def write_text(path: Path, value: str) -> None:
    with NamedTemporaryFile(dir=path.parent, delete=False) as file:
        temporary = Path(file.name)
    try:
        temporary.write_text(value, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def new_workspace(workspace: Path) -> None:
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


def open_exercise(workspace: Path, lesson: str, manifest: dict) -> None:
    copied = (workspace / "backend").resolve()
    updates: dict[Path, str] = {}
    for filename, symbols in LESSONS[lesson]["files"].items():
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
            lines[start:end] = [stub]
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


def check_exercise(workspace: Path, lesson: str) -> int:
    selected = LESSONS.values() if lesson == "all" else (LESSONS[lesson],)
    targets = dict.fromkeys(test for group in selected for test in group["tests"])
    tests = [test for test in targets if "::" not in test or test.split("::")[0] not in targets]
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=workspace / "backend",
        env=demo_environment("sqlite+aiosqlite:///:memory:"),
        check=False,
    ).returncode


def demo_environment(database_url: str) -> dict[str, str]:
    return {
        **os.environ,
        "DATABASE_URL": database_url,
        "AUTH_MODE": "disabled",
        "MCP_AUTH_MODE": "disabled",
        "API_PREFIX": "/api/v1",
        "AUTO_CREATE_SCHEMA": "true",
        "AI_PROVIDER": "demo",
        "RETRIEVAL_BACKEND": "local",
        "CHECKPOINT_BACKEND": "memory",
        "OTEL_ENABLED": "false",
    }


def run_demo(workspace: Path, command: str, port: int = 8030) -> int:
    backend = workspace / "backend"
    database = "agent-practice.sqlite3"
    if command == "serve":
        call = ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)]
    else:
        if not (backend / database).exists():
            raise ValueError("Start the practice API first so it creates the SQLite schema.")
        call = ["app.runtime.worker"]
    return subprocess.run(
        [sys.executable, "-m", *call],
        cwd=backend,
        env=demo_environment(f"sqlite+aiosqlite:///./{database}"),
        check=False,
    ).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("new", help="Create a fresh practice copy.")
    commands.add_parser("open", help="Prepare the selected functions for editing.").add_argument(
        "lesson", choices=LESSONS,
    )
    commands.add_parser("check", help="Run the relevant real tests on your copy.").add_argument(
        "lesson", choices=(*LESSONS, "all"),
    )
    commands.add_parser("serve", help="Run the practice API on the loopback address.").add_argument(
        "--port", type=int, default=8030,
    )
    commands.add_parser("worker", help="Run a Worker against the same practice SQLite database.")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.command == "new":
            new_workspace(workspace)
            return 0
        manifest = json.loads((workspace / MANIFEST).read_text(encoding="utf-8"))
        copied = (workspace / "backend").resolve()
        if manifest["source"] != str(BACKEND) or not copied.is_relative_to(workspace):
            raise ValueError("This is not a practice copy created from this source checkout.")
        if copied == BACKEND:
            raise ValueError("The original backend cannot be used as a practice workspace.")
        if args.command == "open":
            open_exercise(workspace, args.lesson, manifest)
            return 0
        if args.command == "check":
            return check_exercise(workspace, args.lesson)
        return run_demo(workspace, args.command, getattr(args, "port", 8030))
    except KeyboardInterrupt:
        return 130
    except (OSError, SyntaxError, ValueError) as exc:
        parser.exit(2, f"{exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
