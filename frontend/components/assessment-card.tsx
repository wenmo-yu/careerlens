"use client";

import { useEffect, useState } from "react";
import {
  deleteAssessmentResult, getAssessmentInstrument, listAssessmentInstruments,
  listAssessmentResults, type AssessmentComputed, type AssessmentInstrument,
  type AssessmentInstrumentSummary, type AssessmentResult,
} from "@/lib/api";
import { resultHeadline } from "@/lib/assessment-format";
import { AssessmentInstrumentRunner } from "@/components/assessment-instrument-runner";
import { AssessmentProfileTools } from "@/components/assessment-profile-tools";
import { AssessmentQuickForm } from "@/components/assessment-quick-form";
import { AssessmentResultView } from "@/components/assessment-result-view";

const INTRO = "先问真实选择，3 分钟可跳过；完整量表另存，不写入事实画像。";

export function AssessmentCard({ userId, onNotice }: {
  userId: string;
  onNotice: (text: string) => void;
}) {
  const [instruments, setInstruments] = useState<AssessmentInstrumentSummary[]>([]);
  const [instrumentId, setInstrumentId] = useState("");
  const [instrument, setInstrument] = useState<AssessmentInstrument | null>(null);
  const [loadError, setLoadError] = useState("");
  const [results, setResults] = useState<AssessmentResult[]>([]);
  const [latest, setLatest] = useState<AssessmentComputed | null>(null);
  const [latestId, setLatestId] = useState<string | null>(null);

  useEffect(() => {
    void listAssessmentInstruments()
      .then((payload) => {
        setInstruments(payload.instruments);
        setInstrumentId((current) => current || payload.instruments[0]?.instrument_id || "");
      })
      .catch(() => setInstruments([]));
    void listAssessmentResults(userId)
      .then(setResults)
      .catch(() => setResults([]));
  }, [userId]);

  useEffect(() => {
    if (!instrumentId) return;
    let active = true;
    void getAssessmentInstrument(instrumentId)
      .then((payload) => {
        if (!active) return;
        setInstrument(payload);
        setLoadError("");
      })
      .catch(() => {
        if (active) setLoadError("量表加载失败，请稍后重试。");
      });
    return () => { active = false; };
  }, [instrumentId]);

  function refreshResults() {
    return listAssessmentResults(userId).then(setResults);
  }

  function handleSubmitted(id: string, result: AssessmentComputed) {
    setLatest(result);
    setLatestId(id);
    void refreshResults();
  }

  return (
    <section className="assessment-panel" aria-label="自我探索测评">
      <div className="assessment-head">
        <span>SELF EXPLORATION / 自陈信息</span>
        <h3>先问真实选择，再做可选测评</h3>
        <p>{INTRO}所有结果可跳过、重做、导出与删除；不改变技能覆盖与岗位匹配分。</p>
      </div>

      <AssessmentQuickForm userId={userId} onNotice={onNotice} onSaved={refreshResults} />

      <div className="instrument-picker">
        <div className="instrument-tabs" role="group" aria-label="完整量表">
          {instruments.map((row) => (
            <button key={row.instrument_id} type="button"
              aria-pressed={row.instrument_id === instrumentId}
              className={row.instrument_id === instrumentId ? "active" : ""}
              onClick={() => setInstrumentId(row.instrument_id)}>
              <strong>{row.title}</strong>
              <small>{row.item_count} 题 · 约 {row.estimated_minutes} 分钟</small>
            </button>
          ))}
        </div>
        {instrument && (
          <div className="instrument-meta">
            <p>{instrument.construct}</p>
            <small>{instrument.response_scale.prompt} · 许可：{instrument.license.license}</small>
          </div>
        )}
        {loadError && <p className="instrument-error">{loadError}</p>}
      </div>

      {instrument && (
        <AssessmentInstrumentRunner
          key={instrument.instrument_id}
          userId={userId}
          instrument={instrument}
          onNotice={onNotice}
          onSubmitted={handleSubmitted}
        />
      )}

      {latest && <AssessmentResultView result={latest} onNotice={onNotice} />}

      {!!results.length && (
        <details className="assessment-results">
          <summary>历史测评结果（{results.length}）</summary>
          {results.map((row) => {
            const stored = row.result as unknown as AssessmentComputed;
            const viewable = Boolean(stored?.scoring_type && stored?.scores);
            return (
              <div key={row.id}>
                <span>
                  {row.instrument} · {row.version} · {row.taken_at.slice(0, 10)} ·{" "}
                  {viewable ? resultHeadline(stored) : "旧版记录"}
                </span>
                {viewable && <button type="button" className="secondary"
                  onClick={() => { setLatest(stored); setLatestId(row.id); }}>查看</button>}
                <button type="button" className="secondary"
                  onClick={() => void deleteAssessmentResult(row.id, userId)
                    .then(() => {
                      if (latestId === row.id) { setLatest(null); setLatestId(null); }
                      return refreshResults();
                    })
                    .catch((error) => onNotice(
                      error instanceof Error ? error.message : "删除失败",
                    ))}>
                  删除
                </button>
              </div>
            );
          })}
        </details>
      )}

      <AssessmentProfileTools userId={userId} onNotice={onNotice} />
    </section>
  );
}
