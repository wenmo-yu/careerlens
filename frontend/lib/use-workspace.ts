"use client";

import { ChangeEvent, FormEvent, useEffect, useMemo, useRef, useState } from "react";
import type { ImportResult } from "@/components/import-result-card";
import { BrowserCaptureDraft, parseBrowserCaptureDraft } from "@/lib/browser-capture";
import {
  BackgroundRun,
  CareerReport,
  ChatResult,
  createRun,
  createUploadRun,
  getCareerReport,
  getJobAnalysis,
  getWikiPage,
  KnowledgeMode,
  listWikiEvidence,
  WikiPage,
  importEvidence,
  importBilibiliExport,
  importBrowserCapture,
  importWeiboExport,
  JobAnalysis,
  Profile,
  ProfileProposal,
  EvidenceItem,
  EvaluationRun,
  ObservabilitySummary,
  AuditEvent,
  decideProfileUpdate,
  clearAccessToken,
  deleteAccount,
  deleteEvidence,
  downloadCareerReport,
  exportUserData,
  getAuditLog,
  getProfile,
  getProfileOverview,
  getRoles,
  getCourses,
  recommendRoles,
  saveJob,
  listSavedJobs,
  compareSavedJobs,
  updateLearningProgress,
  type Course,
  type LearningPlanStep,
  type RoleSuggestion,
  type SavedJob,
  listEvidence,
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

/**
 * All workbench state and side effects.
 *
 * Keeping them here lets the page stay a pure rendering layer: every handler
 * below is the single owner of one API call, and the page never mutates state
 * inline beyond controlled inputs.
 */
export function useWorkspace() {
  const [userId, setUserId] = useState("demo-user");
  const [evidenceText, setEvidenceText] = useState(demoEvidence);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [overview, setOverview] = useState<Awaited<ReturnType<typeof getProfileOverview>> | null>(null);
  const [evidenceList, setEvidenceList] = useState<EvidenceItem[]>([]);
  const [jobTitle, setJobTitle] = useState("AI Agent 开发实习生");
  const [jdText, setJdText] = useState(demoJd);
  const [weeklyHours, setWeeklyHours] = useState(8);
  const [analysis, setAnalysis] = useState<JobAnalysis | null>(null);
  const [roleSuggestions, setRoleSuggestions] = useState<RoleSuggestion[]>([]);
  const [courses, setCourses] = useState<Course[]>([]);
  const [savedJobs, setSavedJobs] = useState<SavedJob[]>([]);
  const [savedJobTitle, setSavedJobTitle] = useState("");
  const [report, setReport] = useState<CareerReport | null>(null);
  const [chatInput, setChatInput] = useState("为什么认为我适合 Agent 开发？");
  const [chat, setChat] = useState<ChatResult | null>(null);
  const [knowledgeMode, setKnowledgeMode] = useState<KnowledgeMode>("rag");
  const [wikiSources, setWikiSources] = useState<{
    userId: string;
    items: Awaited<ReturnType<typeof listWikiEvidence>>["items"];
    offset: number;
  } | null>(null);
  const [wikiSelection, setWikiSelection] = useState<string[]>([]);
  const [wikiTitle, setWikiTitle] = useState("");
  const [confirmWiki, setConfirmWiki] = useState(false);
  const [openedWiki, setOpenedWiki] = useState<{ userId: string; page: WikiPage } | null>(null);
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
  const [latestRun, setLatestRun] = useState<BackgroundRun | null>(null);
  const [importResult, setImportResult] = useState<ImportResult | null>(null);
  const [tasksVersion, setTasksVersion] = useState(0);
  const activeAction = useRef(false);
  const submittedKeys = useRef(new Map<string, string>());

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
    void Promise.all([getRoles(), getCourses(), listSavedJobs(userId)])
      .then(([, courseRows, jobs]) => {
        setCourses(courseRows);
        setSavedJobs(jobs);
      })
      .catch(() => undefined);
    // Reload the persisted profile so a refresh never looks like data loss.
    void getProfile(userId).then(setProfile).catch(() => setProfile(null));
    void getProfileOverview(userId).then(setOverview).catch(() => setOverview(null));
    void listEvidence(userId).then((payload) => setEvidenceList(payload.items)).catch(() => setEvidenceList([]));
  }, [userId]);


  async function run(label: string, action: () => Promise<void>) {
    if (activeAction.current) return;
    activeAction.current = true;
    setBusy(label);
    setNotice(null);
    try {
      await action();
    } catch (error) {
      setNotice({ kind: "error", text: error instanceof Error ? error.message : "操作失败" });
    } finally {
      activeAction.current = false;
      setBusy(null);
    }
  }

  async function submitTask(identity: string, submit: (key: string) => Promise<BackgroundRun>) {
    const key = submittedKeys.current.get(identity) ?? crypto.randomUUID();
    submittedKeys.current.set(identity, key);
    const task = await submit(key);
    submittedKeys.current.delete(identity);
    setLatestRun(task);
    setNotice({ kind: "ok", text: task.status === "waiting_confirmation"
      ? "任务已创建，在后台任务中确认后执行。" : "已提交，可在后台任务中查看进度与结果。" });
    document.getElementById("runs")?.scrollIntoView({ block: "start" });
  }

  function openRunResult(task: BackgroundRun) {
    if (task.user_id !== userId || !task.result) return;
    const result = task.result;
    void run("run-result", async () => {
      if (task.operation === "file_import" || task.operation === "media_import") {
        const { items } = await listWikiEvidence(userId);
        const wanted = new Set(result.evidence_ids ?? []);
        setImportResult({
          label: task.operation === "file_import" ? "文档导入" : "媒体解析",
          count: result.count ?? 0,
          parseStatus: result.parse_status,
          readableCount: result.readable_count,
          ocrPendingCount: result.ocr_pending_count,
          duplicateCount: result.duplicate_count,
          warnings: result.warnings,
          evidenceIds: result.evidence_ids,
          items: wanted.size ? items.filter((item) => wanted.has(item.id)) : [],
        });
        document.getElementById("profile")?.scrollIntoView({ block: "start" });
      } else if (result.job_analysis_id) {
        setAnalysis(await getJobAnalysis(result.job_analysis_id));
        setReport(null);
        document.getElementById("matching")?.scrollIntoView();
      } else if (result.report_id) {
        setReport(await getCareerReport(result.report_id));
        document.getElementById("report")?.scrollIntoView();
      } else if (result.wiki_slug) {
        setOpenedWiki({ userId, page: await getWikiPage(userId, result.wiki_slug) });
        setKnowledgeMode("hybrid");
        document.getElementById("copilot")?.scrollIntoView();
      }
    });
  }

  function handleBuildProfile(event: FormEvent) {
    event.preventDefault();
    void run("profile", async () => {
      await importEvidence(userId, evidenceText);
      const result = await rebuildProfile(userId);
      setProfile(result);
      setOverview(await getProfileOverview(userId));
      setEvidenceList((await listEvidence(userId)).items);
      setAnalysis(null);
      setReport(null);
      setTelemetry(await getObservabilitySummary());
      setNotice({ kind: "ok", text: `画像已更新：${result.count} 个可追溯条目` });
    });
  }

  function handleJob(event: FormEvent) {
    event.preventDefault();
    void run("job", async () => {
      const input = { title: jobTitle, jd_text: jdText, weekly_hours: weeklyHours };
      await submitTask(JSON.stringify([userId, "job", input]), (key) =>
        createRun(userId, { operation: "job_analysis", input }, key));
    });
  }

  function handleSaveJob() {
    void run("save-job", async () => {
      const saved = await saveJob({
        user_id: userId,
        title: savedJobTitle.trim() || jobTitle,
        jd_text: jdText,
        notes: weeklyHours ? `每周可投入 ${weeklyHours} 小时` : "",
      });
      setSavedJobs((await listSavedJobs(userId)));
      setSavedJobTitle("");
      const comparison = await compareSavedJobs(userId);
      setNotice({ kind: "ok", text: `已保存「${saved.title}」；当前可对比 ${comparison.count} 份 JD。${comparison.note}` });
    });
  }

  function handleRecommendRoles() {
    void run("roles", async () => {
      const rows = await recommendRoles(userId, 5);
      setRoleSuggestions(rows);
      setNotice({ kind: "ok", text: rows.length ? `给出 ${rows.length} 个相邻方向，理由均可回查证据。` : "暂无可推荐方向，请先导入证据并生成画像。" });
    });
  }

  function handleProgress(step: LearningPlanStep, status: string) {
    void run("progress", async () => {
      await updateLearningProgress(analysis?.id ?? "manual-plan", userId, {
        skill: step.skill, stage: step.stage, status,
        evidence_ids: step.source_evidence_ids ?? [],
        actual_hours: step.estimated_hours ?? 0,
      });
      setNotice({ kind: "ok", text: `${step.skill} 进度已更新为「${status}」；完成状态不会自动新增能力事实。` });
    });
  }

  function handleChat(event: FormEvent) {
    event.preventDefault();
    void run("chat", async () => {
      const result = await sendChat(userId, chatInput, chat?.thread_id, analysis?.id, knowledgeMode);
      setChat(result);
      setTelemetry(await getObservabilitySummary());
    });
  }

  function loadWikiSources(offset = 0, resetSelection = false) {
    void run("wiki-sources", async () => {
      const { items } = await listWikiEvidence(userId, offset);
      setWikiSources({ userId, items, offset });
      if (resetSelection || wikiSources?.userId !== userId) setWikiSelection([]);
    });
  }

  function handleWikiCompile(event: FormEvent) {
    event.preventDefault();
    if (wikiSources?.userId !== userId || !wikiSelection.length || !wikiTitle.trim()) return;
    void run("wiki-compile", async () => {
      const title = wikiTitle.trim();
      const ids = [...wikiSelection].sort();
      await submitTask(JSON.stringify([userId, "wiki", title, ids, confirmWiki]), (key) =>
        createRun(userId, {
          operation: "wiki_compile", requires_confirmation: confirmWiki,
          input: { slug: `topic-${key}`, title, evidence_ids: ids },
        }, key));
    });
  }

  function openWiki(slug: string) {
    void run("wiki-page", async () => {
      const page = await getWikiPage(userId, slug);
      setOpenedWiki({ userId, page });
    });
  }

  function handleReport() {
    if (!analysis) return;
    void run("report", async () => {
      await submitTask(JSON.stringify([userId, "report", analysis.id]), (key) =>
        createRun(userId, { operation: "report", input: { job_analysis_id: analysis.id } }, key));
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
      if (approve) {
        setProfile(await getProfile(userId));
        setOverview(await getProfileOverview(userId));
        setAnalysis(null);
        setReport(null);
      }
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
    handleUpload(event, true);
  }

  function handleDocument(event: ChangeEvent<HTMLInputElement>) {
    handleUpload(event, false);
  }

  function handleUpload(event: ChangeEvent<HTMLInputElement>, media: boolean) {
    const file = event.target.files?.[0];
    if (!file) return;
    void run(media ? "media" : "document", async () => {
      const identity = JSON.stringify([userId, media, file.name, file.size, file.lastModified]);
      await submitTask(identity, (key) => createUploadRun(userId, file, media, key));
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
      setTasksVersion((current) => current + 1);
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
    if (!deleteEvidenceId || !window.confirm("确认删除这条 Evidence？关联的解析块、Wiki 专题和版本也可能被删除。")) return;
    void run("delete", async () => {
      const result = await deleteEvidence(deleteEvidenceId);
      setDeleteEvidenceId("");
      setProfile(await getProfile(userId));
      setOverview(await getProfileOverview(userId));
      setEvidenceList((await listEvidence(userId)).items);
      setOpenedWiki(null);
      setChat(null);
      setAnalysis(null);
      setReport(null);
      setWikiSources(null);
      setWikiSelection([]);
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
      setOpenedWiki(null);
      setWikiSources(null);
      setWikiSelection([]);
      setProposal(null);
      setAuditEvents([]);
      setLatestRun(null);
      submittedKeys.current.clear();
      setTasksVersion((current) => current + 1);
      setNotice({ kind: "ok", text: `账号数据已删除。匿名回执：${result.receipt_id}` });
    });
  }


  return {
    userId, setUserId, evidenceText, setEvidenceText, profile, setProfile, overview, setOverview, evidenceList, setEvidenceList, jobTitle, setJobTitle, jdText, setJdText, weeklyHours, setWeeklyHours, analysis, setAnalysis, roleSuggestions, setRoleSuggestions, courses, setCourses, savedJobs, setSavedJobs, savedJobTitle, setSavedJobTitle, report, setReport, chatInput, setChatInput, chat, setChat, knowledgeMode, setKnowledgeMode, wikiSources, setWikiSources, wikiSelection, setWikiSelection, wikiTitle, setWikiTitle, confirmWiki, setConfirmWiki, openedWiki, setOpenedWiki, memoryInput, setMemoryInput, proposal, setProposal, evaluation, setEvaluation, telemetry, setTelemetry, registrationSecret, setRegistrationSecret, issuedToken, setIssuedToken, deleteEvidenceId, setDeleteEvidenceId, accountDeletionConfirm, setAccountDeletionConfirm, auditEvents, setAuditEvents, busy, setBusy, notice, setNotice, browserDraft, setBrowserDraft, selectedCaptureItems, setSelectedCaptureItems, latestRun, setLatestRun, importResult, setImportResult, tasksVersion, setTasksVersion, run, submitTask, openRunResult, handleBuildProfile, handleJob, handleSaveJob, handleRecommendRoles, handleProgress, handleChat, loadWikiSources, handleWikiCompile, openWiki, handleReport, handleReportDownload, handleProposal, handleDecision, handleBilibili, handleWeibo, handleBrowserCapture, handleConfirmBrowserCapture, handleMedia, handleDocument, handleUpload, handleEvaluation, handleRegisterOwner, handleExport, handleLoadAudit, handleDeleteEvidence, handleDeleteAccount, skills,
  };
}
