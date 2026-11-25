"use client";

import type { AssessmentComputed } from "@/lib/api";
import {
  bandTone, completenessNote, resultHeadline, scoreWidth, strongestPole,
} from "@/lib/assessment-format";

/** Read-only rendering of one stored result; no scoring happens here. */
export function AssessmentResultView({ result, onNotice }: {
  result: AssessmentComputed;
  onNotice: (text: string) => void;
}) {
  const license = result.license;
  return (
    <section className="assessment-result" aria-label="本次测评结果">
      <div className="result-head">
        <span>RESULT / 自陈结果</span>
        <h4>{result.instrument_title ?? "测评结果"}</h4>
        <strong className="result-code">{resultHeadline(result)}</strong>
        <small>{result.code_label ?? ""} · {completenessNote(result)}</small>
      </div>

      {result.scoring_type === "dichotomy" && (
        <div className="dichotomy-grid">
          {result.scores.map((row) => {
            const top = strongestPole(row);
            return (
              <article key={row.dimension ?? row.label}>
                <header>
                  <strong>{row.label}</strong>
                  <span>{row.letter ?? "?"} · {top.label} {top.percent}%</span>
                </header>
                <div className="pole-bars">
                  {(row.poles ?? []).map((pole) => (
                    <div key={pole.key} className="pole-row">
                      <span>{pole.label}</span>
                      <div className="bar"><i style={{ width: `${scoreWidth(pole.percent)}%` }} /></div>
                      <b>{scoreWidth(pole.percent)}%</b>
                    </div>
                  ))}
                </div>
                {row.balanced && <small className="balanced">接近中点：不宜当作固定偏好</small>}
              </article>
            );
          })}
        </div>
      )}

      {result.scoring_type === "interest" && (
        <div className="interest-grid">
          {result.scores.map((row) => (
            <div key={row.key ?? row.label} className="score-row">
              <span>{row.key} · {row.label}</span>
              <div className="bar"><i style={{ width: `${scoreWidth(row.score)}%` }} /></div>
              <b>{scoreWidth(row.score)}</b>
            </div>
          ))}
          {result.consistency && (
            <p className="result-note">代码一致性：{result.consistency.level} · {result.consistency.note}</p>
          )}
          {typeof result.differentiation === "number" && (
            <p className="result-note">分化度 {result.differentiation}：越高表示偏好越集中。</p>
          )}
          {!!result.role_hints?.length && (
            <div className="role-hints">
              <h5>方向线索（本地教学目录，不是市场结论）</h5>
              {result.role_hints.map((hint) => (
                <article key={hint.role_id}>
                  <strong>{hint.name}</strong>
                  <span>{hint.match} 分 · {hint.riasec.join(" / ")}</span>
                  <p>{hint.reason}</p>
                </article>
              ))}
            </div>
          )}
        </div>
      )}

      {result.scoring_type === "trait" && (
        <div className="trait-grid">
          {result.scores.map((row) => (
            <article key={row.key ?? row.label} className={bandTone(row.band)}>
              <header>
                <strong>{row.label}</strong>
                <span>{scoreWidth(row.score)} · {row.band}</span>
              </header>
              <div className="bar"><i style={{ width: `${scoreWidth(row.score)}%` }} /></div>
              <p>{row.description}</p>
            </article>
          ))}
        </div>
      )}

      {!!result.hints?.length && (
        <ul className="result-hints">
          {result.hints.map((hint) => <li key={hint}>{hint}</li>)}
        </ul>
      )}

      <div className="result-methods">
        <p>{result.methodology}</p>
        <p className="instrument-disclaimer">{result.disclaimer}</p>
        {license && (
          <details className="assessment-license">
            <summary>许可与未采用的题库</summary>
            <p>{license.attribution}</p>
            <ul>{license.not_used.map((row) => <li key={row}>{row}</li>)}</ul>
          </details>
        )}
        <button type="button" className="secondary"
          onClick={() => onNotice("结果只是自陈探索；如需引用，请连同方法说明与免责声明一起引用。")}>
          引用时注意什么
        </button>
      </div>
    </section>
  );
}
