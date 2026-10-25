import assert from "node:assert/strict";
import { parseBrowserCaptureDraft } from "./browser-capture.ts";

const valid = {
  format: "careerlens-browser-capture-v1",
  platform: "weibo",
  kind: "favorite",
  source_url: "https://weibo.com/u/12345",
  captured_at: "2026-10-25T00:00:00Z",
  items: [{ url: "https://weibo.com/status/ABCDE", title: "Test", text: "Visible content" }],
};
assert.deepEqual(parseBrowserCaptureDraft(JSON.stringify(valid)), valid);
assert.equal(JSON.stringify(parseBrowserCaptureDraft(JSON.stringify({ ...valid, cookie: "secret", items: [{ ...valid.items[0], token: "secret" }] }))).includes("secret"), false);
assert.throws(() => parseBrowserCaptureDraft("{"), /JSON/);
assert.throws(() => parseBrowserCaptureDraft(JSON.stringify({ ...valid, platform: "other" })), /格式/);
assert.throws(() => parseBrowserCaptureDraft(JSON.stringify({ ...valid, items: [] })), /格式/);
assert.throws(() => parseBrowserCaptureDraft(JSON.stringify({ ...valid, items: [{ url: 1 }] })), /格式/);
console.log("browser capture preview tests passed");
