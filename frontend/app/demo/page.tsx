import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { demoStory } from "@/lib/demo-story";

export const metadata: Metadata = {
  title: "虚构案例体验 · CareerLens",
  description: "用一组明确标注为虚构的经历和岗位要求，了解 CareerLens 的证据、画像与岗位分析流程。",
};

export default function DemoPage() {
  return (
    <main className="site-page detail-page demo-page">
      <SiteHeader active="demo" />
      <section className="detail-hero demo-hero"><div><span className="site-kicker">CASE STUDY / FICTIONAL DATA</span><h1>先看一个<br /><em>完整案例。</em></h1><p>用一组虚构经历，跟着 CareerLens 走一遍“证据 → 画像 → 岗位分析 → 报告”的完整链路。</p><div className="detail-hero-actions"><Link className="site-button site-button-dark" href="/workspace">自己动手体验 <span>↗</span></Link><a className="text-link" href="#case-input">开始阅读案例 ↓</a></div></div><aside><span>CASE FILE 001</span><strong>{demoStory.person}</strong><p>{demoStory.summary}</p><small>{demoStory.badge}</small></aside></section>

      <section className="detail-section" id="case-input"><div className="site-section-heading"><div><span className="site-kicker">INPUT / 01</span><h2>两份输入，<br />从这里开始。</h2></div><p>以下均为虚构内容，不涉及真实个人资料。</p></div><div className="demo-input-grid"><article><span>PERSONAL EVIDENCE</span><h3>个人经历与自述</h3><p>{demoStory.statement}</p><small>来源：自述文本 · 可追溯 Evidence</small></article><article><span>TARGET JOB</span><h3>{demoStory.role}</h3><p>{demoStory.jd}</p><small>输入：岗位描述 · JD REQUIREMENTS</small></article></div></section>

      <section className="detail-section demo-profile-section"><div className="site-section-heading"><div><span className="site-kicker">PROFILE / 02</span><h2>把经历拆成<br />可引用的能力。</h2></div><p>结构化画像不是新编的履历，而是从 Evidence 中提取的条目。</p></div><div className="demo-profile-grid"><div className="demo-evidence-card"><span>原始证据 / EVIDENCE</span><blockquote>“使用 Python、FastAPI 和 LangGraph 构建过多轮 Agent；使用 Qdrant 实现 RAG 检索……”</blockquote><small>虚构演示文本 · 来源可回看</small></div><div className="demo-skills"><div><span>EXTRACTED PROFILE</span><strong>技能画像</strong></div><div>{demoStory.skills.map((skill, index) => <span key={skill}>{String(index + 1).padStart(2, "0")} / {skill}</span>)}</div><small>本案例中的单条自述只提供有限证据，因此匹配为 partial；系统不会把这些技能都当作充分掌握。</small></div></div></section>

      <section className="detail-section demo-match-section"><div className="site-section-heading"><div><span className="site-kicker">JOB FIT / 03</span><h2>岗位要求，<br />逐项对照。</h2></div><p>这里展示的是规则匹配结果，不是录用概率或真实用户准确率。</p></div><div className="demo-match-layout"><div className="demo-match-score"><span>VERIFIABLE MATCH</span><strong>{demoStory.score}</strong><p>基于此虚构示例与当前规则的匹配分数。证据不足时保留“部分匹配”，不直接写成完全胜任。</p></div><div className="demo-match-table"><div className="demo-match-head"><span>岗位要求</span><span>优先级</span><span>状态</span><span>证据</span></div>{demoStory.requirements.map((item) => <div className="demo-match-row" key={item.name}><strong>{item.name}</strong><span>{item.priority}</span><b className={`demo-status ${item.tone}`}>{item.status}</b><span>{item.evidence}</span></div>)}</div></div></section>

      <section className="detail-section demo-output-section"><div className="site-section-heading"><div><span className="site-kicker">DECISION / 04</span><h2>最后交付的，<br />不止一个分数。</h2></div><p>把缺口变成可执行行动，再固化为可下载的报告。</p></div><div className="demo-output-grid"><article><span>LEARNING PATH</span><h3>能力缺口 → 学习动作</h3><div><b>01</b><p><strong>MCP 项目实践</strong><small>做一个可演示工具，并保存项目证据。</small></p></div><div><b>02</b><p><strong>Kubernetes 基础</strong><small>完成部署练习与复盘记录。</small></p></div></article><article><span>VERSIONED REPORT</span><h3>职业报告 v1</h3><p>汇总画像、证据目录、岗位分析、能力缺口与行动建议。每次生成保留新版本，引用的 Evidence 变化后可标记历史版本为陈旧。</p><Link href="/workspace#report">在工作台生成报告 ↗</Link></article><article><span>CAREER COPILOT</span><h3>继续追问依据</h3><p>“为什么是这个方向？”“这项能力的证据在哪里？”对话会检索当前用户的 Evidence，展示引用和检索诊断。</p><Link href="/workspace#copilot">打开 Career Copilot ↗</Link></article></div></section>

      <section className="detail-end"><div><span className="site-kicker">TRY THE REAL FLOW</span><h2>示例看完，<br />现在轮到你操作。</h2><p>工作台预填虚构资料。你可以直接点击导入、分析和生成报告，也可以替换为自己有权使用的内容。</p></div><Link className="site-button site-button-lime" href="/workspace">进入可操作工作台 <span>↗</span></Link></section>
      <SiteFooter />
    </main>
  );
}
