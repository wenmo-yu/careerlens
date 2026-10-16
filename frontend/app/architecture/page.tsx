import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";

export const metadata: Metadata = {
  title: "系统设计 · CareerLens",
  description: "了解 CareerLens 的证据生命周期、三节点 LangGraph 工作流、混合检索与权限边界。",
};

const layers = [
  { index: "01", title: "交互层", label: "NEXT.JS", detail: "导入、画像、岗位分析、报告、对话与评测工作台。", tone: "paper" },
  { index: "02", title: "服务层", label: "FASTAPI + MCP", detail: "HTTP 与 MCP 共用业务服务、校验逻辑与数据权限。", tone: "lime" },
  { index: "03", title: "决策层", label: "DOMAIN + LANGGRAPH", detail: "画像构建、JD 对照、版本化报告与三节点对话。", tone: "paper" },
  { index: "04", title: "数据层", label: "POSTGRESQL + QDRANT", detail: "PostgreSQL 是真相源；Qdrant 是可重建的用户隔离检索索引。", tone: "dark" },
];

export default function ArchitecturePage() {
  return (
    <main className="site-page detail-page architecture-page">
      <SiteHeader active="architecture" />
      <section className="detail-hero architecture-hero"><div><span className="site-kicker">SYSTEM DESIGN / BUILT TO BE INSPECTED</span><h1>一个清晰的系统，<br /><em>胜过一个黑箱。</em></h1><p>CareerLens 把“个人证据”作为整个应用的基座。页面、服务、检索与模型可以各司其职，结论始终能回到原始资料。</p><div className="detail-hero-actions"><a className="site-button site-button-dark" href="https://github.com/wenmo-yu/careerlens/tree/main/docs" target="_blank" rel="noreferrer">阅读技术文档 <span>↗</span></a><Link className="text-link" href="/demo">从案例理解系统 →</Link></div></div><aside className="architecture-hero-aside"><span>DESIGN PRINCIPLE</span><strong>Evidence<br />before<br />Inference.</strong><small>个人数据 → 证据 → 决策</small></aside></section>

      <section className="detail-section architecture-layer-section"><div className="site-section-heading"><div><span className="site-kicker">THE STACK / 01</span><h2>四层结构，<br />职责分明。</h2></div><p>从浏览器到数据库，每一层都有明确边界。</p></div><div className="architecture-layers">{layers.map((layer) => <article className={`architecture-layer ${layer.tone}`} key={layer.index}><span>{layer.index} / {layer.label}</span><h3>{layer.title}</h3><p>{layer.detail}</p><b>↙</b></article>)}</div></section>

      <section className="detail-section architecture-flow-section"><div className="site-section-heading"><div><span className="site-kicker">EVIDENCE LIFECYCLE / 02</span><h2>同一条证据链，<br />支撑不同输出。</h2></div><p>岗位分析和对话共享 Evidence，但走的是不同处理路径。</p></div><div className="architecture-paths"><div className="architecture-source"><span>USER-AUTHORIZED INPUT</span><strong>简历 · 自述 · 授权导出</strong><p>解析与分块后写入 Evidence，保留用户、来源和时间等信息。</p></div><div className="architecture-path-grid"><article><span>PATH A / DECISION</span><h3>Evidence → Profile → JD</h3><p>画像条目携带 Evidence ID。岗位服务提取要求后与画像逐项对照，输出匹配与缺口。</p><b>规则对照 · 非逐项向量检索</b></article><article><span>PATH B / COPILOT</span><h3>Question → Retrieval → Answer</h3><p>对话按用户范围检索原始 Evidence，再约束回答只能引用检索结果中的 ID。</p><b>Dense + Sparse · RRF · Rerank</b></article></div><div className="architecture-output"><span>TRACEABLE OUTPUT</span><strong>版本化职业报告 + 可追问的回答</strong></div></div></section>

      <section className="detail-section architecture-graph-section"><div className="site-section-heading"><div><span className="site-kicker">CAREER COPILOT / 03</span><h2>Agent 工作流，<br />有边界也有回退。</h2></div><p>当前是固定三节点 LangGraph，不是多个自主 Agent。</p></div><div className="graph-nodes"><article><b>01</b><span>UNDERSTAND_INTENT</span><h3>理解问题意图</h3><p>识别证据解释、技能缺口、职业方向等请求。</p></article><i>→</i><article><b>02</b><span>RETRIEVE_EVIDENCE</span><h3>限定用户检索</h3><p>Qdrant 双路融合；异常时在 auto 模式退回本地检索。</p></article><i>→</i><article><b>03</b><span>COMPOSE_ANSWER</span><h3>组织有引用的回答</h3><p>模型输出需符合结构化格式；失败时有确定性回退。</p></article></div></section>

      <section className="detail-section architecture-boundary-section"><div className="site-section-heading"><div><span className="site-kicker">TRUST BOUNDARIES / 04</span><h2>数据可控，<br />输出可核验。</h2></div><p>本地演示与对公网部署是不同的安全场景。</p></div><div className="boundary-grid"><article><span>01 / OWNERSHIP</span><h3>按用户隔离</h3><p>检索按 `user_id` 过滤，HTTP/MCP 令牌限制资源归属与 Scope。</p></article><article><span>02 / CORRECTION</span><h3>人工确认变更</h3><p>长期画像修正先生成草案，再由用户批准写入。</p></article><article><span>03 / PORTABILITY</span><h3>导出与删除</h3><p>提供账号数据导出、单条 Evidence 删除、账号清理和审计记录。</p></article><article><span>04 / HONESTY</span><h3>清楚标注基线</h3><p>默认 Hash Embedding 与 Demo Provider 便于复现；合成评测不代表真实业务准确率。</p></article></div></section>

      <section className="detail-end"><div><span className="site-kicker">FROM ARCHITECTURE TO ACTION</span><h2>看完设计，<br />亲自跑一遍。</h2><p>所有关键流程都可以在本地工作台体验，接口与代码路径在 GitHub 文档中可查。</p></div><Link className="site-button site-button-lime" href="/workspace">打开工作台 <span>↗</span></Link></section>
      <SiteFooter />
    </main>
  );
}
