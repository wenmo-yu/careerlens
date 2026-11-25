"use client";

import { useState } from "react";
import type { Course, LearningPlanStep, RoleSuggestion } from "@/lib/api";

const STATUS_OPTIONS = ["待开始", "进行中", "待提交作品", "已核对", "暂停"];

export function RoleSuggestions({ rows }: { rows: RoleSuggestion[] }) {
  if (!rows.length) return <p className="insight-empty">先导入证据并生成画像，再查看职业方向建议。</p>;
  return (
    <div className="role-grid">
      {rows.map((row) => (
        <article key={row.role_id}>
          <span>{row.family}</span>
          <h4>{row.name}</h4>
          <div className="role-coverage"><div className="bar"><i style={{ width: `${row.coverage * 100}%` }} /></div><b>{Math.round(row.coverage * 100)}%</b></div>
          <p>{row.reason}</p>
          <small>匹配必需：{row.matched_required.join("、") || "暂无"}</small>
          <small>缺口：{row.gaps.join("、") || "无"}</small>
          <small>可回查证据 {row.evidence_ids.length} 条 · {row.source_note}</small>
        </article>
      ))}
    </div>
  );
}

export function CourseCatalog({ courses, skill }: { courses: Course[]; skill?: string }) {
  const rows = skill ? courses.filter((row) => row.skill.toLowerCase() === skill.toLowerCase()) : courses;
  if (!rows.length) return <p className="insight-empty">当前技能在目录里没有对应资源。</p>;
  return (
    <div className="course-catalog">
      <div className="catalog-head">
        <h4>本地课程目录</h4>
        <p>按技能关联的公开学习资源，标注许可、成本与核对日期；链接指向原始站点。</p>
      </div>
      <div className="course-grid">
      {rows.map((row) => (
        <article key={row.course_id}>
          <div><span>{row.level} · {row.format}</span><b>{row.estimated_hours}h</b></div>
          <h4><a href={row.url} target="_blank" rel="noreferrer">{row.title}</a></h4>
          <small>{row.provider} · {row.language} · {row.license} · {row.cost}</small>
          <p>{row.verification}</p>
          <small>先修：{row.prerequisites.join("、") || "无"} · 核对于 {row.last_checked_at}</small>
        </article>
      ))}
      </div>
    </div>
  );
}

export function LearningBoard({ steps, onProgress }: {
  steps: LearningPlanStep[];
  onProgress: (step: LearningPlanStep, status: string) => void;
}) {
  const [statusOverrides, setStatusOverrides] = useState<Record<string, string>>({});
  if (!steps.length) return <p className="insight-empty">完成岗位分析后可生成按周排布的学习计划。</p>;
  return (
    <div className="learning-board">
      {steps.map((step) => {
        const status = statusOverrides[step.skill] ?? step.progress_status ?? "待开始";
        return (
          <article key={`${step.stage}-${step.skill}`}>
            <div className="learning-week">
              <b>W{step.start_week ?? step.stage}</b>
              <span>{step.weeks ?? 1} 周 · {step.estimated_hours ?? 0} 小时</span>
            </div>
            <div className="learning-body">
              <h4>{step.skill} <small>Level {step.current_level ?? 1} → {step.target_level ?? 2}</small></h4>
              <p>{step.goal}</p>
              {!!step.resources?.length && <ul>{step.resources.map((resource) => (
                <li key={resource.course_id}><a href={resource.url} target="_blank" rel="noreferrer">{resource.title}</a>（{resource.estimated_hours}h）</li>
              ))}</ul>}
              <small className="insight-note">验收：{step.verification || step.goal}</small>
              <div className="learning-actions">
                <select value={status} onChange={(event) => {
                  setStatusOverrides((current) => ({ ...current, [step.skill]: event.target.value }));
                  onProgress(step, event.target.value);
                }}>
                  {STATUS_OPTIONS.map((option) => <option key={option}>{option}</option>)}
                </select>
                <small>产物：{step.deliverables.join("、") || "待定义"}</small>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
