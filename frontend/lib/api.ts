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
  report: { summary: string; recommendation: string; claim_policy: string };
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

export type ChatResult = {
  thread_id: string;
  intent: string;
  answer: string;
  evidence: Array<{
    evidence_id: string;
    score: number;
    source_name: string;
    content: string;
    rerank_score: number;
    retrieval_method: string;
  }>;
  retrieval: {
    backend: string;
    fusion: string;
    reranker: string;
    fallback: boolean;
    reason?: string;
  };
  model: { provider: string; model: string; fallback: boolean; reason?: string };
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

async function upload<T>(path: string, form: FormData): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: "POST",
    headers: authorizationHeaders(),
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

export function importMedia(userId: string, file: File) {
  const form = new FormData();
  form.append("user_id", userId);
  form.append("source_type", "personal_media");
  form.append("upload", file);
  return upload<{ count: number }>("/evidence/media", form);
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

export function sendChat(userId: string, message: string, threadId?: string, jobAnalysisId?: string) {
  return request<ChatResult>("/chat", {
    method: "POST",
    body: JSON.stringify({
      user_id: userId,
      message,
      thread_id: threadId ?? null,
      job_analysis_id: jobAnalysisId ?? null,
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
