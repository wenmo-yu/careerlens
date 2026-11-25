"use client";

import type { JobAnalysis } from "@/lib/api";
import { buildScoreBreakdown } from "@/lib/profile-views";

export function ScoreBreakdown({ analysis }: { analysis: JobAnalysis | null }) {
  const data = buildScoreBreakdown(analysis);
  if (!analysis) return <p className="insight-empty">{data.note}</p>;
  return (
    <div className="score-breakdown">
      <div className="score-breakdown-head">
        <span>SCORE BREAKDOWN</span>
        <b>{analysis.score}%</b>
      </div>
      <div className="score-breakdown-grid">
        <div><span>必需 / 加分</span><b>{data.required} / {data.preferred}</b></div>
        <div><span>strong / partial / gap</span><b>{data.strong} / {data.partial} / {data.gap}</b></div>
        <div><span>对照要求</span><b>{data.total} 项</b></div>
      </div>
      <p className="insight-note">{data.note}</p>
    </div>
  );
}

const CHAPTER_LABELS: Record<string, string> = {
  executive_summary: "摘要",
  core_capabilities: "核心能力",
  evidence_catalog: "证据目录",
  career_direction: "推荐方向",
  job_matching: "岗位匹配",
  skill_gaps: "能力缺口",
  learning_path: "学习路径",
  action_plan: "下一步行动",
};

export function ReportOverview({ content }: { content: Record<string, unknown> }) {
  const entries = Object.entries(content).filter(([, value]) => value !== undefined && value !== null);
  if (!entries.length) return <p className="insight-empty">报告内容等待生成。</p>;
  return (
    <div className="report-overview">
      {entries.map(([key, value]) => (
        <details key={key}>
          <summary>{CHAPTER_LABELS[key] ?? key}</summary>
          <div className="report-overview-body">
            {typeof value === "string" ? <p>{value}</p>
              : Array.isArray(value) ? <ul>{value.map((item, index) => <li key={index}>{typeof item === "string" ? item : JSON.stringify(item)}</li>)}</ul>
              : <pre>{JSON.stringify(value, null, 2)}</pre>}
          </div>
        </details>
      ))}
    </div>
  );
}
