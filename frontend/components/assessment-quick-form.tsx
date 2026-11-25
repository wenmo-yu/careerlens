"use client";

import { useEffect, useState } from "react";
import {
  getAssessmentQuestions, submitAssessment, type AssessmentQuestion,
} from "@/lib/api";

/** Legacy five-question quick form; intentionally skippable and separate from packs. */
export function AssessmentQuickForm({ userId, onNotice, onSaved }: {
  userId: string;
  onNotice: (text: string) => void;
  onSaved: () => void | Promise<void>;
}) {
  const [questions, setQuestions] = useState<AssessmentQuestion[]>([]);
  const [answers, setAnswers] = useState<Record<string, number>>({});
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void getAssessmentQuestions("work_preference")
      .then((payload) => setQuestions(payload.questions))
      .catch(() => setQuestions([]));
  }, []);

  function submit() {
    setBusy(true);
    void submitAssessment("work_preference", {
      user_id: userId, instrument: "work_preference", answers, consent,
    }).then((result) => {
      onNotice(result.note ?? "已保存工作方式快测。");
      setConsent(false);
      return onSaved();
    }).catch((error) => onNotice(
      error instanceof Error ? error.message : "提交失败",
    )).finally(() => setBusy(false));
  }

  return (
    <details className="quick-preference">
      <summary>① 工作方式快测（{questions.length} 题，可跳过）</summary>
      <div className="assessment-questions">
        {questions.map((question) => (
          <label key={question.id}>
            <span>{question.text}</span>
            <input
              type="range" min={1} max={5} value={answers[question.id] ?? 3}
              onChange={(event) => setAnswers((current) => ({
                ...current, [question.id]: Number(event.target.value),
              }))}
            />
          </label>
        ))}
      </div>
      <label className="assessment-consent">
        <input type="checkbox" checked={consent}
          onChange={(event) => setConsent(event.target.checked)} />
        我确认这是自愿填写的自陈信息，可随时删除。
      </label>
      <button type="button" disabled={!consent || busy} onClick={submit}>
        {busy ? "保存中…" : "保存快测"}
      </button>
    </details>
  );
}
