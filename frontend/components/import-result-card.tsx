"use client";

import { useState } from "react";
import type { EvidenceItem } from "@/lib/api";

export type ImportResult = {
  label: string;
  count: number;
  parseStatus?: string | null;
  readableCount?: number;
  ocrPendingCount?: number;
  duplicateCount?: number;
  warnings?: string[];
  evidenceIds?: string[];
  items?: EvidenceItem[];
  notice?: string;
};

type Props = {
  result: ImportResult;
  onDismiss?: () => void;
  onDeleteEvidence?: (id: string) => void;
};

const STATUS_LABEL: Record<string, string> = {
  parsed: "已读出文字",
  partial: "部分页面待 OCR",
  scanned: "只有扫描页",
  parsed_empty: "未读出文字",
};

/** HY4-A: a result card that says what was read, what is missing, and where to click. */
export function ImportResultCard({ result, onDismiss, onDeleteEvidence }: Props) {
  const [open, setOpen] = useState<string | null>(null);
  const status = result.parseStatus ?? (result.count > 0 ? "parsed" : "scanned");
  const statusLabel = STATUS_LABEL[status] ?? status;

  return (
    <div className="import-result" role="status" aria-live="polite">
      <div className="import-result-head">
        <div>
          <span>IMPORT RESULT</span>
          <h4>{result.label} · {statusLabel}</h4>
        </div>
        {onDismiss && (
          <button type="button" className="secondary" onClick={onDismiss}>收起</button>
        )}
      </div>
      <div className="import-result-stats">
        <div><b>{result.readableCount ?? result.count}</b><span>可读证据</span></div>
        <div><b>{result.ocrPendingCount ?? 0}</b><span>待 OCR 页</span></div>
        <div><b>{result.duplicateCount ?? 0}</b><span>重复跳过</span></div>
        <div><b>{result.items?.length ?? result.evidenceIds?.length ?? result.count}</b><span>可定位条目</span></div>
      </div>
      {result.notice && <p className="import-result-note">{result.notice}</p>}
      {result.warnings?.map((warning, index) => (
        <p className="import-result-warning" key={`${warning}-${index}`}>{warning}</p>
      ))}
      {status === "partial" && (
        <p className="import-result-warning">提示：任务成功不等于读出了文字。待 OCR 页面不会形成证据，可补充 OCR 能力或换用带文字层的 PDF。</p>
      )}
      {!!result.items?.length && (
        <details className="import-result-evidence">
          <summary>展开证据定位（{result.items.length} 条）</summary>
          <ul>
            {result.items.map((item) => {
              const metadata = item.source_metadata ?? {};
              const page = metadata.page ?? metadata.page_no;
              const claim = metadata.claim_strength as string | undefined;
              const key = item.id;
              return (
                <li key={key}>
                  <button type="button" onClick={() => setOpen(open === key ? null : key)}>
                    {item.source_name || item.source_type}
                    {page ? ` · 第 ${page} 页` : ""}
                    {claim === "preference_signal" ? " · 兴趣线索" : ""}
                  </button>
                  {open === key && (
                    <div>
                      <p>{item.content}</p>
                      <small>ID {item.id} · {item.source_type}</small>
                      {onDeleteEvidence && (
                        <button type="button" className="secondary" onClick={() => onDeleteEvidence(item.id)}>删除此证据</button>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </details>
      )}
      {!result.items?.length && !!result.evidenceIds?.length && (
        <p className="import-result-note">本次新增 {result.evidenceIds.length} 条证据，可在证据列表按 ID 核对原文。</p>
      )}
    </div>
  );
}
