"use client";

import { useEffect, useState } from "react";
import { getSourceRegistry, importGitHubRepos, importPublicLinks, type SourceSpec } from "@/lib/api";

type LinkDraft = { url: string; title: string; note: string; confirmed: boolean };

export function ImportHub({ userId, onNotice }: {
  userId: string; onNotice: (text: string) => void;
}) {
  const [sources, setSources] = useState<SourceSpec[]>([]);
  const [draft, setDraft] = useState<LinkDraft>({
    url: "", title: "", note: "", confirmed: false,
  });
  const [token, setToken] = useState("");
  const [repos, setRepos] = useState("");
  const [repoConsent, setRepoConsent] = useState(false);
  const [githubBusy, setGithubBusy] = useState(false);

  useEffect(() => {
    void getSourceRegistry().then((payload) => setSources(payload.sources)).catch(() => undefined);
  }, []);

  function submitLink() {
    if (!draft.url.trim() || !draft.title.trim()) return;
    if (!draft.confirmed) {
      onNotice("请确认这条链接来自你自己的公开内容；系统不会访问链接。");
      return;
    }
    void importPublicLinks(userId, [{
      url: draft.url.trim(), title: draft.title.trim(),
      note: draft.note.trim(), confirmed: true,
    }]).then((result) => {
      onNotice(`已生成 ${result.created_count} 条证据卡，跳过 ${result.skipped_count} 条；系统未访问链接。`);
      setDraft({ url: "", title: "", note: "", confirmed: false });
    }).catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"));
  }

  function submitGithub() {
    const repoList = repos.split(/[\n,]+/).map((row) => row.trim()).filter(Boolean);
    if (token.trim().length < 20) {
      onNotice("请粘贴完整的只读令牌（通常以 github_pat_ 或 ghp_ 开头）。");
      return;
    }
    if (!repoConsent) {
      onNotice("请确认仓库属于你自己，且令牌只有只读权限。");
      return;
    }
    setGithubBusy(true);
    void importGitHubRepos(userId, token.trim(), repoList).then((result) => {
      onNotice(`已读取 ${result.created_count} 个仓库，跳过 ${result.skipped_count} 个；令牌未保存。`);
      setToken("");
      setRepos("");
      setRepoConsent(false);
    }).catch((error) => onNotice(
      error instanceof Error ? error.message : "GitHub 导入失败，令牌未保存。",
    )).finally(() => setGithubBusy(false));
  }

  return (
    <section className="import-hub" aria-label="导入来源清单">
      <div className="hub-head">
        <span>SOURCE REGISTRY</span>
        <h3>每个来源能证明什么，先说清楚</h3>
        <p>只做用户主动提供的四种方式：上传已有文件、当前页手动采集、粘贴公开链接、自备只读令牌。需注册应用的 OAuth 同步仍未实现，不会假装可用。</p>
      </div>
      <div className="source-grid">
        {sources.map((source) => (
          <article key={source.key} className={source.available ? "" : "unavailable"}>
            <div>
              <strong>{source.label}</strong>
              <span className={`pill ${source.auth_level.toLowerCase()}`}>{source.auth_label}</span>
            </div>
            <small>{source.formats.length ? source.formats.join(" / ") : "—"}</small>
            <p>{source.note}</p>
            {!source.available && <b className="not-ready">未实现 · 需平台对接</b>}
          </article>
        ))}
      </div>
      <div className="link-card-form">
        <h4>公开链接证据卡（代码平台 / 技术文章）</h4>
        <p>粘贴你自己的公开内容和链接，确认后才入库。系统只保存你填的文字，不访问链接、不证明账号归属。</p>
        <div>
          <input value={draft.url} placeholder="https://github.com/你/项目/pull/1" onChange={(event) => setDraft({ ...draft, url: event.target.value })} />
          <input value={draft.title} placeholder="标题，例如：我提交的 RAG 检索 PR" onChange={(event) => setDraft({ ...draft, title: event.target.value })} />
          <input value={draft.note} placeholder="补充说明（可选）" onChange={(event) => setDraft({ ...draft, note: event.target.value })} />
        </div>
        <label className="link-consent">
          <input type="checkbox" checked={draft.confirmed} onChange={(event) => setDraft({ ...draft, confirmed: event.target.checked })} />
          <span>我确认这是来自我自己的公开内容，并理解系统不会访问该链接。</span>
        </label>
        <button type="button" onClick={submitLink}>生成证据卡</button>
      </div>

      <div className="github-form">
        <h4>GitHub 仓库（自备只读令牌，无需注册应用）</h4>
        <p>
          用你自己创建的只读令牌读取仓库简介、语言、Star 与 README，生成可回查的证据。
          令牌只在本次请求使用：不写数据库、不写日志，刷新页面即丢失。不读 issues、PR、提交记录或令牌未授权的仓库。
        </p>
        <div className="github-row">
          <label>只读令牌
            <input type="password" value={token} autoComplete="off" spellCheck={false}
              placeholder="github_pat_… 或 ghp_…"
              onChange={(event) => setToken(event.target.value)} />
          </label>
          <label>仓库（可选，每行一个 owner/name；留空则取最近推送的 10 个）
            <textarea value={repos} placeholder={"octo/demo\nocto/another-repo"}
              onChange={(event) => setRepos(event.target.value)} />
          </label>
        </div>
        <label className="link-consent">
          <input type="checkbox" checked={repoConsent}
            onChange={(event) => setRepoConsent(event.target.checked)} />
          <span>我确认这些仓库属于我自己，令牌只勾选了 Contents 与 Metadata 的只读权限。</span>
        </label>
        <button type="button" disabled={githubBusy} onClick={submitGithub}>
          {githubBusy ? "读取中…" : "读取仓库并生成证据"}
        </button>
        <details className="github-guide">
          <summary>怎么创建一个最小权限的令牌（约 1 分钟）</summary>
          <ol>
            <li>GitHub 右上头像 → <code>Settings</code> → 左侧最下 <code>Developer settings</code>。</li>
            <li><code>Personal access tokens</code> → <code>Fine-grained tokens</code> → <code>Generate new token</code>。</li>
            <li><code>Repository access</code> 选 <code>Only select repositories</code>，只勾要导入的仓库。</li>
            <li>权限里把 <code>Contents</code> 设为 <code>Read-only</code>，<code>Metadata</code> 设为 <code>Read-only</code>（必选）。</li>
            <li>过期时间选 7 天或更短；生成后令牌只显示一次，复制回来粘贴。</li>
            <li>导入完成后可直接在 GitHub 删除该令牌；本系统没有保存它，删掉不影响已导入的证据。</li>
          </ol>
        </details>
      </div>
    </section>
  );
}
