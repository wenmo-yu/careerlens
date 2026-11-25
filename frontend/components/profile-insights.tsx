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

const CATEGORY_LABEL: Record<string, string> = {
  skill: "技能",
  target_role: "目标岗位",
  education: "教育",
  project: "项目",
  experience: "经历",
  interest: "兴趣",
  certificate: "证书",
  language: "语言",
};
const labelOf = (category: string) => CATEGORY_LABEL[category] ?? category;

const STATUS_LABEL: Record<string, string> = {
  confirmed: "已确认",
  supported: "证据支持",
  weak: "自报",
  pending: "待补证据",
};

/** Category distribution drawn as a real radial chart, with a table fallback. */
export function ProfileRadar({ profile }: { profile: Profile | null }) {
  const rows = buildCategoryRadar(profile);
  const max = Math.max(1, ...rows.map((row) => row.count));
  if (!rows.length) return <Empty text="导入证据并生成画像后，这里按类别显示条目分布。" />;
  if (rows.length < 3) {
    return (
      <div className="insight-block">
        <h4>画像分布</h4>
        <div className="radar-bars">
          {rows.map((row) => (
            <div className="radar-row" key={row.category}>
              <span>{labelOf(row.category)}</span>
              <div className="bar"><i style={{ width: `${(row.count / max) * 100}%` }} /></div>
              <b>{row.count}</b>
            </div>
          ))}
        </div>
        <p className="insight-note">类别少于三类时用条形展示，避免雷达图退化。</p>
        <details><summary>查看文字表格</summary><table><thead><tr><th>类别</th><th>条目数</th></tr></thead><tbody>{rows.map((row) => <tr key={row.category}><td>{row.category}</td><td>{row.count}</td></tr>)}</tbody></table></details>
      </div>
    );
  }

  const n = rows.length;
  const cx = 118;
  const cy = 104;
  const radius = 66;
  const angle = (index: number) => (Math.PI * 2 * index) / n - Math.PI / 2;
  const at = (index: number, ratio: number): [number, number] => [
    cx + Math.cos(angle(index)) * radius * ratio,
    cy + Math.sin(angle(index)) * radius * ratio,
  ];
  const ring = (ratio: number) => rows.map((_, index) => at(index, ratio).join(",")).join(" ");
  const shape = rows.map((row, index) => at(index, row.count / max).join(",")).join(" ");
  const summary = rows.map((row) => `${labelOf(row.category)} ${row.count}`).join("，");

  return (
    <div className="insight-block">
      <h4>画像分布</h4>
      <div className="radar-chart">
        <svg viewBox="0 0 236 208" role="img" aria-label={`画像类别分布：${summary}`}>
          {[0.33, 0.66, 1].map((ratio) => (
            <polygon key={ratio} points={ring(ratio)} className="radar-ring" />
          ))}
          {rows.map((row, index) => {
            const [x, y] = at(index, 1);
            return <line key={row.category} x1={cx} y1={cy} x2={x} y2={y} className="radar-axis" />;
          })}
          <polygon points={shape} className="radar-area" />
          {rows.map((row, index) => {
            const [x, y] = at(index, row.count / max);
            return <circle key={row.category} cx={x} cy={y} r={2.8} className="radar-dot" />;
          })}
          {rows.map((row, index) => {
            const [x, y] = at(index, 1.26);
            const anchor = x > cx + 4 ? "start" : x < cx - 4 ? "end" : "middle";
            return (
              <text key={row.category} x={x} y={y + 3} textAnchor={anchor} className="radar-label">
                {labelOf(row.category)}
              </text>
            );
          })}
        </svg>
      </div>
      <div className="radar-legend">
        {rows.map((row) => <span key={row.category}>{labelOf(row.category)}<b>{row.count}</b></span>)}
      </div>
      <details>
        <summary>查看文字表格</summary>
        <table>
          <thead><tr><th>类别</th><th>条目数</th></tr></thead>
          <tbody>{rows.map((row) => <tr key={row.category}><td>{row.category}</td><td>{row.count}</td></tr>)}</tbody>
        </table>
      </details>
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
            <div><strong>{row.name}</strong><span className={`pill ${row.status}`}>{STATUS_LABEL[row.status] ?? row.status}</span></div>
            <span className="level-scale" role="img" aria-label={`等级 ${row.level} / 5`}>
              {[1, 2, 3, 4, 5].map((n) => <i key={n} className={n <= row.level ? "on" : ""} />)}
            </span>
            <small>L{row.level} · {row.evidenceCount} 条证据 · 可信{row.confidence >= .9 ? "高" : row.confidence >= .8 ? "中" : "低"}</small>
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
  const pct = (value: number) => Math.round((value / total) * 100);
  return (
    <div className="insight-block">
      <h4>证据覆盖度</h4>
      <div className="coverage-bar" role="img" aria-label={`有证据 ${supported}，弱证据 ${weak}，无证据 ${missing}`}>
        <span style={{ width: `${(supported / total) * 100}%` }} className="supported" />
        <span style={{ width: `${(weak / total) * 100}%` }} className="weak" />
        <span style={{ width: `${(missing / total) * 100}%` }} className="missing" />
      </div>
      <div className="coverage-legend">
        <span><i className="dot supported" />有证据 {supported} · {pct(supported)}%</span>
        <span><i className="dot weak" />弱证据 {weak} · {pct(weak)}%</span>
        <span><i className="dot missing" />无证据 {missing} · {pct(missing)}%</span>
      </div>
      <details className="insight-method">
        <summary>统计口径</summary>
        <p>{overview.methodology}</p>
      </details>
      <p className="insight-note">统计时间：{overview.generated_at.slice(0, 19).replace("T", " ")}</p>
    </div>
  );
}
