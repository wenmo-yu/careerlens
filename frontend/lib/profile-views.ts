import type { EvidenceItem, JobAnalysis, Profile, ProfileItem } from "./api";

export type ProfileOverview = {
  user_id: string;
  evidence_count: number;
  source_document_count: number;
  readable_evidence_count: number;
  profile_item_count: number;
  confirmed_item_count: number;
  self_report_item_count: number;
  coverage: { supported: number; weak: number; missing: number };
  by_category: Record<string, number>;
  assessments?: Array<{ instrument: string; title: string | null; code: string | null }>;
  generated_at: string;
  methodology: string;
};

export type SkillMatrixRow = {
  name: string;
  level: number;
  confidence: number;
  evidenceCount: number;
  category: string;
  status: "confirmed" | "supported" | "weak" | "pending";
};

export type CapabilityCard = {
  id: string;
  name: string;
  category: string;
  action: string;
  environment: string;
  evidenceIds: string[];
  status: "已确认" | "证据支持" | "自报" | "待补证据";
};

export type TimelinePoint = {
  id: string;
  label: string;
  sourceType: string;
  createdAt: string;
  preview: string;
  claimStrength?: string;
};

export type ScoreBreakdown = {
  required: number;
  preferred: number;
  strong: number;
  partial: number;
  gap: number;
  total: number;
  note: string;
};

const WEAK_CONFIDENCE = 0.7;

export function buildSkillMatrix(profile: Profile | null): SkillMatrixRow[] {
  if (!profile) return [];
  return profile.items
    .filter((item) => item.category === "skill")
    .map((item) => ({
      name: item.name,
      level: item.level,
      confidence: item.confidence,
      evidenceCount: item.evidence_ids.length,
      category: item.category,
      status: itemStatus(item),
    }))
    .sort((a, b) => b.confidence - a.confidence || b.level - a.level);
}

function itemStatus(item: ProfileItem): SkillMatrixRow["status"] {
  if (item.details?.source === "confirmed_user_update") return "confirmed";
  if (!item.evidence_ids.length) return "pending";
  if (item.evidence_ids.length === 1 || item.confidence < WEAK_CONFIDENCE) return "weak";
  return "supported";
}

export function buildCapabilityCards(
  profile: Profile | null, evidence: EvidenceItem[],
): CapabilityCard[] {
  if (!profile) return [];
  const byId = new Map(evidence.map((item) => [item.id, item]));
  return profile.items.map((item) => {
    const first = item.evidence_ids.map((id) => byId.get(id)).find(Boolean);
    const metadata = first?.source_metadata ?? {};
    const isPreference = metadata.claim_strength === "preference_signal";
    return {
      id: item.id,
      name: item.name,
      category: item.category,
      action: item.name,
      environment: typeof metadata.environment === "string" ? metadata.environment : "未提供（请结合原文核对）",
      evidenceIds: item.evidence_ids,
      status: itemStatus(item) === "confirmed" ? "已确认"
        : itemStatus(item) === "pending" ? "待补证据"
        : isPreference ? "自报" : "证据支持",
    };
  });
}

export function buildEvidenceTimeline(evidence: EvidenceItem[]): TimelinePoint[] {
  return [...evidence]
    .sort((a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""))
    .map((item) => {
      const metadata = item.source_metadata ?? {};
      return {
        id: item.id,
        label: item.source_name || item.source_type,
        sourceType: item.source_type,
        createdAt: item.created_at ?? "",
        preview: item.content.slice(0, 160),
        claimStrength: typeof metadata.claim_strength === "string"
          ? metadata.claim_strength : undefined,
      };
    });
}

export function buildScoreBreakdown(analysis: JobAnalysis | null): ScoreBreakdown {
  if (!analysis) {
    return { required: 0, preferred: 0, strong: 0, partial: 0, gap: 0, total: 0,
      note: "完成岗位分析后显示分数构成；规则分不是录用概率。" };
  }
  const matches = analysis.matches ?? [];
  const count = (key: "required" | "preferred") =>
    matches.filter((item) => item.priority === key).length;
  const statusCount = (key: "strong" | "partial" | "gap") =>
    matches.filter((item) => item.status === key).length;
  return {
    required: count("required"),
    preferred: count("preferred"),
    strong: statusCount("strong"),
    partial: statusCount("partial"),
    gap: statusCount("gap"),
    total: matches.length,
    note: "必需项权重 1.0、加分项 0.5；strong=1.0、partial=0.65、gap=0。规则分不是录用概率。",
  };
}

export function buildCategoryRadar(profile: Profile | null): Array<{ category: string; count: number }> {
  if (!profile) return [];
  const map = new Map<string, number>();
  for (const item of profile.items) map.set(item.category, (map.get(item.category) ?? 0) + 1);
  return [...map.entries()].map(([category, count]) => ({ category, count }));
}
