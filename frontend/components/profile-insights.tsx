"use client";

import type { EvidenceItem } from "@/lib/api";
import {
  buildCategoryRadar, buildEvidenceTimeline, buildSkillMatrix,
  type ProfileOverview,
} from "@/lib/profile-views";
import type { Profile } from "@/lib/api";

function Empty({ text }: { text: string }) {
  return <p className="insight-empty">{text}</p>;
}

/** Five-category overview. Pure CSS bars, plus a text table fallback. */
export function ProfileRadar({ profile }: { profile: Profile | null }) {
  const rows = buildCategoryRadar(profile);
  const max = Math.max(1, ...rows.map((row) => row.count));
  if (!rows.length) return <Empty text="导入证据并生成画像后，这里按类别显示条目分布。" />;
  return (
    <div className="insight-block">
      <h4>画像分布</h4>
      <div className="radar-bars">
        {rows.map((row) => (
          <div className="radar-row" key={row.category}>
            <span>{row.category}</span>
            <div className="bar"><i style={{ width: `${(row.count / max) * 100}%` }} /></div>
            <b>{row.count}</b>
          </div>
        ))}
      </div>
      <details><summary>查看文字表格</summary><table><thead><tr><th>类别</th><th>条目数</th></tr></thead><tbody>{rows.map((row) => <tr key={row.category}><td>{row.category}</td><td>{row.count}</td></tr>)}</tbody></table></details>
    </div>
  );
}

export function SkillMatrix({ profile }: { profile: Profile | null }) {
  const rows = buildSkillMatrix(profile);
  if (!rows.length) return <Empty text="技能矩阵等待带证据的技能条目。" />;
  return (
    <div className="insight-block">
      <h4>技能矩阵 · 等级 × 可信度 × 证据</h4>
      <div className="matrix-grid">
        {rows.map((row) => (
          <article key={row.name}>
            <div><strong>{row.name}</strong><span className={`pill ${row.status}`}>{row.status}</span></div>
            <small>Level {row.level} / 5 · {row.evidenceCount} 条证据</small>
            <div className="bar"><i style={{ width: `${row.confidence * 100}%` }} /></div>
            <small>启发式可信度 {Math.round(row.confidence * 100)}%</small>
          </article>
        ))}
      </div>
      <p className="insight-note">等级与可信度来自抽取器启发式，用于排序和补证提醒，不是能力概率。</p>
    </div>
  );
}

export function EvidenceTimeline({ evidence }: { evidence: EvidenceItem[] }) {
  const rows = buildEvidenceTimeline(evidence);
  if (!rows.length) return <Empty text="证据时间线等待导入记录。" />;
  return (
    <div className="insight-block">
      <h4>证据时间线</h4>
      <ol className="timeline-list">
        {rows.slice(0, 30).map((row) => (
          <li key={row.id}>
            <time>{row.createdAt ? row.createdAt.slice(0, 10) : "时间未知"}</time>
            <div>
              <strong>{row.label}</strong>
              <small>{row.sourceType}{row.claimStrength === "preference_signal" ? " · 兴趣线索" : ""}</small>
              <p>{row.preview}</p>
            </div>
          </li>
        ))}
      </ol>
      <details><summary>查看文字表格</summary><table><thead><tr><th>时间</th><th>来源</th><th>类型</th></tr></thead><tbody>{rows.map((row) => <tr key={row.id}><td>{row.createdAt.slice(0, 10)}</td><td>{row.label}</td><td>{row.sourceType}</td></tr>)}</tbody></table></details>
    </div>
  );
}

export function CoverageCard({ overview }: { overview: ProfileOverview | null }) {
  if (!overview) return <Empty text="覆盖度需要画像概览数据；刷新后显示。" />;
  const { supported, weak, missing } = overview.coverage;
  const total = Math.max(1, supported + weak + missing);
  return (
    <div className="insight-block">
      <h4>证据覆盖度</h4>
      <div className="coverage-bar" role="img" aria-label={`有证据 ${supported}，弱证据 ${weak}，无证据 ${missing}`}>
        <span style={{ width: `${(supported / total) * 100}%` }} className="supported" />
        <span style={{ width: `${(weak / total) * 100}%` }} className="weak" />
        <span style={{ width: `${(missing / total) * 100}%` }} className="missing" />
      </div>
      <div className="coverage-legend">
        <span>有证据 {supported}</span><span>弱证据 {weak}</span><span>无证据 {missing}</span>
      </div>
      <p className="insight-note">{overview.methodology}</p>
      <p className="insight-note">统计时间：{overview.generated_at.slice(0, 19).replace("T", " ")}</p>
    </div>
  );
}
