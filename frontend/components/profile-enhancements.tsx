"use client";

import { useEffect, useState } from "react";
import type { EvidenceItem, InterviewStory, Profile, ViewPreferences } from "@/lib/api";
import {
  createInterviewStory, deleteInterviewStory, getInterviewStories,
  getViewPreferences, putViewPreferences,
} from "@/lib/api";
import { buildCapabilityCards } from "@/lib/profile-views";

const MODULE_LABELS: Record<string, string> = {
  skill_matrix: "技能矩阵",
  experience_timeline: "经历时间线",
  interest: "兴趣线索",
  target_role: "目标角色",
  evidence_health: "证据健康度",
  work_values: "工作价值观",
  constraints: "约束条件",
  custom_dimensions: "自定义维度",
  learning_progress: "学习进度",
  interview_stories: "面试故事库",
};

export function CapabilityCards({ profile, evidence }: {
  profile: Profile | null; evidence: EvidenceItem[];
}) {
  const cards = buildCapabilityCards(profile, evidence);
  if (!cards.length) return <p className="insight-empty">生成画像后显示能力证据卡。</p>;
  return (
    <div className="capability-grid">
      {cards.map((card) => (
        <article key={card.id}>
          <div><strong>{card.name}</strong><span className="pill">{card.status}</span></div>
          <dl>
            <dt>动作</dt><dd>{card.action}</dd>
            <dt>环境</dt><dd>{card.environment}</dd>
            <dt>证据</dt><dd>{card.evidenceIds.length ? `${card.evidenceIds.length} 条可回查` : "待补"}</dd>
          </dl>
          <small>{card.category} · {card.evidenceIds.slice(0, 2).join(" / ")}</small>
        </article>
      ))}
    </div>
  );
}

export function ProfileModes({ userId, onNotice }: {
  userId: string; onNotice: (text: string) => void;
}) {
  const [prefs, setPrefs] = useState<ViewPreferences | null>(null);
  const [stories, setStories] = useState<InterviewStory[]>([]);
  const [storyTitle, setStoryTitle] = useState("");
  const [storyAction, setStoryAction] = useState("");
  const [storyEvidence, setStoryEvidence] = useState("");

  async function refresh() {
    const [preferenceData, storyData] = await Promise.all([
      getViewPreferences(userId), getInterviewStories(userId),
    ]);
    setPrefs(preferenceData);
    setStories(storyData.stories);
  }

  useEffect(() => {
    void Promise.all([getViewPreferences(userId), getInterviewStories(userId)])
      .then(([preferenceData, storyData]) => {
        setPrefs(preferenceData);
        setStories(storyData.stories);
      })
      .catch(() => undefined);
  }, [userId]);

  function changeMode(mode: string) {
    if (!prefs) return;
    void putViewPreferences(userId, {
      user_id: userId, mode, modules: prefs.modules,
    }).then((result) => {
      setPrefs((current) => current ? { ...current, mode: result.mode, mode_label: result.mode_label } : current);
      onNotice(`已切换为「${result.mode_label}」，只改变展示与软排序，不改事实画像。`);
    }).catch((error) => onNotice(error instanceof Error ? error.message : "切换失败"));
  }

  function toggleModule(key: string, value: boolean) {
    if (!prefs) return;
    const modules = { ...prefs.modules, [key]: value };
    void putViewPreferences(userId, { user_id: userId, mode: prefs.mode, modules })
      .then(() => setPrefs((current) => current ? { ...current, modules } : current))
      .catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"));
  }

  function addStory() {
    if (!storyTitle.trim()) return;
    void createInterviewStory(userId, {
      user_id: userId,
      title: storyTitle.trim(),
      action: storyAction,
      evidence_ids: storyEvidence.trim() ? [storyEvidence.trim()] : [],
    }).then((result) => {
      onNotice(`故事已保存：${result.status}`);
      setStoryTitle(""); setStoryAction(""); setStoryEvidence("");
      void refresh();
    }).catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"));
  }

  return (
    <section className="profile-modes" aria-label="画像模式与面试故事库">
      <div className="modes-head">
        <span>PROFILE MODES</span>
        <h3>选择你现在的用途</h3>
        <p>{prefs?.note ?? "模式只改展示和推荐软排序，不改事实、证据或匹配分。"}</p>
      </div>
      <div className="mode-chips">
        {prefs?.available_modes.map((mode) => (
          <button
            type="button" key={mode.key}
            className={prefs.mode === mode.key ? "active" : ""}
            onClick={() => changeMode(mode.key)}
          >{mode.label}</button>
        ))}
      </div>
      <details className="module-switches">
        <summary>显示模块开关（{prefs ? Object.values(prefs.modules).filter(Boolean).length : 0} 项启用）</summary>
        <div className="module-grid">
          {prefs && Object.entries(prefs.modules).map(([key, value]) => (
            <label key={key}>
              <input type="checkbox" checked={value} onChange={(event) => toggleModule(key, event.target.checked)} />
              {MODULE_LABELS[key] ?? key}
            </label>
          ))}
        </div>
      </details>
      <div className="story-library">
        <h4>面试故事库</h4>
        <p>每条故事记录一个可复述的经历；填 Evidence ID 才能算「证据支持」，否则标为待补。</p>
        <div className="story-form">
          <input value={storyTitle} placeholder="故事标题" onChange={(event) => setStoryTitle(event.target.value)} />
          <input value={storyAction} placeholder="我做了什么" onChange={(event) => setStoryAction(event.target.value)} />
          <input value={storyEvidence} placeholder="Evidence ID（可选）" onChange={(event) => setStoryEvidence(event.target.value)} />
          <button type="button" disabled={!storyTitle.trim()} onClick={addStory}>添加故事</button>
        </div>
        <ul>
          {stories.map((story) => (
            <li key={story.id}>
              <div><strong>{story.title}</strong><span className="pill">{story.status}</span></div>
              {story.action && <p>{story.action}</p>}
              <small>{story.evidence_ids.join(" / ") || "无证据锚点"}</small>
              <button type="button" className="secondary" onClick={() => void deleteInterviewStory(userId, story.id).then(() => refresh())}>删除</button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
