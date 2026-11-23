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


def rewrite_links(out: Path, sha: str) -> tuple[int, list[str]]:
    """把指向未打包文件的相对链接改成 GitHub 链接。返回 (改写数, 错误列表)。

    错误包括：源目标在仓库里根本不存在（不能洗白成 404 的 GitHub 链接）。
    """
    count = 0
    problems: list[str] = []
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
            anchor = target[len(path_part):]
            changed = True
            count += 1
            return f"[{label}]({new}{anchor})"

        new_text = link_re.sub(repl, text)
        if changed:
            md.write_text(new_text, encoding="utf-8")
    return count, problems


def fix_homepage_links(out: Path, homepage_rel: str = "tutorials/从这里开始.md") -> int:
    """修正首页正文里的相对链接，使其在 Docsify 的 #/ 路由下可用。

    Docsify 把 homepage 渲染在站点根路由（#/），正文相对链接基于站点根解析；
    而 从这里开始.md 的原文链接基于 tutorials/ 目录（GitHub 浏览正确）。
    两边基准不同，无法用一份相对链接同时满足。打包时给首页正文的相对链接
    补上 tutorials/ 前缀（../ 开头的去掉 ..），GitHub 原文保持不变，两边都对。
    返回改写数量。
    """
    home = out / homepage_rel
    if not home.exists():
        return 0
    text = home.read_text(encoding="utf-8")
    count = 0

    def repl(m: re.Match) -> str:
        nonlocal count
        label, target = m.group(1), m.group(2).strip()
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return m.group(0)
        path_part, sep, anchor = target.partition("#")
        if not path_part:
            return m.group(0)
        # 指向 docs/ 或仓库根 README 的 ../ 链接：去掉 .. 即为站点根相对路径
        if path_part.startswith("../"):
            new_path = path_part[3:]
        elif path_part.startswith("./"):
            new_path = "tutorials/" + path_part[2:]
        elif "/" in path_part and path_part.split("/")[0] in ("tutorials", "docs", "examples"):
            return m.group(0)  # 已是站点根相对路径
        else:
            new_path = "tutorials/" + path_part
        count += 1
        return f"[{label}]({new_path}{sep}{anchor})"

    new_text = re.sub(r"\[([^\]]*)\]\(([^)]+)\)", repl, text)
    if count:
        home.write_text(new_text, encoding="utf-8")
    return count


def resolve_link(md: Path, out: Path, path_part: str) -> Path:
    """解析站内相对链接。普通篇章按 md 所在目录解析；首页（站点根路由）按 out 根解析。

    同一路径两种基准都试，任一命中即返回，兼顾 GitHub 原文的目录相对语义
    与 Docsify 首页的站点根语义。
    """
    candidates = [(md.parent / path_part), (out / path_part)]
    for c in candidates:
        if c.resolve().exists():
            return c.resolve()
    return candidates[0].resolve()


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
    ascii_punct = set(string.punctuation)
    slug = "".join("-" if ch.isspace() else ("" if ch in ascii_punct else ch) for ch in text)
    return re.sub(r"-+", "-", slug)   # 删标点后相邻空格会留下双 -,Docsify 会折叠


def check_anchors(out: Path) -> list[str]:
    """校验站内 md 链接的 #anchor 确实指向目标文件的某个标题。

    只检查指向已打包 .md 的相对链接；外链、mailto、纯锚点和源码行号锚点
    （#L10 这类）跳过，它们不是标题锚点。
    """
    problems: list[str] = []
    link_re = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
    anchor_cache: dict[Path, set[str]] = {}

    def headings(md: Path) -> set[str]:
        if md not in anchor_cache:
            found = set()
            for line in md.read_text(encoding="utf-8").splitlines():
                m = re.match(r"^#{1,6}\s+(.*)$", line)
                if m:
                    found.add(slugify_heading(m.group(1)))
            anchor_cache[md] = found
        return anchor_cache[md]

    for md in out.rglob("*.md"):
        for m in link_re.finditer(md.read_text(encoding="utf-8")):
            target = m.group(2).strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            path_part, sep, anchor = target.partition("#")
            if not sep or not anchor or anchor.startswith("L"):
                continue
            dest = resolve_link(md, out, path_part) if path_part else md.resolve()
            if not dest.exists() or dest.suffix.lower() != ".md":
                continue  # 坏文件由 check_no_local_links 负责
            try:
                dest.relative_to(out.resolve())
            except ValueError:
                continue  # 指向站外的链接，改写阶段会处理
            if anchor.lower() not in headings(dest):
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
    home_fixed = fix_homepage_links(out)
    # 同一坏文件会被 check_no_local_links 和 rewrite_links 各报一次，去重保持输出干净
    problems = list(dict.fromkeys(check_no_local_links(out) + rewrite_problems + check_anchors(out)))
    denied = deny_scan(out)

    print(f"artifact: {out}")
    print(f"files: {sum(1 for p in out.rglob('*') if p.is_file())}")
    print(f"commit link sha: {sha}")
    print(f"links rewritten to GitHub: {rewritten}")
    print(f"homepage links prefixed with tutorials/: {home_fixed}")
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
