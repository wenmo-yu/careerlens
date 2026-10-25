"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useState } from "react";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import { BrowserCaptureDraft, parseBrowserCaptureDraft } from "@/lib/browser-capture";
import {
  analyzeJob,
  CareerReport,
  ChatResult,
  importEvidence,
  importBilibiliExport,
  importBrowserCapture,
  importMedia,
  importWeiboExport,
  JobAnalysis,
  Profile,
  ProfileProposal,
  EvaluationRun,
  ObservabilitySummary,
  AuditEvent,
  decideProfileUpdate,
  clearAccessToken,
  deleteAccount,
  deleteEvidence,
  downloadCareerReport,
  exportUserData,
  generateCareerReport,
  getAuditLog,
  getProfile,
  getEvaluationRuns,
  getObservabilitySummary,
  proposeProfileUpdate,
  runBenchmarkRegression,
  registerOwner,
  setAccessToken,
  rebuildProfile,
  sendChat,
} from "@/lib/api";

const demoEvidence = `我希望寻找 AI Agent 或 LLM 应用开发岗位。使用 Python、FastAPI 和 LangGraph 构建过多轮 Agent；使用 Qdrant 实现 RAG 检索，并通过 Docker 完成服务部署。熟悉 PostgreSQL、React 和 TypeScript。`;
const demoJd = `AI Agent 开发实习生：要求熟悉 Python、FastAPI、LangGraph、RAG、PostgreSQL；了解 Docker。具备 Kubernetes 或 MCP 项目经验者优先。`;

type Notice = { kind: "ok" | "error"; text: string } | null;

export default function Home() {
  const [userId, setUserId] = useState("demo-user");
  const [evidenceText, setEvidenceText] = useState(demoEvidence);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [jobTitle, setJobTitle] = useState("AI Agent 开发实习生");
  const [jdText, setJdText] = useState(demoJd);
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [report, setReport] = useState<CareerReport | null>(null);
  const [chatInput, setChatInput] = useState("为什么认为我适合 Agent 开发？");
  const [chat, setChat] = useState<ChatResult | null>(null);
  const [memoryInput, setMemoryInput] = useState("我不再考虑纯 CV 岗位，更希望做 AI Agent 应用开发。");
  const [proposal, setProposal] = useState<ProfileProposal | null>(null);
  const [evaluation, setEvaluation] = useState<EvaluationRun | null>(null);
  const [telemetry, setTelemetry] = useState<ObservabilitySummary | null>(null);
  const [registrationSecret, setRegistrationSecret] = useState("");
  const [issuedToken, setIssuedToken] = useState("");
  const [deleteEvidenceId, setDeleteEvidenceId] = useState("");
  const [accountDeletionConfirm, setAccountDeletionConfirm] = useState("");
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [browserDraft, setBrowserDraft] = useState<{ capture: BrowserCaptureDraft; userId: string } | null>(null);
  const [selectedCaptureItems, setSelectedCaptureItems] = useState<number[]>([]);

  const skills = useMemo(
    () => profile?.items.filter((item) => item.category === "skill") ?? [],
    [profile],
  );

  useEffect(() => {
    void Promise.all([getEvaluationRuns(), getObservabilitySummary()])
      .then(([runs, summary]) => {
        setEvaluation(runs[0] ?? null);
        setTelemetry(summary);
      })
      .catch(() => undefined);
  }, []);

  async function run(label: string, action: () => Promise<void>) {
    setBusy(label);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "操作失败" });
    } finally {
      setBusy(null);
    }
  }

  function handleBuildProfile(event: FormEvent) {
    event.preventDefault();
    void run("profile", async () => {
      await importEvidence(userId, evidenceText);
      const result = await rebuildProfile(userId);
      setProfile(result);
      setAnalysis(null);
      setReport(null);
      setTelemetry(await getObservabilitySummary());
      setNotice({ kind: "ok", text: `画像已更新：${result.count} 个可追溯条目` });
    });
  }

  function handleJob(event: FormEvent) {
    event.preventDefault();
    void run("job", async () => {
      const result = await analyzeJob(userId, jobTitle, jdText, weeklyHours);
      setAnalysis(result);
      setReport(null);
      setNotice({ kind: "ok", text: "JD 已完成逐项证据匹配" });
    });
  }

  function handleChat(event: FormEvent) {
    event.preventDefault();
    void run("chat", async () => {
      const result = await sendChat(userId, chatInput, chat?.thread_id, analysis?.id);
      setChat(result);
      setTelemetry(await getObservabilitySummary());
    });
  }

  function handleReport() {
    if (!analysis) return;
    void run("report", async () => {
      const result = await generateCareerReport(userId, analysis.id);
      setReport(result);
      setNotice({ kind: "ok", text: `职业报告 v${result.version} 已生成并保存。` });
    });
  }

  function handleReportDownload() {
    if (!report) return;
    void run("report-download", async () => {
      const markdown = await downloadCareerReport(report.id);
      const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `careerlens-report-v${report.version}.md`;
      anchor.click();
      URL.revokeObjectURL(url);
      setNotice({ kind: "ok", text: "Markdown 职业报告已下载。" });
    });
  }

  function handleProposal(event: FormEvent) {
    event.preventDefault();
    void run("proposal", async () => {
      const result = await proposeProfileUpdate(userId, memoryInput);
      setProposal(result);
      setNotice({ kind: "ok", text: "已生成画像变更草案，确认前不会写入。" });
    });
  }

  function handleDecision(approve: boolean) {
    if (!proposal) return;
    void run("decision", async () => {
      const result = await decideProfileUpdate(proposal.id, approve);
      setProposal(result);
      if (approve) setProfile(await getProfile(userId));
      setNotice({ kind: "ok", text: approve ? "已确认并写入长期画像。" : "已拒绝，本次没有修改画像。" });
    });
  }

  function handleBilibili(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run("bilibili", async () => {
      const result = await importBilibiliExport(userId, file);
      setNotice({
        kind: "ok",
        text: `B站导出已导入 ${result.created_count} 条，跳过 ${result.duplicate_count} 条重复内容。`,
      });
    });
    event.target.value = "";
  }

  function handleWeibo(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run("weibo", async () => {
      const result = await importWeiboExport(userId, file);
      setNotice({
        kind: "ok",
        text: `微博导出已导入 ${result.created_count} 条，跳过 ${result.duplicate_count} 条重复内容。`,
      });
    });
    event.target.value = "";
  }

  function handleBrowserCapture(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setBrowserDraft(null);
    setSelectedCaptureItems([]);
    void run("browser-preview", async () => {
      if (!userId.trim()) throw new Error("请先填写用户标识。");
      if (file.size > 2_000_000) throw new Error("采集文件不能超过 2 MB。");
      const capture = parseBrowserCaptureDraft(await file.text());
      setBrowserDraft({ capture, userId: userId.trim() });
      setSelectedCaptureItems(capture.items.map((_, index) => index));
      setNotice({ kind: "ok", text: `已读取 ${capture.items.length} 条采集内容。请逐条核对，确认后才会入库。` });
    });
    event.target.value = "";
  }

  function handleConfirmBrowserCapture() {
    if (!browserDraft || !selectedCaptureItems.length) return;
    void run("browser-capture", async () => {
      const capture = {
        ...browserDraft.capture,
        items: browserDraft.capture.items.filter((_, index) => selectedCaptureItems.includes(index)),
      };
      const file = new File([JSON.stringify(capture)], "careerlens-reviewed-capture.json", { type: "application/json" });
      const result = await importBrowserCapture(browserDraft.userId, file);
      setBrowserDraft(null);
      setSelectedCaptureItems([]);
      setNotice({
        kind: "ok",
        text: `已为 ${browserDraft.userId} 导入 ${result.created_count} 条，跳过 ${result.skipped_count} 条无效项与 ${result.duplicate_count} 条重复项。互动记录仅作兴趣线索。`,
      });
    });
  }

  function handleMedia(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run("media", async () => {
      const result = await importMedia(userId, file);
      setNotice({ kind: "ok", text: `媒体解析完成，生成 ${result.count} 条 Evidence。` });
    });
    event.target.value = "";
  }

  function handleEvaluation() {
    void run("evaluation", async () => {
      const [result, summary] = await Promise.all([
        runBenchmarkRegression(),
        getObservabilitySummary(),
      ]);
      setEvaluation(result.run);
      setTelemetry(summary);
      setNotice({
        kind: result.status === "passed" ? "ok" : "error",
        text: result.status === "passed"
          ? `质量门禁通过：${result.run.dataset_name}`
          : `质量门禁失败：${result.failures.length} 项指标低于基线`,
      });
    });
  }

  function handleRegisterOwner() {
    void run("register", async () => {
      const result = await registerOwner(userId, registrationSecret);
      setAccessToken(result.token);
      setIssuedToken(result.token);
      setNotice({ kind: "ok", text: "Owner Token 已创建并仅保存在当前浏览器会话中。" });
    });
  }

  function handleExport() {
    void run("export", async () => {
      const data = await exportUserData(userId);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `careerlens-${userId}-export.json`;
      anchor.click();
      URL.revokeObjectURL(url);
      setAuditEvents(await getAuditLog(userId));
      setNotice({ kind: "ok", text: "用户数据已导出，导出动作已写入审计日志。" });
    });
  }

  function handleLoadAudit() {
    void run("audit", async () => setAuditEvents(await getAuditLog(userId)));
  }

  function handleDeleteEvidence() {
    if (!deleteEvidenceId || !window.confirm("确认删除这条 Evidence？相关画像引用也会同步清理。")) return;
    void run("delete", async () => {
      const result = await deleteEvidence(deleteEvidenceId);
      setDeleteEvidenceId("");
      setAuditEvents(await getAuditLog(userId));
      setNotice({ kind: "ok", text: `Evidence 已删除，并清理 ${result.removed_profile_items} 个失去证据的画像条目。` });
    });
  }

  function handleDeleteAccount() {
    if (accountDeletionConfirm !== userId) return;
    if (!window.confirm("这会永久删除账号数据、访问令牌、向量和对话状态。确认继续？")) return;
    void run("delete-account", async () => {
      const result = await deleteAccount(userId);
      clearAccessToken();
      setIssuedToken("");
      setAccountDeletionConfirm("");
      setProfile(null);
      setAnalysis(null);
      setReport(null);
      setChat(null);
      setProposal(null);
      setAuditEvents([]);
      setNotice({ kind: "ok", text: `账号数据已删除。匿名回执：${result.receipt_id}` });
    });
  }

  return (
    <main className="site-page workspace-page">
      <SiteHeader active="workspace" />
      <nav className="workspace-subnav" aria-label="工作台模块">
        <span>WORKSPACE / 真实业务接口 · 虚构预填内容</span>
        <div><a href="#profile">职业画像</a><a href="#matching">岗位匹配</a><a href="#report">职业报告</a><a href="#copilot">Career Copilot</a><a href="#quality">质量评测</a><a href="#privacy">数据控制</a></div>
      </nav>

      <section className="hero" id="top">
        <div>
          <p className="eyebrow">INTERACTIVE WORKSPACE / PERSONAL DATA → EVIDENCE → DECISION</p>
          <h1>让每一个职业判断，<br /><em>都有证据。</em></h1>
          <p className="hero-copy">导入你的经历，构建长期职业画像，再与真实岗位逐项比对。下方已预填虚构 Demo 内容；操作会调用真实业务接口，不会替你编造已有能力。</p>
        </div>
        <div className="hero-metric" aria-label="系统原则">
          <span>可信结论策略</span>
          <strong>Evidence</strong>
          <p>Supported / Partial / Gap</p>
        </div>
      </section>

      {notice && <div className={`notice ${notice.kind}`} role="status">{notice.text}</div>}

      <section className="workspace" id="profile">
        <div className="section-heading">
          <div><span>01</span><h2>构建职业画像</h2></div>
          <p>先从简历、自述或导出内容建立 Evidence。</p>
        </div>
        <div className="two-column">
          <form className="panel input-panel" onSubmit={handleBuildProfile}>
            <label>用户标识<input value={userId} onChange={(event) => setUserId(event.target.value)} required /></label>
            <label>个人经历与自述<textarea rows={9} value={evidenceText} onChange={(event) => setEvidenceText(event.target.value)} required /></label>
            <button disabled={busy !== null}>{busy === "profile" ? "正在构建…" : "导入并生成画像"}<span>↗</span></button>
          </form>
          <div className="panel profile-panel">
            <div className="panel-title"><h3>Structured Profile</h3><span>{profile ? `${profile.count} ITEMS` : "WAITING"}</span></div>
            {skills.length ? <div className="skill-list">{skills.map((skill) => (
              <article key={skill.id}>
                <div><strong>{skill.name}</strong><small>{skill.evidence_ids.length} 条证据</small></div>
                <div className="bar"><i style={{ width: `${skill.confidence * 100}%` }} /></div>
                <b>{Math.round(skill.confidence * 100)}%</b>
              </article>
            ))}</div> : <Empty text="导入经历后，这里会显示带内部可信程度和 Evidence ID 的技能画像。" />}
            {skills.length > 0 && <p className="profile-score-note">百分比是抽取器的启发式可信程度，用于排序和展示；不是“具备该能力”的统计概率。请结合 Evidence 原文核对。</p>}
          </div>
        </div>
        <div className="connector-strip">
          <div><span>AUTHORIZED CONNECTORS</span><h3>从个人数据源继续补充证据</h3><p>可使用 browser-helper 在已登录页面本地采集并核对后导入；不读取或上传 Cookie。互动记录仅作兴趣线索。</p></div>
          <label className="upload-card"><b>Bilibili Export</b><small>JSON · 视频标题 / 简介 / 字幕 / 标签</small><input type="file" accept="application/json,.json" onChange={handleBilibili} disabled={busy !== null} /><i>{busy === "bilibili" ? "导入中…" : "选择导出文件 ↗"}</i></label>
          <label className="upload-card"><b>Weibo Export</b><small>JSON / CSV · 正文 / 话题 / 转发 / 时间</small><input type="file" accept="application/json,text/csv,.json,.csv" onChange={handleWeibo} disabled={busy !== null} /><i>{busy === "weibo" ? "导入中…" : "选择导出文件 ↗"}</i></label>
          <label className="upload-card"><b>Browser Capture</b><small>B站 / 微博 / 抖音 · 发布 / 点赞 / 收藏 / 关注 · JSON</small><input type="file" accept="application/json,.json" onChange={handleBrowserCapture} disabled={busy !== null} /><i>{busy === "browser-preview" ? "读取中…" : "选择采集文件并核对 ↗"}</i></label>
          <label className="upload-card"><b>OCR / ASR</b><small>PNG / JPG / MP3 / WAV / MP4 / WEBM</small><input type="file" accept="image/*,audio/*,video/*" onChange={handleMedia} disabled={busy !== null} /><i>{busy === "media" ? "解析中…" : "选择媒体文件 ↗"}</i></label>
        </div>
        {browserDraft && <div className="capture-review" aria-label="页面采集审核">
          <div className="capture-review-head">
            <div><span>REVIEW BEFORE IMPORT</span><h3>核对页面采集内容</h3><p>目标用户：{browserDraft.userId} · {browserDraft.capture.platform} / {browserDraft.capture.kind} · 已选 {selectedCaptureItems.length} / {browserDraft.capture.items.length} 条</p></div>
            <div className="capture-review-actions"><button type="button" className="secondary" onClick={() => setSelectedCaptureItems(browserDraft.capture.items.map((_, index) => index))}>全选</button><button type="button" className="secondary" onClick={() => setSelectedCaptureItems([])}>全不选</button></div>
          </div>
          <p className="capture-review-note">只导入勾选的条目。请核对内容确实来自自己的页面，且没有不希望保存的文字。发布内容按用户自报处理；点赞、收藏与关注仅用于兴趣线索。</p>
          <div className="capture-review-list">{browserDraft.capture.items.map((item, index) => <label key={`${item.url}-${index}`} className="capture-review-item">
            <input type="checkbox" checked={selectedCaptureItems.includes(index)} onChange={(event) => setSelectedCaptureItems((current) => event.target.checked ? [...current, index] : current.filter((value) => value !== index))} />
            <span><strong>{item.title || `条目 ${index + 1}`}</strong><small>{item.text.slice(0, 240)}</small><em>{item.url}</em></span>
          </label>)}</div>
          <div className="capture-review-actions"><button type="button" onClick={handleConfirmBrowserCapture} disabled={busy !== null || selectedCaptureItems.length === 0}>{busy === "browser-capture" ? "导入中…" : `确认导入 ${selectedCaptureItems.length} 条`}</button><button type="button" className="secondary" disabled={busy !== null} onClick={() => { setBrowserDraft(null); setSelectedCaptureItems([]); setNotice({ kind: "ok", text: "已取消，本次采集内容没有写入。" }); }}>取消</button></div>
        </div>}
        <div className="memory-panel">
          <div><span>HUMAN IN THE LOOP</span><h3>长期画像纠正</h3><p>模型只生成变更草案；只有你确认后，系统才把它作为新证据写入画像。</p></div>
          <form onSubmit={handleProposal}><textarea rows={3} value={memoryInput} onChange={(event) => setMemoryInput(event.target.value)} required /><button disabled={busy !== null}>{busy === "proposal" ? "解析中…" : "生成变更草案"}</button></form>
          {proposal && <div className={`proposal ${proposal.status}`}><b>{proposal.status === "pending" ? "等待确认" : proposal.status === "approved" ? "已写入" : "已拒绝"}</b>{proposal.changes.map((change, index) => <p key={`${change.name}-${index}`}><code>{change.action}</code> {change.category} · {change.name}</p>)}{proposal.status === "pending" && <div><button type="button" onClick={() => handleDecision(true)} disabled={busy !== null}>确认写入</button><button type="button" className="secondary" onClick={() => handleDecision(false)} disabled={busy !== null}>拒绝</button></div>}</div>}
        </div>
      </section>

      <section className="workspace dark-section" id="matching">
        <div className="section-heading light">
          <div><span>02</span><h2>岗位逐项匹配</h2></div>
          <p>逐项识别岗位要求，与带证据引用的职业画像对照。</p>
        </div>
        <form className="jd-form" onSubmit={handleJob}>
          <div className="jd-fields">
            <label>岗位名称<input value={jobTitle} onChange={(event) => setJobTitle(event.target.value)} required /></label>
            <label className="hours">每周学习小时<input type="number" min="1" max="80" value={weeklyHours} onChange={(event) => setWeeklyHours(Number(event.target.value))} /></label>
            <label className="wide">岗位描述<textarea rows={6} value={jdText} onChange={(event) => setJdText(event.target.value)} required /></label>
            <button disabled={busy !== null}>{busy === "job" ? "分析中…" : "分析匹配度"}</button>
          </div>
          <div className="score-card">
            <span>RULE-BASED MATCH</span>
            <strong>{analysis ? analysis.score : "—"}<small>{analysis && "%"}</small></strong>
            <p>{analysis?.report.recommendation ?? "完成画像后提交 JD"}</p>
            {analysis && <small className="score-disclaimer">规则匹配分，不是录用概率</small>}
          </div>
        </form>
        {analysis && <div className="match-grid">
          <div className="match-table">
            <div className="table-row head"><span>岗位要求</span><span>状态</span><span>证据</span></div>
            {analysis.matches.map((match) => <div className="table-row" key={match.name}>
              <span>{match.name}<small>{match.priority === "preferred" ? "加分项" : "必需"}</small></span>
              <span className={`pill ${match.status}`}>{match.status}</span>
              <span>{match.evidence_ids.length ? `${match.evidence_ids.length} 条` : "暂无"}</span>
            </div>)}
          </div>
          <div className="path-card"><h3>Gap → Learning Path</h3><p className="path-disclaimer">按缺口、现有等级与每周时间排序的规则式计划；实践成果可作为下一轮 Evidence。</p>{analysis.learning_path.length ? analysis.learning_path.map((step) => <article key={step.skill}><b>0{step.stage}</b><div><strong>{step.skill}</strong><p>{step.goal}</p><small>{step.start_week ? `第 ${step.start_week} 周起 · ` : ""}预计 {step.weeks} 周{step.estimated_hours ? ` / ${step.estimated_hours} 小时` : ""}</small></div></article>) : <Empty text="当前没有识别到明确缺口。" />}</div>
        </div>}
      </section>

      <section className="workspace report-section" id="report">
        <div className="section-heading">
          <div><span>03</span><h2>完整职业报告</h2></div>
          <p>将画像、岗位证据、能力缺口和学习路线固化为可追溯版本。</p>
        </div>
        <div className="report-shell">
          <div className="report-intro">
            <span>REPORT BUILDER</span>
            <h3>{report?.title ?? "等待岗位分析"}</h3>
            <p>{report?.content.executive_summary ?? "先完成目标 JD 分析，再生成八个固定章节的职业报告。模型只负责在证据边界内润色；不可用时自动生成确定性版本。"}</p>
            <div className="report-actions">
              <button type="button" onClick={handleReport} disabled={busy !== null || !analysis}>{busy === "report" ? "生成中…" : report ? "生成新版本" : "生成职业报告"}</button>
              <button type="button" className="secondary" onClick={handleReportDownload} disabled={busy !== null || !report}>{busy === "report-download" ? "导出中…" : "下载 Markdown"}</button>
            </div>
            {report && <div className="report-meta"><span>VERSION {report.version}</span><span>{report.model_diagnostics.provider} / {report.model_diagnostics.model}</span><span>{report.content.referenced_evidence_ids.length} EVIDENCE</span>{report.is_stale && <span className="stale">STALE</span>}</div>}
          </div>
          <div className="report-preview">
            {report ? <>
              <article><b>01</b><div><span>个人职业画像</span><strong>{report.content.core_capabilities.slice(0, 4).map((item) => item.name).join(" · ") || "等待画像"}</strong></div></article>
              <article><b>02</b><div><span>推荐就业方向</span><strong>{report.content.career_direction.primary_role} · {report.content.career_direction.match_score}%</strong></div></article>
              <article><b>03</b><div><span>能力缺口</span><strong>{report.content.skill_gaps.map((item) => item.name).join(" · ") || "当前 JD 无明确缺口"}</strong></div></article>
              <article><b>04</b><div><span>下一步行动</span><strong>{report.content.action_plan[0]}</strong></div></article>
              <blockquote>{report.content.interview_pitch}</blockquote>
            </> : <Empty text="报告会保留版本号、Provider 诊断与 Evidence 引用。" />}
          </div>
        </div>
      </section>

      <section className="workspace copilot" id="copilot">
        <div className="section-heading"><div><span>04</span><h2>Career Copilot</h2></div><p>追问结论，直接查看引用证据。</p></div>
        <div className="chat-shell">
          <div className="chat-context"><span>当前用户</span><strong>{userId}</strong><p>{skills.slice(0, 4).map((item) => item.name).join(" · ") || "等待画像"}</p></div>
          <div className="conversation">
            {chat ? <>
              <div className="bubble user">{chatInput}</div>
              <div className="bubble agent"><small>CAREERLENS · {chat.intent}</small><p>{chat.answer}</p><div className="retrieval-badges"><span>{chat.model.provider} / {chat.model.model}</span><span>{chat.retrieval.backend}</span><span>{chat.retrieval.fusion}</span><span>{chat.retrieval.reranker}</span>{chat.model.fallback && <span className="fallback">model fallback</span>}{chat.retrieval.fallback && <span className="fallback">retrieval fallback</span>}</div></div>
              {chat.evidence.length > 0 && <div className="evidence-stack"><b>引用证据 · {chat.retrieval.backend === "qdrant" ? "RRF + Rerank" : "Local Hybrid"}</b>{chat.evidence.map((item) => <details key={item.evidence_id}><summary>{item.source_name}<span>{Math.round(item.rerank_score * 100)}%</span></summary><p>{item.content}</p><code>{item.evidence_id}</code></details>)}</div>}
            </> : <Empty text="试着问：为什么认为我适合 Agent 开发？" />}
            <form className="chat-input" onSubmit={handleChat}><input value={chatInput} onChange={(event) => setChatInput(event.target.value)} placeholder="询问你的职业画像…" required /><button aria-label="发送" disabled={busy !== null}>↑</button></form>
          </div>
        </div>
      </section>

      <section className="workspace quality-section" id="quality">
        <div className="section-heading">
          <div><span>05</span><h2>质量评测与观测</h2></div>
          <p>使用人工标注基准衡量抽取、检索和匹配，不让模型自己给自己打分。</p>
        </div>
        <div className="quality-grid">
          <div className="quality-main">
            <div className="quality-title"><div><span>CONTINUOUS REGRESSION GATE</span><h3>{evaluation?.dataset_name ?? "等待首次评测"}</h3></div><button type="button" onClick={handleEvaluation} disabled={busy !== null}>{busy === "evaluation" ? "评测中…" : "运行质量门禁"}</button></div>
            <div className="metric-grid">
              <Metric label="Profile Extraction F1" value={evaluation?.profile_extraction_f1} />
              <Metric label={`Evidence Recall@${evaluation?.metrics.recall_k ?? "K"}`} value={evaluation?.evidence_recall_at_k} />
              <Metric label="Supported Claim Rate" value={evaluation?.supported_claim_rate} />
              <Metric label="Requirement Matching F1" value={evaluation?.requirement_matching_f1} />
            </div>
            {evaluation?.details.regression && <div className={`gate-strip ${evaluation.details.regression.status}`}><strong>{evaluation.details.regression.status === "passed" ? "PASS" : "FAIL"}</strong><span>{evaluation.details.regression.status === "passed" ? "全部核心指标达到冻结基线" : `${evaluation.details.regression.failures.length} 项指标未达到最低阈值`}</span></div>}
            <p className="sample-note">{evaluation ? `${evaluation.metrics.case_count} 个场景 · ${evaluation.metrics.query_count} 个检索问题 · ${evaluation.metrics.claim_count} 个画像结论` : "开发基准用于持续回归；真实业务指标需另行扩充脱敏人工标注集后再引用。"} {evaluation?.dataset_name.includes("dev-benchmark") && "当前为合成开发基准，不代表真实用户准确率。"}</p>
          </div>
          <aside className="telemetry-card">
            <span>MODEL OBSERVABILITY</span><h3>调用健康度</h3>
            <dl><div><dt>请求数</dt><dd>{telemetry?.request_count ?? 0}</dd></div><div><dt>成功率</dt><dd>{Math.round((telemetry?.success_rate ?? 0) * 100)}%</dd></div><div><dt>平均延迟</dt><dd>{telemetry?.average_latency_ms ?? 0}<small> ms</small></dd></div><div><dt>P95 延迟</dt><dd>{telemetry?.p95_latency_ms ?? 0}<small> ms</small></dd></div><div><dt>Token</dt><dd>{(telemetry?.prompt_tokens ?? 0) + (telemetry?.completion_tokens ?? 0)}</dd></div><div><dt>估算成本</dt><dd>${(telemetry?.estimated_cost_usd ?? 0).toFixed(4)}</dd></div></dl>
            <p>成本由环境变量中的每百万 Token 单价估算；OTLP Span 只记录模型、耗时、Token 和状态，不记录 Prompt、API Key 或 Evidence 原文。</p>
          </aside>
        </div>
      </section>

      <section className="workspace privacy-section" id="privacy">
        <div className="section-heading light">
          <div><span>06</span><h2>隐私与数据控制</h2></div>
          <p>Token 只返回一次；导出和删除会留下不包含原文的审计记录。</p>
        </div>
        <div className="privacy-grid">
          <article><span>01 / ACCESS</span><h3>Owner Token</h3><p>生产环境开启强制鉴权后，用 Registration Secret 初始化第一个 Owner Token。</p><input type="password" value={registrationSecret} onChange={(event) => setRegistrationSecret(event.target.value)} placeholder="Registration Secret（本地可留空）" /><button type="button" onClick={handleRegisterOwner} disabled={busy !== null}>{busy === "register" ? "创建中…" : "创建并启用 Token"}</button>{issuedToken && <code className="token-output">{issuedToken}</code>}</article>
          <article><span>02 / PORTABILITY</span><h3>导出我的数据</h3><p>导出 Evidence、画像、JD 分析、职业报告、画像纠正和审计日志，不包含 Token 哈希。</p><button type="button" onClick={handleExport} disabled={busy !== null}>{busy === "export" ? "导出中…" : "下载 JSON 数据副本"}</button></article>
          <article><span>03 / ERASURE</span><h3>删除数据</h3><p>可删除单条 Evidence；永久删除账号会同时清理数据库、向量、对话状态和全部 Token。</p><input value={deleteEvidenceId} onChange={(event) => setDeleteEvidenceId(event.target.value)} placeholder="Evidence ID" /><button type="button" className="danger" onClick={handleDeleteEvidence} disabled={busy !== null || !deleteEvidenceId}>{busy === "delete" ? "删除中…" : "删除 Evidence"}</button><div className="erasure-divider" /><input value={accountDeletionConfirm} onChange={(event) => setAccountDeletionConfirm(event.target.value)} placeholder={`输入 ${userId} 确认永久删除`} /><button type="button" className="danger" onClick={handleDeleteAccount} disabled={busy !== null || accountDeletionConfirm !== userId}>{busy === "delete-account" ? "正在永久删除…" : "永久删除账号"}</button></article>
          <article className="audit-card"><span>04 / AUDIT</span><h3>最近操作</h3><button type="button" className="secondary" onClick={handleLoadAudit} disabled={busy !== null}>{busy === "audit" ? "读取中…" : "刷新审计日志"}</button>{auditEvents.length ? <div>{auditEvents.map((event) => <p key={event.id}><b>{event.action}</b><small>{event.resource_id ?? event.resource_type}</small></p>)}</div> : <p>尚未读取审计事件。</p>}</article>
        </div>
      </section>

      <SiteFooter />
    </main>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="empty"><span>＋</span><p>{text}</p></div>;
}

function Metric({ label, value }: { label: string; value?: number }) {
  return <article><span>{label}</span><strong>{value === undefined ? "—" : Math.round(value * 100)}<small>{value === undefined ? "" : "%"}</small></strong><i><b style={{ width: `${(value ?? 0) * 100}%` }} /></i></article>;
}
