import assert from "node:assert/strict";
import { mergeCapture } from "./collection.js";

const base = {
  format: "careerlens-browser-capture-v1",
  platform: "bilibili",
  kind: "liked",
  source_url: "https://space.bilibili.com/1",
  captured_at: "2026-10-25T00:00:00Z",
  items: [{ url: "https://www.bilibili.com/video/1", title: "A", text: "short" }],
};
const incoming = {
  ...base,
  captured_at: "2026-10-25T01:00:00Z",
  items: [
    { url: "https://www.bilibili.com/video/1", title: "A", text: "a longer description" },
    { url: "https://www.bilibili.com/video/2", title: "B", text: "new" },
  ],
};
const merged = mergeCapture(base, incoming);
assert.equal(merged.added, 1);
assert.equal(merged.capture.items.length, 2);
assert.equal(merged.capture.items[0].text, "a longer description");
assert.equal(merged.capture.captured_at, incoming.captured_at);
assert.equal(mergeCapture(base, incoming, 1).capture.items.length, 1);
assert.throws(() => mergeCapture(base, { ...incoming, kind: "following" }));
console.log("browser-helper collection tests passed");
