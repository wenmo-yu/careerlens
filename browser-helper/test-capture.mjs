import assert from "node:assert/strict";
import { capturePage } from "./capture.js";

const cases = [
  ["www.bilibili.com", "/video/BV1CAREER", "bilibili"],
  ["weibo.com", "/status/CAREER123", "weibo"],
  ["weibo.com", "/1234567890/AbCde123", "weibo"],
  ["www.douyin.com", "/video/123456", "douyin"],
];

for (const [hostname, pathname, platform] of cases) {
  const url = `https://${hostname}${pathname}`;
  globalThis.location = { hostname, pathname, origin: `https://${hostname}`, href: `${url}?token=secret` };
  const card = { innerText: "使用 Python 制作项目记录", textContent: "使用 Python 制作项目记录" };
  const anchor = {
    textContent: "项目记录",
    parentElement: card,
    getAttribute(name) { return name === "href" ? url : null; },
    closest() { return card; },
  };
  globalThis.document = { querySelectorAll() { return [anchor]; } };
  globalThis.getComputedStyle = () => ({ display: "block", visibility: "visible" });
  const result = capturePage("liked");
  assert.equal(result.platform, platform);
  assert.equal(result.items.length, 1);
  assert.equal(result.source_url, url);
  assert.equal(result.items[0].url, url);
  assert.equal(JSON.stringify(result).includes("secret"), false);
}

console.log("browser-helper capture tests passed");
