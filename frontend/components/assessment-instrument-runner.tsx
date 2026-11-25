"use client";

import { useMemo, useState } from "react";
import {
  submitInstrumentAssessment, type AssessmentComputed, type AssessmentInstrument,
} from "@/lib/api";
import {
  PAGE_SIZE, answeredCount, chunkItems, minimumAnswers, missingIds,
  progressPercent,
} from "@/lib/assessment-format";

/** Paged runner for one versioned item pack. Remount with a key to reset it. */
export function AssessmentInstrumentRunner({ userId, instrument, onNotice, onSubmitted }: {
  userId: string;
  instrument: AssessmentInstrument;
  onNotice: (text: string) => void;
  onSubmitted: (id: string, result: AssessmentComputed) => void;
}) {
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [page, setPage] = useState(0);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);

  const pages = useMemo(() => chunkItems(instrument.items), [instrument]);
  const ids = useMemo(() => instrument.items.map((item) => item.id), [instrument]);
  const answered = answeredCount(ids, answers);
  const total = ids.length;
  const minimum = minimumAnswers(total);
  const missing = missingIds(ids, answers).length;
  const progress = progressPercent(answered, total);
  const currentPage = pages[Math.min(page, pages.length - 1)] ?? [];

  function submit() {
    if (!consent) {
      onNotice("请先确认这是自愿填写的自陈信息。");
      return;
    }
    if (answered < minimum) {
      onNotice(`至少需要回答 ${minimum}/${total} 题，当前还差 ${minimum - answered} 题。`);
      return;
    }
    setBusy(true);
    void submitInstrumentAssessment(instrument.instrument_id, {
      user_id: userId, answers, consent,
    }).then((payload) => {
      onSubmitted(payload.id, payload.result);
      onNotice(payload.note);
      setConsent(false);
    }).catch((error) => onNotice(
      error instanceof Error ? error.message : "提交失败",
    )).finally(() => setBusy(false));
  }

  return (
    <div className="instrument-body">
      <div className="instrument-progress">
        <div className="progress-track"><i style={{ width: `${progress}%` }} /></div>
        <span>{answered}/{total} 题 · {progress}% · 至少 {minimum} 题可提交</span>
      </div>

      <ol className="instrument-items" start={page * PAGE_SIZE + 1}>
        {currentPage.map((item) => (
          <li key={item.id}>
            <p>{item.text}</p>
            <div className="likert" role="group" aria-label={item.text}>
              {instrument.response_scale.labels.map((label, index) => {
                const value = instrument.response_scale.min + index;
                return (
                  <button key={value} type="button"
                    className={answers[item.id] === value ? "active" : ""}
                    aria-pressed={answers[item.id] === value}
                    onClick={() => setAnswers((current) => ({ ...current, [item.id]: value }))}>
                    <b>{value}</b><small>{label}</small>
                  </button>
                );
              })}
            </div>
          </li>
        ))}
      </ol>

      <div className="instrument-pager">
        <button type="button" className="secondary" disabled={page === 0}
          onClick={() => setPage((current) => Math.max(0, current - 1))}>上一页</button>
        <span>第 {Math.min(page, pages.length - 1) + 1} / {pages.length} 页 · 未答 {missing} 题</span>
        <button type="button" className="secondary" disabled={page >= pages.length - 1}
          onClick={() => setPage((current) => Math.min(pages.length - 1, current + 1))}>下一页</button>
      </div>

      <label className="assessment-consent">
        <input type="checkbox" checked={consent}
          onChange={(event) => setConsent(event.target.checked)} />
        我确认这是自愿填写的自陈信息，可随时删除；理解它不是能力事实。
      </label>
      <div className="instrument-actions">
        <button type="button" disabled={busy} onClick={submit}>
          {busy ? "计分中…" : "提交并查看结果"}
        </button>
        <button type="button" className="secondary" onClick={() => {
          setAnswers({}); setPage(0);
        }}>清空重答</button>
      </div>

      <p className="instrument-disclaimer">{instrument.disclaimer}</p>
      <details className="assessment-license">
        <summary>题目来源与没做的事</summary>
        <p>{instrument.license.attribution}</p>
        <ul>{instrument.license.not_used.map((row) => <li key={row}>{row}</li>)}</ul>
        <small>{instrument.license.items} · {instrument.license.license} · 版本 {instrument.version}</small>
      </details>
    </div>
  );
}
