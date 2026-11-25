"use client";

import { useEffect, useState } from "react";
import {
  getConstraints, getDimensions, putConstraint, putDimension, type DimensionView,
} from "@/lib/api";

/** Constraints and custom dimensions: display/filter only, never scoring. */
export function AssessmentProfileTools({ userId, onNotice }: {
  userId: string;
  onNotice: (text: string) => void;
}) {
  const [dimensions, setDimensions] = useState<DimensionView[]>([]);
  const [constraints, setConstraints] = useState<Array<{
    kind: string; value: string; strength: number;
  }>>([]);
  const [constraintText, setConstraintText] = useState("");
  const [dimensionKey, setDimensionKey] = useState("");
  const [dimensionLabel, setDimensionLabel] = useState("");

  function refresh() {
    return Promise.all([getDimensions(userId), getConstraints(userId)])
      .then(([allDimensions, allConstraints]) => {
        setDimensions(allDimensions.dimensions);
        setConstraints(allConstraints);
      });
  }

  useEffect(() => {
    void Promise.all([getDimensions(userId), getConstraints(userId)])
      .then(([allDimensions, allConstraints]) => {
        setDimensions(allDimensions.dimensions);
        setConstraints(allConstraints);
      })
      .catch(() => undefined);
  }, [userId]);

  return (
    <>
      <div className="assessment-constraints">
        <h4>约束条件（自陈，用于过滤不参与评分）</h4>
        <label>新增约束<input value={constraintText} placeholder="例如：只考虑本地或远程"
          onChange={(event) => setConstraintText(event.target.value)} /></label>
        <button type="button" disabled={!constraintText.trim()} onClick={() => void putConstraint({
          user_id: userId, kind: "general", value: constraintText.trim(), strength: 3,
        }).then(() => { setConstraintText(""); return refresh(); })
          .catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"))}>
          保存约束
        </button>
        <ul>{constraints.map((row) => <li key={row.kind}>{row.kind} · {row.value}（强度 {row.strength}）</li>)}</ul>
      </div>

      <div className="assessment-dimensions">
        <h4>自定义画像维度（开关只影响展示）</h4>
        <div className="dimension-form">
          <input value={dimensionKey} placeholder="key，如 values_growth"
            onChange={(event) => setDimensionKey(event.target.value)} />
          <input value={dimensionLabel} placeholder="显示名称"
            onChange={(event) => setDimensionLabel(event.target.value)} />
          <button type="button" disabled={!dimensionKey.trim() || !dimensionLabel.trim()}
            onClick={() => void putDimension(userId, {
              user_id: userId, key: dimensionKey.trim(), label: dimensionLabel.trim(),
              enabled: true, value: {},
            }).then(() => { setDimensionKey(""); setDimensionLabel(""); return refresh(); })
              .catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"))}>
            添加维度
          </button>
        </div>
        <ul>{dimensions.map((row) => <li key={row.key}>
          <strong>{row.label}</strong> · {row.key}
          <button type="button" className="secondary" onClick={() => void putDimension(userId, {
            user_id: userId, key: row.key, label: row.label, description: row.description,
            enabled: !row.enabled, value: row.value, evidence_ids: row.evidence_ids,
          }).then(() => refresh())
            .catch((error) => onNotice(error instanceof Error ? error.message : "保存失败"))}>
            {row.enabled ? "停用" : "启用"}
          </button>
        </li>)}</ul>
      </div>
    </>
  );
}
