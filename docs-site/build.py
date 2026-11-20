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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "docs-site"

# 只打包这些目录/文件（相对仓库根）
INCLUDE_DIRS = ["tutorials", "docs"]
INCLUDE_FILES = ["README.md"]
# docs 下的图片等公开素材一并带上
ASSET_SUFFIXES = {".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp"}

# 站点壳里本来就有的文件，直接复制
SHELL_FILES = ["index.html", "_sidebar.md", "_coverpage.md", ".nojekyll"]
SHELL_DIRS = ["vendor"]

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


def rewrite_links(out: Path, sha: str) -> int:
    """把指向未打包文件的相对链接改成 GitHub 链接。返回改写数量。"""
    count = 0
    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    packed = {
        str(p.relative_to(out)).replace("\\", "/")
        for p in out.rglob("*") if p.is_file()
    }

    for md in out.rglob("*.md"):
        text = md.read_text(encoding="utf-8")
        changed = False

        def repl(m: re.Match) -> str:
            nonlocal changed, count
            label, target = m.group(1), m.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                return m.group(0)
            path_part = target.split("#")[0]
            if not path_part:
                return m.group(0)
            resolved = (md.parent / path_part).resolve()
            # 站点里确实有这个文件，保留相对链接（Docsify 路由可处理）
            try:
                rel_to_out = resolved.relative_to(out.resolve()).as_posix()
            except ValueError:
                rel_to_out = ""
            if rel_to_out in packed:
                return m.group(0)
            # 未打包的文件（源码/示例/目录/未发布篇章）→ GitHub 固定链接
            # 从仓库根反推原始相对路径：md 在 out 里的位置对应它在 ROOT 里的位置
            md_rel = md.relative_to(out).as_posix()          # 如 docs/architecture.md
            original_md = (ROOT / md_rel).parent             # 仓库里该 md 的原始目录
            original_target = (original_md / path_part).resolve()
            try:
                rel_to_root = original_target.relative_to(ROOT.resolve()).as_posix()
            except ValueError:
                return m.group(0)
            new = github_url(rel_to_root.rstrip("/"), sha)
            changed = True
            count += 1
            return f"[{label}]({new})"

        new_text = link_re.sub(repl, text)
        if changed:
            md.write_text(new_text, encoding="utf-8")
    return count


def check_no_local_links(out: Path) -> list[str]:
    """校验输出里没有指向仓库内未打包文件的相对链接。"""
    problems: list[str] = []
    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    for md in out.rglob("*.md"):
        for m in link_re.finditer(md.read_text(encoding="utf-8")):
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part = target.split("#")[0]
            if not path_part:
                continue
            if not (md.parent / path_part).resolve().exists():
                problems.append(f"{md.relative_to(out)}: {target}")
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
    rewritten = rewrite_links(out, sha)
    problems = check_no_local_links(out)
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
