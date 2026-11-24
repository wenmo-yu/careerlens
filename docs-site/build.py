#!/usr/bin/env python3
"""Build the Docsify site artifact for GitHub Pages.

职责：
1. 把站点壳 + 选定的教程/文档 Markdown 复制进输出目录，保留目录层级；
2. 把指向未打包文件（源码、示例脚本、未发布篇章）的相对链接改为 GitHub 固定链接；
3. 不把 .env、数据库、真实简历、缓存等敏感/无关文件带进站点；
4. 校验输出里没有指向本地文件的相对链接残留。

只用 Python 标准库。用法：
    python3 docs-site/build.py <output_dir> [commit_sha]
commit_sha 缺省用 git rev-parse HEAD，用于生成 GitHub 链接。
"""
from __future__ import annotations

import re
import shutil
import string
import subprocess
import sys
from html import escape
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs-site"

# 只打包这些目录/文件（相对仓库根）
INCLUDE_DIRS = ["tutorials", "docs"]
INCLUDE_FILES = ["README.md"]
# docs 下的图片等公开素材一并带上
ASSET_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}

# 站点壳里本来就有的文件，直接复制
SHELL_FILES = [
    "index.html", "mermaid-docsify.js", "foundations-lab.html",
    "_sidebar.md", "_coverpage.md", ".nojekyll",
]
SHELL_DIRS = ["vendor"]
SITE_NAVIGATION = {"tutorials/从这里开始.md", "_sidebar.md", "_coverpage.md"}
MARKDOWN_LINK = re.compile(r"(!?)\[([^\]]*)\]\(([^)]+)\)")

# 绝不进站点的东西
DENY_NAMES = {".env", ".env.example", ".env.production.example"}
DENY_PARTS = {".git", "node_modules", "__pycache__", ".venv", ".cache"}


def github_url(rel_path: str, sha: str) -> str:
    return f"https://github.com/wenmo-yu/careerlens/blob/{sha}/{rel_path}"


def sha_or_head(explicit: str | None) -> str:
    if explicit:
        return explicit
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout.strip()
    except Exception:
        return "main"


def copy_sources(out: Path) -> None:
    """复制站点壳与选定 Markdown/素材，保留目录层级。"""
    for name in SHELL_FILES:
        src = SITE / name
        if src.exists():
            shutil.copy2(src, out / name)
    for name in SHELL_DIRS:
        src = SITE / name
        if src.is_dir():
            shutil.copytree(src, out / name, dirs_exist_ok=True)

    for d in INCLUDE_DIRS:
        src_root = ROOT / d
        for src in src_root.rglob("*"):
            if not src.is_file():
                continue
            rel = src.relative_to(ROOT)
            if any(p in DENY_PARTS for p in rel.parts) or src.name in DENY_NAMES:
                continue
            if src.suffix.lower() in ASSET_SUFFIXES or src.suffix.lower() == ".md":
                dst = out / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    for name in INCLUDE_FILES:
        src = ROOT / name
        if src.exists():
            shutil.copy2(src, out / name)


def rewrite_links(out: Path, sha: str) -> tuple[int, list[str]]:
    """生成站内导航链接和未打包文件的 GitHub 固定链接。

    首页既在根路由显示，也能从独立的 Markdown 路由打开。首页和公共侧栏
    都从站点根寻址，以便从任何篇章访问同一个目标。原始 Markdown 保留仓库相对链接。
    """
    count = 0
    problems: list[str] = []
    packed = {
        str(p.relative_to(out)).replace("\\", "/")
        for p in out.rglob("*") if p.is_file()
    }

    for md in out.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        md_rel = md.relative_to(out).as_posix()
        changed = False

        def repl(m: re.Match) -> str:
            nonlocal changed, count
            image, label, target = m.groups()
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#", "/")):
                return m.group(0)
            path_part, sep, anchor = target.partition("#")
            if not path_part:
                return m.group(0)
            resolved = resolve_link(md, out, path_part)
            try:
                rel_to_out = resolved.relative_to(out.resolve()).as_posix()
            except ValueError:
                rel_to_out = ""
            if rel_to_out in packed:
                if md_rel in SITE_NAVIGATION:
                    changed = True
                    if image:
                        # 浏览器从 index.html 加载资源，路径不会跟着 Docsify 的 hash 路由变化。
                        src = escape(f"{rel_to_out}{sep}{anchor}", quote=True)
                        return f'<img src="{src}" alt="{escape(label, quote=True)}">'
                    return f"[{label}](/{rel_to_out}{sep}{anchor})"
                return m.group(0)
            # 未打包的文件（源码/示例/目录/未发布篇章）→ GitHub 固定链接
            # 从仓库根反推原始相对路径：md 在 out 里的位置对应它在 ROOT 里的位置
            original_md = (ROOT / md_rel).parent
            original_target = (original_md / unquote(path_part)).resolve()
            # 源目标不存在就不能改写成 GitHub 链接——那会生成一个 404 的坏链
            if not original_target.exists():
                problems.append(f"{md.relative_to(out)}: {target} (source not found)")
                return m.group(0)
            try:
                rel_to_root = original_target.relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                return m.group(0)
            new = github_url(rel_to_root.rstrip("/"), sha)
            # 保留锚点（如 #L10），改写时不能丢
            changed = True
            count += 1
            return f"{image}[{label}]({new}{sep}{anchor})"

        new_text = MARKDOWN_LINK.sub(repl, text)
        if changed:
            md.write_text(new_text, encoding="utf-8")
    return count, problems


def resolve_link(md: Path, out: Path, path_part: str) -> Path:
    """和 Docsify 一致，前导斜杠从站点根解析，其余从文档所在目录解析。"""
    path_part = unquote(path_part)
    if path_part.startswith("/"):
        return (out / path_part.lstrip("/")).resolve()
    return (md.parent / path_part).resolve()


def check_no_local_links(out: Path) -> list[str]:
    """校验输出里没有指向仓库内未打包文件的相对链接。"""
    problems: list[str] = []
    for md in out.rglob("*.md"):
        for m in MARKDOWN_LINK.finditer(md.read_text(encoding="utf-8")):
            target = m.group(3).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#")[0]
            if not path_part:
                continue
            if not resolve_link(md, out, path_part).exists():
                problems.append(f"{md.relative_to(out)}: {target}")
    return problems


def slugify_heading(text: str) -> str:
    """按 Docsify 4.x 实测的标题锚点规则生成 id（用无头 Chrome 核对过）。

    实测规则：去 markdown 强调符（`*_`）、小写化、空白转 `-`，
    去掉 **ASCII 标点**（如 `/`、`&`、`.`），但保留 **全角标点**
    （`：？（）｜，`）——slugify 库只处理 ASCII punctuation。
    例：「观察 3：用两份合成 DOCX，亲手验证两级去重」→
    `观察-3：用两份合成-docx，亲手验证两级去重`；
    「与 WeKnora / WorkBuddy 的实现对照」→
    `与-weknora-workbuddy-的实现对照`（ASCII `/` 被删）。
    """
    text = re.sub(r"`|\*", "", text).strip().lower()
    punctuation = set(string.punctuation) - {"-", "_"}
    text = re.sub(r"[\u2000-\u206f\u2e00-\u2e7f]", "", text)
    slug = "".join("-" if ch.isspace() else ("" if ch in punctuation else ch) for ch in text)
    slug = re.sub(r"-+", "-", slug)
    return re.sub(r"^([0-9])", r"_\1", slug)


def check_anchors(out: Path) -> list[str]:
    """校验同页跳转和已打包文档之间的标题链接。"""
    problems: list[str] = []
    anchor_cache: dict[Path, set[str]] = {}

    def headings(md: Path) -> set[str]:
        if md not in anchor_cache:
            found = set()
            duplicates: dict[str, int] = {}
            for line in md.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^#{1,6}\s+(.*)$", line)
                if m:
                    slug = slugify_heading(m.group(1))
                    index = duplicates.get(slug, 0)
                    found.add(f"{slug}-{index}" if index else slug)
                    duplicates[slug] = index + 1
            anchor_cache[md] = found
        return anchor_cache[md]

    for md in out.rglob("*.md"):
        for m in MARKDOWN_LINK.finditer(md.read_text(encoding="utf-8")):
            target = m.group(3).strip()
            if target.startswith(("http://", "https://", "mailto:")):
                continue
            path_part, sep, anchor = target.partition("#")
            if not sep or not anchor:
                continue
            dest = resolve_link(md, out, path_part) if path_part else md.resolve()
            if not dest.exists() or dest.suffix.lower() != ".md":
                continue  # 坏文件由 check_no_local_links 负责
            try:
                dest.relative_to(out.resolve())
            except ValueError:
                continue  # 指向站外的链接，改写阶段会处理
            if unquote(anchor) not in headings(dest):
                problems.append(f"{md.relative_to(out)}: {target} (anchor not found)")
    return problems


def deny_scan(out: Path) -> list[str]:
    """拒绝敏感/无关文件进入站点。"""
    hits = []
    for p in out.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(out)
        if p.name in DENY_NAMES or any(part in DENY_PARTS for part in rel.parts):
            hits.append(str(rel))
    return hits


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: python3 docs-site/build.py <output_dir> [commit_sha]", file=sys.stderr)
        return 2
    out = Path(sys.argv[1]).resolve()
    sha = sha_or_head(sys.argv[2] if len(sys.argv) > 2 else None)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)

    copy_sources(out)
    rewritten, rewrite_problems = rewrite_links(out, sha)
    # 同一坏文件会被 check_no_local_links 和 rewrite_links 各报一次，去重保持输出干净
    problems = list(dict.fromkeys(check_no_local_links(out) + rewrite_problems + check_anchors(out)))
    denied = deny_scan(out)

    print(f"artifact: {out}")
    print(f"files: {sum(1 for p in out.rglob('*') if p.is_file())}")
    print(f"commit link sha: {sha}")
    print(f"links rewritten to GitHub: {rewritten}")
    if denied:
        print("DENIED FILES FOUND:", denied, file=sys.stderr)
        return 1
    if problems:
        print("BROKEN LOCAL LINKS:", problems, file=sys.stderr)
        return 1
    print("OK: no broken local links, no denied files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
