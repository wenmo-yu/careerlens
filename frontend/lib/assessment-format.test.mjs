import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  answeredCount, bandTone, chunkItems, completenessNote, minimumAnswers,
  missingIds, progressPercent, resultHeadline, scoreWidth, strongestPole,
} from "./assessment-format.ts";

describe("assessment formatting", () => {
  it("chunks 32 items into four pages of eight", () => {
    const items = Array.from({ length: 32 }, (_, index) => `q${index}`);
    const pages = chunkItems(items);
    assert.equal(pages.length, 4);
    assert.equal(pages[0].length, 8);
    assert.equal(pages[3][7], "q31");
    assert.deepEqual(chunkItems([], 8), [[]]);
  });

  it("counts answers and enforces the 80% floor", () => {
    const ids = ["a", "b", "c", "d", "e"];
    assert.equal(answeredCount(ids, { a: 1, c: 5 }), 2);
    assert.equal(progressPercent(2, 5), 40);
    assert.equal(minimumAnswers(32), 26);
    assert.equal(minimumAnswers(48), 39);
    assert.deepEqual(missingIds(ids, { a: 1 }), ["b", "c", "d", "e"]);
  });

  it("headlines each scoring type honestly", () => {
    assert.equal(resultHeadline({ scoring_type: "dichotomy", code: "INTJ" }), "INTJ");
    assert.equal(resultHeadline({ scoring_type: "dichotomy", code: "????" }), "接近中点");
    assert.equal(resultHeadline({ scoring_type: "interest", code: "IRA" }), "兴趣代码 IRA");
    assert.equal(resultHeadline({ scoring_type: "trait", code: null }), "五因素画像");
  });

  it("clamps scores and picks the stronger pole", () => {
    assert.equal(scoreWidth(undefined), 0);
    assert.equal(scoreWidth(120), 100);
    assert.equal(scoreWidth(-5), 0);
    assert.equal(scoreWidth(62.4), 62);
    const row = {
      label: "精力方向",
      poles: [
        { key: "E", label: "外倾", percent: 25 },
        { key: "I", label: "内倾", percent: 75 },
      ],
    };
    assert.deepEqual(strongestPole(row), { label: "内倾", percent: 75 });
  });

  it("maps bands to tones and describes completeness", () => {
    assert.equal(bandTone("高"), "high");
    assert.equal(bandTone("偏低"), "low");
    assert.equal(bandTone("中"), "mid");
    assert.equal(completenessNote({ answered_count: 32, item_count: 32 }), "已完成 32/32 题");
    assert.equal(
      completenessNote({ answered_count: 30, item_count: 32 }),
      "已回答 30/32 题（未答项不参与该维度计分）",
    );
  });
});
