import { readRunEvents } from "./run-events";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type ProfileItem = {
  id: string;
  category: string;
  name: string;
  level: number;
  confidence: number;
  evidence_ids: string[];
};

export type Profile = { user_id: string; items: ProfileItem[]; count: number };

export type ProfileProposal = {
  id: string;
  user_id: string;
  message: string;
  changes: Array<{
    action: "upsert" | "remove";
    category: string;
    name: string;
    level: number;
    confidence: number;
  }>;
  status: "pending" | "approved" | "rejected";
  created_at: string;
  resolved_at: string | null;
};

export type Match = {
  name: string;
  priority: "required" | "preferred";
  status: "strong" | "partial" | "gap";
  confidence?: number;
  evidence_ids: string[];
};

export type JobAnalysis = {
  id: string;
  title: string;
  score: number;
  matches: Match[];
  gaps: Match[];
  learning_path: Array<{
    stage: number;
    skill: string;
    weeks: number;
    start_week?: number;
    estimated_hours?: number;
    current_level?: number;
    goal: string;
    deliverables: string[];
  }>;
  report: {
    summary: string;
    recommendation: string;
    claim_policy: string;
    required_gap_count?: number;
    weekly_hours?: number;
  };
};

export type CareerReport = {
  id: string;
  user_id: string;
  job_analysis_id: string;
  version: number;
  title: string;
  content: {
    executive_summary: string;
    interview_pitch: string;
    claim_policy: string;
    core_capabilities: Array<{
      name: string;
      category: string;
      level: number;
      confidence: number;
      evidence_ids: string[];
    }>;
    evidence_catalog: Array<{ id: string; source_type: string; source_name: string }>;
    career_direction: { primary_role: string; match_score: number; recommendation: string };
    job_matching: Match[];
    skill_gaps: Match[];
    learning_path: JobAnalysis["learning_path"];
    action_plan: string[];
    referenced_evidence_ids: string[];
  };
  markdown: string;
  model_diagnostics: { provider: string; model: string; fallback: boolean; reason?: string };
  is_stale: boolean;
  created_at: string;
};

export type KnowledgeMode = "rag" | "wiki" | "hybrid";

export type WikiPage = {
  id: string;
  slug: string;
  title: string;
  content: string;
  version: number;
  chunk_refs: string[];
};

type EvidenceItem = { id: string; source_name: string; content: string };

export type ChatResult = {
  thread_id: string;
  intent: string;
  answer: string;
  evidence: Array<{
    source_kind?: "rag";
    evidence_id: string;
    score: number;
    source_name: string;
    content: string;
    rerank_score: number;
    retrieval_method: string;
  } | {
    source_kind: "wiki";
    page_id: string;
    slug: string;
    title: string;
    content: string;
    chunk_refs: string[];
  }>;
  retrieval: {
    mode?: KnowledgeMode;
    backend?: string;
    fusion?: string;
    knowledge_fusion?: string;
    reranker?: string;
    fallback?: boolean;
    reason?: string;
  };
  model: { provider: string; model: string; fallback: boolean; reason?: string };
  messages: Array<{ role: string; content: string; intent?: string | null; created_at?: string | null }>;
};

export type EvaluationRun = {
  id: string;
  dataset_name: string;
  profile_extraction_f1: number;
  evidence_recall_at_k: number;
  supported_claim_rate: number;
  requirement_matching_f1: number;
  metrics: { case_count: number; query_count: number; claim_count: number; recall_k: number };
  details: {
    regression?: {
      status: "passed" | "failed";
      minimums: Record<string, number>;
      failures: RegressionFailure[];
    };
  };
  created_at: string;
};

export type RegressionFailure = {
  metric: string;
  actual: number;
  minimum: number;
  delta: number;
};

export type RegressionResult = {
  status: "passed" | "failed";
  run: EvaluationRun;
  minimums: Record<string, number>;
  failures: RegressionFailure[];
};

export type ObservabilitySummary = {
  request_count: number;
  success_rate: number;
  average_latency_ms: number;
  p95_latency_ms: number;
  prompt_tokens: number;
  completion_tokens: number;
  estimated_cost_usd: number;
  status_counts: Record<string, number>;
  providers: Record<string, number>;
};

export type AccessTokenCreated = {
  id: string;
  user_id: string;
  name: string;
  scopes: string[];
  token: string;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  action: string;
  resource_type: string;
  resource_id: string | null;
  details: Record<string, unknown>;
  created_at: string;
};

export type AccountDeletionResult = {
  deleted: boolean;
  receipt_id: string;
  deleted_counts: Record<string, number>;
  vector_result: Record<string, unknown>;
  checkpoint_result: { status: string; deleted: number };
  created_at: string;
};

function authorizationHeaders(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const token = window.sessionStorage.getItem("careerlens_access_token");
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export type RunRequest =
  | { operation: "job_analysis"; input: { title: string; jd_text: string; weekly_hours: number } }
  | { operation: "report"; input: { job_analysis_id: string } }
  | { operation: "wiki_compile"; input: {
      slug: string; title: string; evidence_ids: string[]; base_version?: number;
    }; requires_confirmation?: boolean };

export type RunStatus = "queued" | "running" | "waiting_confirmation" |
  "succeeded" | "failed" | "cancelled" | "interrupted";

export type BackgroundRun = {
  id: string;
  user_id: string;
  operation: RunRequest["operation"] | "file_import" | "media_import";
  status: RunStatus;
  confirmation: string;
  attempts: number;
  event_seq: number;
  error_code: string | null;
  result: null | {
    job_analysis_id?: string;
    report_id?: string;
    wiki_slug?: string;
    count?: number;
    parse_status?: string;
    version?: number;
  };
  created_at: string;
};

export type RunEvent = {
  run_id: string;
  seq: number;
  generation: number;
  event_type: string;
  data: { step?: string; reason?: string; attempt?: number; citation_count?: number };
};

export const terminalRun = (status: RunStatus) =>
  status === "succeeded" || status === "failed" || status === "cancelled";

const runQuery = (userId: string) => new URLSearchParams({ user_id: userId }).toString();
const runPath = (userId: string, id: string, suffix = "") =>
  `/runs/${encodeURIComponent(id)}${suffix}?${runQuery(userId)}`;

export function createRun(userId: string, payload: RunRequest, key: string) {
  return request<BackgroundRun>("/runs", {
    method: "POST",
    headers: { "Idempotency-Key": key },
    body: JSON.stringify({ user_id: userId, ...payload }),
  });
}

export function createUploadRun(userId: string, file: File, media: boolean, key: string) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("upload", file);
  form.append("media", String(media));
  return upload<BackgroundRun>("/runs/uploads", form, { "Idempotency-Key": key });
}

export function listRuns(userId: string, signal?: AbortSignal) {
  return request<BackgroundRun[]>(`/runs?${runQuery(userId)}`, { signal });
}

export function getRun(userId: string, id: string, signal?: AbortSignal) {
  return request<BackgroundRun>(runPath(userId, id), { signal });
}

export function cancelRun(userId: string, id: string) {
  return request<BackgroundRun>(runPath(userId, id, "/cancel"), { method: "POST" });
}

export function decideRun(userId: string, id: string, approve: boolean) {
  return request<BackgroundRun>(runPath(userId, id, "/decision"), {
    method: "POST", body: JSON.stringify({ approve }),
  });
}

export async function streamRun(
  userId: string, id: string, after: number,
  signal: AbortSignal, onEvent: (event: RunEvent) => void,
) {
  const response = await fetch(`${API_URL}${runPath(userId, id, "/stream")}`, {
    headers: {
      ...authorizationHeaders(), Accept: "text/event-stream", "Last-Event-ID": String(after),
    },
    signal, cache: "no-store",
  });
  if (!response.ok || !response.body) throw new Error(`无法订阅任务进度 (${response.status})`);
  await readRunEvents(response.body, (event) => onEvent(event as RunEvent));
}

export function getJobAnalysis(id: string) {
  return request<JobAnalysis>(`/jobs/${encodeURIComponent(id)}`);
}

export function getCareerReport(id: string) {
  return request<CareerReport>(`/reports/${encodeURIComponent(id)}`);
}

export function setAccessToken(token: string) {
  window.sessionStorage.setItem("careerlens_access_token", token);
}

export function clearAccessToken() {
  window.sessionStorage.removeItem("careerlens_access_token");
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...authorizationHeaders(), ...init?.headers },
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail ?? "请求失败，请检查后端服务。");
  }
  return payload as T;
}

async function upload<T>(path: string, form: FormData, headers?: Record<string, string>): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: { ...authorizationHeaders(), ...headers },
    body: form,
  });
  const payload = await response.json();
  if (!response.ok) throw new Error(payload.detail ?? "文件导入失败。");
  return payload as T;
}

async function requestText(path: string): Promise<string> {
  const response = await fetch(`${API_URL}${path}`, { headers: authorizationHeaders() });
  if (!response.ok) {
    const payload = await response.json();
    throw new Error(payload.detail ?? "请求失败，请检查后端服务。");
  }
  return response.text();
}

export function importEvidence(userId: string, content: string) {
  return request("/evidence/text", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      source_type: "self_statement",
      source_name: "career-workspace",
      content,
    }),
  });
}

export function importBilibiliExport(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("upload", file);
  return upload<{ created_count: number; skipped_count: number; duplicate_count: number }>(
    "/connectors/bilibili/import",
    form,
  );
}

export function importWeiboExport(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("upload", file);
  return upload<{ created_count: number; skipped_count: number; duplicate_count: number }>(
    "/connectors/weibo/import",
    form,
  );
}

export function importBrowserCapture(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("upload", file);
  return upload<{ created_count: number; skipped_count: number; duplicate_count: number }>(
    "/connectors/browser/import",
    form,
  );
}

export function importMedia(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("source_type", "personal_media");
  form.append("upload", file);
  return upload<{ count: number }>("/evidence/media", form);
}

export function importFile(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("source_type", "resume");
  form.append("upload", file);
  return upload<{ count: number }>("/evidence/file", form);
}

export function rebuildProfile(userId: string) {
  return request<Profile>(`/profiles/${encodeURIComponent(userId)}/rebuild`, { method: "POST" });
}

export function getProfile(userId: string) {
  return request<Profile>(`/profiles/${encodeURIComponent(userId)}`);
}

export function proposeProfileUpdate(userId: string, message: string) {
  return request<ProfileProposal>(`/profiles/${encodeURIComponent(userId)}/proposals`, {
    method: "POST",
    body: JSON.stringify({ message }),
  });
}

export function decideProfileUpdate(proposalId: string, approve: boolean) {
  return request<ProfileProposal>(`/profiles/proposals/${proposalId}/decision`, {
    method: "POST",
    body: JSON.stringify({ approve }),
  });
}

export function analyzeJob(userId: string, title: string, jdText: string, weeklyHours: number) {
  return request<JobAnalysis>("/jobs/analyze", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, title, jd_text: jdText, weekly_hours: weeklyHours }),
  });
}

export function generateCareerReport(userId: string, jobAnalysisId: string) {
  return request<CareerReport>("/reports", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, job_analysis_id: jobAnalysisId }),
  });
}

export function downloadCareerReport(reportId: string) {
  return requestText(`/reports/${encodeURIComponent(reportId)}/markdown`);
}

export function listWikiEvidence(userId: string, offset = 0) {
  const query = new URLSearchParams({ user_id: userId, limit: "50", offset: String(offset) });
  return request<{ items: EvidenceItem[] }>(`/evidence?${query}`);
}

export function getWikiPage(userId: string, slug: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<WikiPage>(`/wiki/${encodeURIComponent(slug)}?${query}`);
}

export function compileWikiPage(userId: string, slug: string, title: string, evidenceIds: string[]) {
  return request<{ page: WikiPage }>("/wiki/compile", {
    method: "POST",
    body: JSON.stringify({ user_id: userId, slug, title, evidence_ids: evidenceIds }),
  });
}

export function sendChat(
  userId: string, message: string, threadId?: string, jobAnalysisId?: string,
  mode: KnowledgeMode = "rag",
) {
  return request<ChatResult>("/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      message,
      thread_id: threadId ?? null,
      job_analysis_id: jobAnalysisId ?? null,
      mode,
    }),
  });
}

export function runSampleRegression() {
  return request<RegressionResult>("/evaluation/regression/sample", { method: "POST" });
}

export function runBenchmarkRegression() {
  return request<RegressionResult>("/evaluation/regression/benchmark", { method: "POST" });
}

export function getEvaluationRuns() {
  return request<EvaluationRun[]>("/evaluation/runs?limit=1");
}

export function getObservabilitySummary() {
  return request<ObservabilitySummary>("/observability/summary");
}

export function registerOwner(userId: string, registrationSecret: string) {
  return request<AccessTokenCreated>("/auth/register", {
    method: "POST",
    headers: registrationSecret ? { "X-Registration-Secret": registrationSecret } : {},
    body: JSON.stringify({ user_id: userId, name: "owner" }),
  });
}

export function exportUserData(userId: string) {
  return request<Record<string, unknown>>(`/privacy/${encodeURIComponent(userId)}/export`);
}

export function getAuditLog(userId: string) {
  return request<AuditEvent[]>(`/privacy/${encodeURIComponent(userId)}/audit?limit=20`);
}

export function deleteEvidence(evidenceId: string) {
  return request<{ deleted: boolean; removed_profile_items: number }>(
    `/evidence/${encodeURIComponent(evidenceId)}`,
    { method: "DELETE" },
  );
}

export function deleteAccount(userId: string) {
  return request<AccountDeletionResult>(`/privacy/${encodeURIComponent(userId)}`, {
    method: "DELETE",
  });
}
