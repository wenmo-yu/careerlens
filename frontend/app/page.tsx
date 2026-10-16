import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { demoStory } from "@/lib/demo-story";

const journey = [
  { number: "01", title: "沉淀个人证据", copy: "简历、自述和授权导出的内容先成为带来源的 Evidence。", href: "/workspace#profile", tag: "INGEST" },
  { number: "02", title: "构建动态画像", copy: "从证据抽取能力条目，并让每个条目保留引用与置信度。", href: "/workspace#profile", tag: "PROFILE" },
  { number: "03", title: "逐项分析岗位", copy: "拆解 JD 要求，对照画像，明确已有能力和真实缺口。", href: "/workspace#matching", tag: "MATCH" },
  { number: "04", title: "交付可追溯结果", copy: "形成版本化报告，并通过 Copilot 继续追问证据。", href: "/workspace#report", tag: "DECIDE" },
];

export default function Home() {
  return (
    <main className="site-page landing-page">
      <SiteHeader active="home" />

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <span className="site-kicker"><i /> EVIDENCE-GROUNDED CAREER INTELLIGENCE</span>
          <h1>职业选择，<br /><em>不靠猜。</em></h1>
          <p>把零散经历整理成可验证的职业画像，让每一次岗位匹配、能力判断和下一步建议，都有证据可循。</p>
          <div className="landing-actions">
            <Link className="site-button site-button-dark" href="/workspace">进入工作台 <span>↗</span></Link>
            <Link className="site-button site-button-outline" href="/demo">先看完整案例 <span>→</span></Link>
          </div>
          <div className="landing-hero-foot"><span>01 / PERSONAL DATA</span><span>02 / EVIDENCE</span><span>03 / DECISION</span></div>
        </div>
        <div className="landing-visual" aria-label="虚构案例界面预览">
          <div className="visual-top"><span><b /> CAREERLENS / DECISION DESK</span><span>DEMO VIEW</span></div>
          <div className="visual-profile"><div className="visual-avatar">CL</div><div><small>CAREER PROFILE</small><strong>{demoStory.person}的职业画像</strong><span>AI 应用开发方向 · 虚构案例</span></div><span className="visual-arrow">↗</span></div>
          <div className="visual-main">
            <div className="visual-score"><small>VERIFIABLE MATCH</small><strong>{demoStory.score}</strong><span>对目标岗位的规则匹配结果</span></div>
            <div className="visual-requirements"><small>REQUIREMENT STATUS</small><div><span>Python / FastAPI</span><b className="visual-partial">PARTIAL</b></div><div><span>LangGraph / RAG</span><b className="visual-partial">PARTIAL</b></div><div><span>MCP / Kubernetes</span><b className="visual-gap">GAP</b></div></div>
          </div>
          <div className="visual-footer"><span>↳ 每个能力结论都有 Evidence ID</span><span>DEMO 01 / 2026</span></div>
          <div className="landing-sticker">证据先于结论 <span>✳</span></div>
        </div>
      </section>

      <div className="landing-rail" aria-label="架构摘要"><span>LANGGRAPH / INTENT ROUTING</span><span>QDRANT / HYBRID SEARCH</span><span>POSTGRESQL / SOURCE OF TRUTH</span><span>MCP / OPEN INTEGRATION</span></div>

      <section className="landing-section landing-problem">
        <div className="site-section-intro"><span className="site-kicker">WHY CAREERLENS / 01</span><h2>建议可以流畅，<br />依据必须清楚。</h2><p>不是把简历扔给模型后得到一段漂亮的话。CareerLens 先建立证据，再让画像、岗位判断和报告沿着同一条证据链产生。</p></div>
        <div className="landing-principles">
          <article><span className="principle-icon">⌁</span><small>01 / TRACEABLE</small><h3>结论回到来源</h3><p>画像条目绑定 Evidence ID；岗位匹配引用画像中的证据，无证据的能力显示为缺口。</p><Link href="/architecture">了解证据链 ↗</Link></article>
          <article><span className="principle-icon">⊕</span><small>02 / CORRECTABLE</small><h3>长期记忆可纠正</h3><p>用户修改职业偏好时，系统先生成变更草案，确认后才写入长期画像。</p><Link href="/workspace#profile">查看画像模块 ↗</Link></article>
          <article><span className="principle-icon">↗</span><small>03 / ACTIONABLE</small><h3>缺口连接行动</h3><p>识别岗位要求与现有能力的差距，形成学习路径和版本化职业报告。</p><Link href="/demo">查看虚构案例 ↗</Link></article>
        </div>
      </section>

      <section className="landing-section landing-journey">
        <div className="site-section-heading"><div><span className="site-kicker">HOW IT WORKS / 02</span><h2>从经历到决定，<br />四步走完。</h2></div><Link className="text-link" href="/workspace">打开可操作工作台 ↗</Link></div>
        <div className="journey-grid">{journey.map((step) => <Link href={step.href} className="journey-card" key={step.number}><div><span>{step.number}</span><small>{step.tag}</small></div><h3>{step.title}</h3><p>{step.copy}</p><b>↗</b></Link>)}</div>
      </section>

      <section className="landing-case">
        <div className="landing-case-copy"><span className="site-kicker">A FICTIONAL WALKTHROUGH / 03</span><h2>一个具体的人，<br />一份具体的 JD。</h2><p>{demoStory.summary}</p><p>看看一份虚构经历如何被拆成画像与岗位要求，哪些能力有证据，哪些仍需补足。</p><Link className="site-button site-button-lime" href="/demo">打开案例体验 <span>↗</span></Link></div>
        <div className="case-ticket"><div><span>CASE FILE / 001</span><span>FICTIONAL DATA</span></div><strong>{demoStory.person}<small>→ {demoStory.role}</small></strong><div className="case-ticket-bottom"><span>画像条目<br /><b>12 项</b></span><span>待补能力<br /><b>02 项</b></span><span>规则匹配<br /><b>{demoStory.score}</b></span></div></div>
      </section>

      <section className="landing-section landing-tech"><div><span className="site-kicker">UNDER THE HOOD / 04</span><h2>可读、可换、可验证<br />的技术骨架。</h2></div><div className="landing-tech-right"><p>Next.js 工作台与 FastAPI 业务接口共享同一条证据链。PostgreSQL 保存业务数据，Qdrant 承担派生检索索引；LangGraph 对话和 MCP 工具复用业务服务。默认 Demo 模式可无密钥体验完整流程。</p><div className="tech-pills"><span>FastAPI</span><span>LangGraph</span><span>Qdrant</span><span>PostgreSQL</span><span>MCP</span><span>Next.js</span></div><Link className="text-link" href="/architecture">查看系统设计与边界 ↗</Link></div></section>

      <section className="landing-final"><span className="site-kicker">START EXPLORING</span><h2>下一步，<br />从证据开始。</h2><div><Link className="site-button site-button-dark" href="/workspace">进入工作台 <span>↗</span></Link><Link className="site-button site-button-outline" href="/start">查看启动方法 <span>→</span></Link></div></section>
      <SiteFooter />
    </main>
  );
}
