import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildCapabilityCards, buildCategoryRadar, buildEvidenceTimeline,
  buildScoreBreakdown, buildSkillMatrix,
} from "./profile-views.ts";

const profile = {
  user_id: "u1",
  count: 3,
  items: [
    { id: "p1", category: "skill", name: "Python", level: 4, confidence: 0.9, evidence_ids: ["e1", "e2"], details: {} },
    { id: "p2", category: "skill", name: "FastAPI", level: 2, confidence: 0.6, evidence_ids: ["e1"], details: {} },
    { id: "p3", category: "target_role", name: "Agent 开发", level: 3, confidence: 0.8, evidence_ids: [], details: { source: "confirmed_user_update" } },
  ],
};

const evidence = [
  { id: "e1", source_name: "cv.pdf", source_type: "resume", content: "熟悉 Python", created_at: "2026-11-20T10:00:00Z", source_metadata: { page: 2 } },
  { id: "e2", source_name: "capture.json", source_type: "bilibili_browser", content: "收藏了教程", created_at: "2026-11-21T10:00:00Z", source_metadata: { claim_strength: "preference_signal" } },
];

describe("profile views", () => {
  it("skill matrix keeps only skills and marks weak/supported", () => {
    const rows = buildSkillMatrix(profile);
    assert.deepEqual(rows.map((r) => r.name), ["Python", "FastAPI"]);
    assert.equal(rows[0].status, "supported");
    assert.equal(rows[1].status, "weak");
  });

  it("capability cards carry action, environment, evidence and status", () => {
    const cards = buildCapabilityCards(profile, evidence);
    assert.equal(cards[0].action, "Python");
    assert.equal(cards[0].environment, "未提供（请结合原文核对）");
    assert.equal(cards[2].status, "已确认");
  });

  it("timeline newest first and labels preference signals", () => {
    const rows = buildEvidenceTimeline(evidence);
    assert.equal(rows[0].id, "e2");
    assert.equal(rows[0].claimStrength, "preference_signal");
  });

  it("category radar counts every category", () => {
    assert.deepEqual(buildCategoryRadar(profile), [
      { category: "skill", count: 2 }, { category: "target_role", count: 1 },
    ]);
  });

  it("score breakdown splits required/preferred and statuses", () => {
    const analysis = {
      matches: [
        { name: "Python", priority: "required", status: "strong", evidence_ids: ["e1"] },
        { name: "K8s", priority: "required", status: "gap", evidence_ids: [] },
        { name: "Docker", priority: "preferred", status: "partial", evidence_ids: ["e2"] },
      ],
    };
    const data = buildScoreBreakdown(analysis);
    assert.deepEqual([data.required, data.preferred, data.strong, data.partial, data.gap], [2, 1, 1, 1, 1]);
    assert.match(data.note, /不是录用概率/);
  });
});
