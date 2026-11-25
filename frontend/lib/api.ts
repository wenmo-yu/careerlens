import { readRunEvents } from "./run-events";

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api/v1";

export type ProfileItem = {
  id: string;
  user_id?: string;
  category: string;
  name: string;
  level: number;
  confidence: number;
  evidence_ids: string[];
  details?: Record<string, unknown>;
  updated_at?: string;
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
    source_evidence_ids?: string[];
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

export type EvidenceItem = {
  id: string;
  user_id?: string;
  source_type: string;
  source_name: string;
  content: string;
  content_type?: string;
  chunk_index?: number;
  source_metadata?: Record<string, unknown>;
  created_at?: string;
};

export type EvidenceBatch = {
  items: EvidenceItem[];
  count: number;
  parse_status?: string | null;
  source_document_id?: string | null;
  readable_count?: number;
  ocr_pending_count?: number;
  duplicate_count?: number;
  warnings?: string[];
};

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
    source_document_id?: string;
    readable_count?: number;
    ocr_pending_count?: number;
    duplicate_count?: number;
    warnings?: string[];
    evidence_ids?: string[];
    version?: number;
  };
  created_at: string;
};

export type RunEvent = {
  run_id: string;
  seq: number;
  generation: number;
  event_type: string;
  data: {
    step?: string;
    reason?: string;
    attempt?: number;
    citation_count?: number;
    duration_ms?: number;
    error_type?: string;
    fallback?: boolean;
    block_count?: number;
  };
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
  return request<EvidenceBatch>("/evidence/text", {
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

export type SourceSpec = {
  key: string;
  label: string;
  auth_level: "A" | "B" | "T" | "C";
  auth_label: string;
  formats: string[];
  endpoint: string | null;
  available: boolean;
  evidence_kind: string;
  note: string;
};

export function getSourceRegistry() {
  return request<{ sources: SourceSpec[] }>("/connectors/registry");
}

export function importPublicLinks(userId: string, cards: Array<{
  url: string; title: string; note?: string; confirmed: boolean;
}>) {
  return request<{ created_count: number; skipped_count: number; duplicate_count: number }>(
    "/connectors/public-link/import",
    { method: "POST", body: JSON.stringify({ user_id: userId, cards }) },
  );
}

export function importGitHubRepos(userId: string, token: string, repos: string[]) {
  return request<{ created_count: number; skipped_count: number; duplicate_count: number; connector: string }>(
    "/connectors/github/import",
    { method: "POST", body: JSON.stringify({ user_id: userId, token, repos }) },
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
  return upload<EvidenceBatch>("/evidence/file", form);
}

export function rebuildProfile(userId: string) {
  return request<Profile>(`/profiles/${encodeURIComponent(userId)}/rebuild`, { method: "POST" });
}

export function getProfile(userId: string) {
  return request<Profile>(`/profiles/${encodeURIComponent(userId)}`);
}

export function getProfileOverview(userId: string) {
  return request<{
    user_id: string;
    evidence_count: number;
    source_document_count: number;
    readable_evidence_count: number;
    profile_item_count: number;
    confirmed_item_count: number;
    self_report_item_count: number;
    coverage: { supported: number; weak: number; missing: number };
    by_category: Record<string, number>;
    assessments: Array<{
      instrument: string; title: string | null; version: string;
      code: string | null; taken_at: string; note: string;
    }>;
    generated_at: string;
    methodology: string;
  }>(`/profiles/${encodeURIComponent(userId)}/overview`);
}

export function getAgentManifest(userId: string) {
  return request<{
    schema_version: string;
    user_id: string;
    writable_policy: string;
    active_dimensions: string[];
    enabled_dimensions: string[];
    capabilities: Array<{
      name: string;
      endpoint: string;
      requires_scope: string;
      evidence_policy: string;
    }>;
    notes: string[];
  }>(`/profiles/${encodeURIComponent(userId)}/agent-manifest`);
}

export function listEvidence(userId: string, limit = 100) {
  const query = new URLSearchParams({ user_id: userId, limit: String(limit) });
  return request<EvidenceBatch>(`/evidence?${query}`);
}

export type RoleTemplate = {
  role_id: string;
  name: string;
  family: string;
  typical_tasks: string[];
  required_skills: string[];
  nice_to_have: string[];
  entry_evidence: string[];
  growth_path: string[];
  source_note: string;
};

export type Course = {
  course_id: string;
  title: string;
  skill: string;
  level: string;
  format: string;
  provider: string;
  estimated_hours: number;
  cost: string;
  prerequisites: string[];
  url: string;
  license: string;
  language: string;
  last_checked_at: string;
  alternative_ids: string[];
  verification: string;
};

export type RoleSuggestion = {
  role_id: string;
  name: string;
  family: string;
  matched_required: string[];
  matched_nice_to_have: string[];
  gaps: string[];
  evidence_ids: string[];
  reason: string;
  typical_tasks: string[];
  growth_path: string[];
  source_note: string;
  coverage: number;
};

export type SavedJob = {
  id: string;
  title: string;
  jd_text: string;
  source_type: string;
  source_url: string | null;
  notes: string;
  created_at: string;
};

export type LearningPlanStep = JobAnalysis["learning_path"][number] & {
  priority?: string;
  target_level?: number;
  resources?: Array<{ course_id: string; title: string; url: string; estimated_hours: number; prerequisites: string[] }>;
  verification?: string;
  progress_status?: string;
};

export function getRoles() { return request<RoleTemplate[]>("/catalog/roles"); }
export function getCourses() { return request<Course[]>("/catalog/courses"); }
export function recommendRoles(userId: string, limit = 5) {
  return request<RoleSuggestion[]>("/recommendations/roles", {
    method: "POST", body: JSON.stringify({ user_id: userId, limit }),
  });
}
export function saveJob(payload: {
  user_id: string; title: string; jd_text: string; source_type?: string;
  source_url?: string | null; notes?: string;
}) { return request<SavedJob>("/saved-jobs", { method: "POST", body: JSON.stringify(payload) }); }
export function listSavedJobs(userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<SavedJob[]>(`/saved-jobs?${query}`);
}
export function deleteSavedJob(id: string, userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<{ deleted: boolean }>(`/saved-jobs/${encodeURIComponent(id)}?${query}`, { method: "DELETE" });
}
export function compareSavedJobs(userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<{ count: number; jobs: SavedJob[]; note: string }>(`/saved-jobs/compare?${query}`);
}
export function getLearningPlan(planId: string, userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<{ plan_id: string; items: Array<{ skill: string; stage: number; status: string; evidence_ids: string[]; actual_hours: number; note: string }> }>(
    `/learning/plans/${encodeURIComponent(planId)}?${query}`,
  );
}
export function updateLearningProgress(planId: string, userId: string, payload: {
  skill: string; stage: number; status: string; evidence_ids?: string[]; actual_hours?: number; note?: string;
}) {
  const query = new URLSearchParams({ user_id: userId });
  return request<{ skill: string; stage: number; status: string }>(
    `/learning/plans/${encodeURIComponent(planId)}/progress?${query}`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export type AssessmentQuestion = { id: string; text: string };

export type AssessmentLicense = {
  items: string;
  license: string;
  attribution: string;
  not_used: string[];
};

export type AssessmentInstrumentSummary = {
  instrument_id: string;
  version: string;
  title: string;
  subtitle: string;
  estimated_minutes: number;
  item_count: number;
  scoring_type: "dichotomy" | "interest" | "trait";
  license_summary: string;
  disclaimer: string;
};

export type AssessmentPole = {
  key: string;
  label: string;
  mean?: number;
  percent?: number;
  answered?: number;
};

export type AssessmentDimension = {
  key: string;
  label: string;
  description: string;
  poles?: Array<{ key: string; label: string }>;
};

export type AssessmentInstrument = AssessmentInstrumentSummary & {
  construct: string;
  response_scale: { min: number; max: number; labels: string[]; prompt: string };
  license: AssessmentLicense;
  dimensions: AssessmentDimension[];
  items: Array<{ id: string; text: string; dimension: string }>;
};

export type AssessmentScore = {
  key?: string;
  dimension?: string;
  label: string;
  letter?: string;
  score?: number;
  mean?: number;
  band?: string;
  strength?: number;
  balanced?: boolean;
  description?: string;
  poles?: AssessmentPole[];
};

export type AssessmentComputed = {
  scoring_type: "dichotomy" | "interest" | "trait";
  code: string | null;
  code_label: string | null;
  scores: AssessmentScore[];
  hints: string[];
  role_hints?: Array<{
    role_id: string; name: string; family: string; riasec: string[];
    match: number; reason: string;
  }>;
  clarity?: number;
  balanced_dimensions?: string[];
  consistency?: { level: string; note: string };
  differentiation?: number;
  completeness: number;
  answered_count: number;
  item_count: number;
  methodology: string;
  disclaimer: string;
  license: AssessmentLicense;
  instrument_title: string;
  instrument_version: string;
};

export type AssessmentSubmission = {
  id: string;
  instrument: string;
  version: string;
  result: AssessmentComputed;
  taken_at: string;
  note: string;
};

export function listAssessmentInstruments() {
  return request<{ instruments: AssessmentInstrumentSummary[]; note: string }>(
    "/assessments/instruments",
  );
}

export function getAssessmentInstrument(instrumentId: string) {
  return request<AssessmentInstrument>(
    `/assessments/instruments/${encodeURIComponent(instrumentId)}`,
  );
}

export function submitInstrumentAssessment(instrumentId: string, payload: {
  user_id: string; answers: Record<string, number>; consent: boolean;
}) {
  return request<AssessmentSubmission>(
    `/assessments/instruments/${encodeURIComponent(instrumentId)}/submit`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}

export type AssessmentResult = {
  id: string;
  instrument: string;
  version: string;
  result: Record<string, unknown>;
  taken_at: string;
  source: string;
};

export type DimensionView = {
  key: string;
  label: string;
  description: string;
  enabled: boolean;
  source: string;
  value: Record<string, unknown> | null;
  evidence_ids: string[];
};

export function getAssessmentQuestions(instrument: string) {
  return request<{ instrument: string; version: string; questions: AssessmentQuestion[]; note: string }>(
    `/assessments/questions/${encodeURIComponent(instrument)}`,
  );
}
export function submitAssessment(instrument: string, payload: {
  user_id: string; instrument: string; answers: Record<string, number>;
  label?: string; consent: boolean;
}) {
  return request<{ id: string; instrument: string; result: Record<string, unknown>; note: string }>(
    `/assessments/${encodeURIComponent(instrument)}/submit`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
export function listAssessmentResults(userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<AssessmentResult[]>(`/assessments/results?${query}`);
}
export function deleteAssessmentResult(id: string, userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<{ deleted: boolean }>(
    `/assessments/results/${encodeURIComponent(id)}?${query}`, { method: "DELETE" },
  );
}
export function getConstraints(userId: string) {
  const query = new URLSearchParams({ user_id: userId });
  return request<Array<{ kind: string; value: string; strength: number }>>(`/constraints/me?${query}`);
}
export function putConstraint(payload: {
  user_id: string; kind: string; value: string; strength?: number;
}) { return request<{ kind: string; value: string }>("/constraints/me", { method: "PUT", body: JSON.stringify(payload) }); }
export function getDimensions(userId: string) {
  return request<{ dimensions: DimensionView[]; note: string }>(
    `/profiles/${encodeURIComponent(userId)}/dimensions`,
  );
}
export function putDimension(userId: string, payload: {
  user_id: string; key: string; label: string; description?: string;
  enabled: boolean; value?: Record<string, unknown> | null; evidence_ids?: string[];
}) {
  return request<{ key: string; enabled: boolean }>(
    `/profiles/${encodeURIComponent(userId)}/dimensions`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}

export type ViewPreferences = {
  mode: string;
  mode_label: string;
  available_modes: Array<{ key: string; label: string }>;
  modules: Record<string, boolean>;
  note: string;
};

export type InterviewStory = {
  id: string;
  key: string;
  title: string;
  situation?: string;
  action?: string;
  result?: string;
  status: string;
  evidence_ids: string[];
};

export function getViewPreferences(userId: string) {
  return request<ViewPreferences>(
    `/profiles/${encodeURIComponent(userId)}/view-preferences`
  );
}
export function putViewPreferences(userId: string, payload: {
  user_id: string; mode: string; modules: Record<string, boolean>;
}) {
  return request<{ mode: string; mode_label: string; modules: Record<string, boolean> }>(
    `/profiles/${encodeURIComponent(userId)}/view-preferences`,
    { method: "PUT", body: JSON.stringify(payload) },
  );
}
export function getInterviewStories(userId: string) {
  return request<{ stories: InterviewStory[]; note: string }>(
    `/profiles/${encodeURIComponent(userId)}/interview-stories`
  );
}
export function createInterviewStory(userId: string, payload: {
  user_id: string; title: string; situation?: string; action?: string;
  result?: string; evidence_ids: string[];
}) {
  return request<{ id: string; status: string }>(
    `/profiles/${encodeURIComponent(userId)}/interview-stories`,
    { method: "POST", body: JSON.stringify(payload) },
  );
}
export function deleteInterviewStory(userId: string, storyId: string) {
  return request<{ deleted: boolean }>(
    `/profiles/${encodeURIComponent(userId)}/interview-stories/${encodeURIComponent(storyId)}`,
    { method: "DELETE" },
  );
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
