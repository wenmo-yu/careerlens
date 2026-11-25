import type { AssessmentComputed, AssessmentScore } from "./api";

export const PAGE_SIZE = 8;

export function chunkItems<T>(items: T[], size = PAGE_SIZE): T[][] {
  if (size <= 0) return [items];
  const pages: T[][] = [];
  for (let index = 0; index < items.length; index += size) {
    pages.push(items.slice(index, index + size));
  }
  return pages.length ? pages : [[]];
}

export function answeredCount(ids: string[], answers: Record<string, number>): number {
  return ids.reduce((total, id) => (answers[id] ? total + 1 : total), 0);
}

export function progressPercent(answered: number, total: number): number {
  if (total <= 0) return 0;
  return Math.min(100, Math.round((answered / total) * 100));
}

export function minimumAnswers(total: number): number {
  return Math.ceil(total * 0.8);
}

export function missingIds(ids: string[], answers: Record<string, number>): string[] {
  return ids.filter((id) => !answers[id]);
}

export function resultHeadline(result: AssessmentComputed): string {
  if (result.scoring_type === "dichotomy") {
    return result.code && result.code !== "????" ? result.code : "接近中点";
  }
  if (result.scoring_type === "interest") {
    return result.code ? `兴趣代码 ${result.code}` : "暂无代码";
  }
  return "五因素画像";
}

export function scoreWidth(score: number | undefined): number {
  if (typeof score !== "number" || Number.isNaN(score)) return 0;
  return Math.max(0, Math.min(100, Math.round(score)));
}

export function strongestPole(row: AssessmentScore): { label: string; percent: number } {
  const poles = row.poles ?? [];
  if (!poles.length) return { label: row.label, percent: 0 };
  const best = poles.reduce((left, right) =>
    (right.percent ?? 0) > (left.percent ?? 0) ? right : left,
  );
  return { label: best.label, percent: scoreWidth(best.percent) };
}

export function bandTone(band: string | undefined): "high" | "mid" | "low" {
  if (!band) return "mid";
  if (band.startsWith("高") || band === "偏高") return "high";
  if (band.startsWith("低") || band === "偏低") return "low";
  return "mid";
}

export function completenessNote(result: AssessmentComputed): string {
  const answered = result.answered_count ?? 0;
  const total = result.item_count ?? 0;
  if (!total) return "";
  if (answered >= total) return `已完成 ${total}/${total} 题`;
  return `已回答 ${answered}/${total} 题（未答项不参与该维度计分）`;
}
