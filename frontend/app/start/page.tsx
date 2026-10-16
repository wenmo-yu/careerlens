import type { Metadata } from "next";
import Link from "next/link";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";

export const metadata: Metadata = {
  title: "快速开始 · CareerLens",
  description: "使用 Docker Compose 在本地启动 CareerLens，并体验从 Evidence 到职业报告的完整流程。",
};

const endpoints = [
  { name: "Web 工作台", url: "http://localhost:3000/workspace", detail: "完整交互流程" },
  { name: "API 文档", url: "http://localhost:8000/docs", detail: "FastAPI 接口" },
  { name: "MCP 服务", url: "http://localhost:8001/mcp", detail: "Streamable HTTP" },
  { name: "Qdrant", url: "http://localhost:16333/dashboard", detail: "检索索引面板" },
];

export default function StartPage() {
  return (
    <main className="site-page detail-page start-page">
      <SiteHeader active="start" />
      <section className="detail-hero start-hero"><div><span className="site-kicker">GET STARTED / LOCAL FIRST</span><h1>拉起项目，<br /><em>开始探索。</em></h1><p>默认 Demo 模式无需 API Key。通过 Docker Compose 启动 Web、API、MCP、PostgreSQL 与 Qdrant，然后用虚构样例走完整条链路。</p><div className="detail-hero-actions"><a className="site-button site-button-dark" href="#run">查看启动命令 <span>↓</span></a><Link className="text-link" href="/demo">先看案例 →</Link></div></div><aside className="start-hero-aside"><span>LOCAL STACK</span><strong>05<span> SERVICES</span></strong><p>WEB · API · MCP<br />POSTGRESQL · QDRANT</p><small>默认演示模型 / 无需密钥</small></aside></section>

      <section className="detail-section start-run" id="run"><div className="site-section-heading"><div><span className="site-kicker">STEP 01 / BOOT</span><h2>两条命令，<br />启动与验收。</h2></div><p>需要 Docker Desktop 或可用的 Docker Engine + Compose。</p></div><div className="start-command"><div><span>POWERSHELL · REPOSITORY ROOT</span><span>01 / 02</span></div><pre><code>{"docker compose up -d --build\n.\\scripts\\docker-smoke.ps1"}</code></pre><p>Smoke Test 会用一次性虚构账号验证 Evidence → 画像 → JD → 报告 → 对话、Qdrant 检索与 MCP 鉴权；默认在结束时清理该测试账号。</p></div></section>

      <section className="detail-section start-endpoints"><div className="site-section-heading"><div><span className="site-kicker">STEP 02 / EXPLORE</span><h2>服务已启动，<br />从这里进入。</h2></div><p>地址均为本机默认端口；无需公网 IP。</p></div><div className="endpoint-grid">{endpoints.map((endpoint) => <a href={endpoint.url} key={endpoint.name} target="_blank" rel="noreferrer"><span>{endpoint.detail}</span><h3>{endpoint.name}</h3><p>{endpoint.url}</p><b>↗</b></a>)}</div></section>

      <section className="detail-section start-walkthrough"><div className="site-section-heading"><div><span className="site-kicker">STEP 03 / WORKFLOW</span><h2>跑通一条<br />完整业务链。</h2></div><p>工作台预填的个人经历与 JD 都是虚构内容。</p></div><div className="walkthrough-list"><Link href="/workspace#profile"><b>01</b><strong>导入经历，生成画像</strong><span>查看 Evidence 引用与置信度</span><i>↗</i></Link><Link href="/workspace#matching"><b>02</b><strong>分析目标岗位</strong><span>区分部分匹配、缺口与学习路径</span><i>↗</i></Link><Link href="/workspace#report"><b>03</b><strong>生成职业报告</strong><span>保留版本并下载 Markdown</span><i>↗</i></Link><Link href="/workspace#copilot"><b>04</b><strong>追问结论</strong><span>展开原始证据与检索诊断</span><i>↗</i></Link></div></section>

      <section className="detail-section start-modes"><div className="site-section-heading"><div><span className="site-kicker">CONFIGURATION / OPTIONAL</span><h2>默认可运行，<br />模型可替换。</h2></div><p>检索模型与生成模型分别配置，不必绑定同一提供方。</p></div><div className="mode-grid"><article><span>01 / REPRODUCIBLE</span><h3>Demo 默认模式</h3><p>确定性文本与 Hash Embedding，适合无密钥体验完整功能与回归测试。</p><b>AI_PROVIDER=demo</b></article><article><span>02 / HOSTED</span><h3>托管模型 API</h3><p>通过 OpenAI-compatible 接口配置 DeepSeek 或其他兼容服务；需自行提供有效密钥与模型 ID。</p><b>AI_PROVIDER=deepseek</b></article><article><span>03 / LOCAL</span><h3>本地 Qwen 路线</h3><p>保留本地兼容推理接口与可选 Embedding/Reranker；效果与资源需求取决于目标机器。</p><b>AI_PROVIDER=local</b></article></div><p className="start-doc-link">更完整的环境变量、模型接入与生产鉴权说明见 <a href="https://github.com/wenmo-yu/careerlens#快速启动" target="_blank" rel="noreferrer">GitHub README ↗</a>。</p></section>

      <section className="detail-end"><div><span className="site-kicker">READY WHEN YOU ARE</span><h2>系统已经就位。<br />从第一条证据开始。</h2><p>请只导入自己有权使用的资料。公开展示时建议使用虚构或脱敏数据。</p></div><Link className="site-button site-button-lime" href="/workspace">进入工作台 <span>↗</span></Link></section>
      <SiteFooter />
    </main>
  );
}
