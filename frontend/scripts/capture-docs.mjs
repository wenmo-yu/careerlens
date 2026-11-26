/**
 * Regenerate docs/assets screenshots against a running stack.
 *
 * Not a test: it drives the workbench through the real async flows and writes
 * the images referenced by docs/showcase.md. Run it after a visual change, then
 * commit docs/assets.
 *
 * Prerequisites: API on :8000 (demo provider, local retrieval), a worker, and
 * the built app on :3000. PW_CHANNEL=msedge reuses an installed browser.
 */
import { chromium } from "@playwright/test";
import { mkdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const BASE = process.env.E2E_BASE_URL ?? "http://127.0.0.1:3000";
const API = process.env.E2E_API_URL ?? "http://127.0.0.1:8000";
const OUT = fileURLToPath(new URL("../../docs/assets", import.meta.url));
const W = 1425;
const H = 891;
const USER = "docs-demo";

const STATEMENT =
  "我希望寻找 AI Agent 或 LLM 应用开发岗位。使用 Python、FastAPI 和 LangGraph 构建过多轮 Agent；" +
  "使用 Qdrant 实现 RAG 检索，并通过 Docker 完成服务部署。熟悉 PostgreSQL、React 和 TypeScript。" +
  "曾带 3 人小组完成一个知识库问答项目，负责架构设计与评测。";

const JD =
  "AI Agent 开发实习生：要求熟悉 Python、FastAPI、LangGraph、RAG、PostgreSQL；了解 Docker。" +
  "具备 Kubernetes 或 MCP 项目经验者优先。";

mkdirSync(OUT, { recursive: true });

const browser = await chromium.launch({ channel: process.env.PW_CHANNEL || undefined });
const context = await browser.newContext({
  viewport: { width: W, height: H },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
page.on("pageerror", (error) => console.error("[pageerror]", error.message));

async function shot(name) {
  // Let the toast clear itself before capturing.
  await page.locator(".notice").waitFor({ state: "detached", timeout: 8000 }).catch(() => undefined);
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 88 });
  console.log("saved", name);
}

/** Scroll a section to the top of the viewport, leaving room for the sticky nav. */
/** Element screenshot with the sticky chrome hidden, so nothing overlaps it. */
async function elementShot(selector, name) {
  const style = await page.addStyleTag({
    // Hide the sticky chrome and lift the scroll cap inside the skill matrix:
    // in the app it scrolls, but a document image should show every row.
    content:
      // Static, not display:none: the sticky bar is painted inside the element
      // screenshot otherwise, and removing it entirely shifts the layout.
      ".site-header { position: static !important; }" +
      ".workspace-steps-wrap, .workspace-subnav { display: none !important; }" +
      ".matrix-grid, .skill-list { max-height: none !important; overflow: visible !important; }",
  });
  const target = page.locator(selector);
  await target.scrollIntoViewIfNeeded();
  await page.waitForTimeout(900);
  await target.screenshot({ path: `${OUT}/${name}.jpg`, type: "jpeg", quality: 90 });
  await style.evaluate((node) => node.remove());
  console.log("saved", name);
}

async function at(selector) {
  // Absolute offset rather than scrollIntoView: with lazy layout the browser
  // sometimes treats the target as already partially visible and scrolls to
  // "nearest", which left the section half cut.
  const top = await page
    .locator(selector)
    .evaluate((el) => el.getBoundingClientRect().top + window.scrollY);
  await page.evaluate((y) => window.scrollTo(0, Math.max(0, y - 76)), top);
  await page.waitForTimeout(700);
}

/** Approve the pending run if any, wait for the worker, then open the result. */
async function finishRun(label) {
  const runs = page.locator("#runs");
  const approve = runs.getByRole("button", { name: "确认执行" });
  await approve.waitFor({ state: "visible", timeout: 4000 }).catch(() => undefined);
  if (await approve.isVisible()) await approve.click();
  await runs.getByRole("heading", { name: new RegExp(label) }).waitFor({ timeout: 90_000 });
  await page.waitForFunction(
    () => document.querySelector("#runs h3")?.textContent?.includes("已完成"),
    undefined,
    { timeout: 90_000 },
  );
  await runs.getByRole("button", { name: "打开结果" }).click();
  await page.waitForTimeout(800);
}

// ---- marketing pages ----
await page.goto(`${BASE}/`);
await page.waitForTimeout(1200);
await shot("overview");

await page.goto(`${BASE}/demo`);
await page.waitForTimeout(1200);
await shot("demo");
const table = page.locator(".demo-match-table, .demo-output-grid").first();
if (await table.count()) {
  await table.screenshot({ path: `${OUT}/demo-requirements.jpg`, type: "jpeg", quality: 90 });
  console.log("saved demo-requirements");
}

await page.goto(`${BASE}/architecture`);
await page.waitForTimeout(1200);
await shot("architecture");

await page.goto(`${BASE}/start`);
await page.waitForTimeout(1200);
await shot("start");

// ---- workbench: real data ----
await page.goto(`${BASE}/workspace`);
await page.getByLabel("用户标识").fill(USER);
await page.getByLabel("个人经历与自述").fill(STATEMENT);
await page.getByRole("button", { name: /导入并生成画像/ }).click();
await page.locator(".skill-list article").first().waitFor({ timeout: 60_000 });
await page.waitForTimeout(900);
await shot("workspace");

// Capture the grid itself. A viewport shot kept landing mid-card because the
// grid sits below the fold of a tall section.
await elementShot(".insight-grid", "profile");
await elementShot(".capability-grid", "capability-cards");
await elementShot(".profile-modes", "profile-modes");

// HY4-A: real HTML upload → background run → import result → expanded original.
const fixture = readFileSync(
  new URL("../../examples/tutorials/fixtures/hy4-lin-api.html", import.meta.url),
);
await page.locator('input[accept=".html,.htm,.zip"]').setInputFiles({
  name: "hy4-lin-api.html",
  mimeType: "text/html",
  buffer: fixture,
});
await finishRun("文档导入");
const importResult = page.locator("#profile .import-result");
await importResult.waitFor();
await elementShot(".import-result", "import-result");
await importResult.locator("summary").click();
await importResult.getByRole("button", { name: /hy4-lin-api\.html/ }).click();
await page.waitForTimeout(400);
await elementShot(".import-result", "evidence-card");

await page.getByLabel("岗位名称").fill("AI Agent 开发实习生");
await page.getByLabel("岗位描述").fill(JD);
await page.getByRole("button", { name: "分析匹配度" }).click();
await finishRun("岗位分析");
await at("#matching");
// The per-requirement table with its gap list is the point of this image; a
// full viewport here would only show the form and the score.
await elementShot(".score-card", "score-card");
await elementShot(".match-grid", "job-match");
await elementShot(".learning-board", "learning-board");
await elementShot(".course-catalog", "course-catalog");

await page.getByRole("button", { name: /查看相邻职业方向/ }).click();
await page.locator(".role-grid article").first().waitFor({ timeout: 60_000 });
await elementShot(".role-grid", "role-suggestions");

await page.getByRole("button", { name: /生成职业报告|生成新版本/ }).click();
await finishRun("职业报告");
await at("#report");
await shot("report");
await page.locator(".report-overview details").filter({ hasText: "证据目录" }).locator("summary").click();
await elementShot(".report-overview", "report-evidence");

await at("#copilot");
await page.getByPlaceholder("询问你的职业画像…").fill("为什么认为我适合 Agent 开发？");
await page.locator(".chat-input button").click();
await page.locator(".bubble").nth(1).waitFor({ timeout: 60_000 });
await page.waitForTimeout(1200);
// Copilot is the last section, so the viewport cannot scroll far enough to put
// its heading at the top; capture the chat panel itself instead.
await elementShot(".chat-shell", "copilot");
await page.locator(".evidence-stack details summary").first().click();
await page.waitForTimeout(400);
await elementShot(".chat-shell", "copilot-evidence");

// HY4-D: submit one synthetic self-report instrument, then show the saved result.
const instruments = await (await page.request.get(`${API}/api/v1/assessments/instruments`)).json();
const chosen = instruments.instruments.find((row) => row.instrument_id === "big_five_20")
  ?? instruments.instruments[0];
const detail = await (await page.request.get(
  `${API}/api/v1/assessments/instruments/${chosen.instrument_id}`,
)).json();
const answers = Object.fromEntries(detail.items.map((item) => [item.id, 4]));
const submitted = await page.request.post(
  `${API}/api/v1/assessments/instruments/${chosen.instrument_id}/submit`,
  { data: { user_id: USER, answers, consent: true } },
);
if (!submitted.ok()) throw new Error(`assessment submit failed: ${submitted.status()}`);
await page.reload();
// Workspace state resets to demo-user on reload; restore the capture account.
await page.getByLabel("用户标识").fill(USER);
await page.locator(".assessment-results summary").waitFor({ timeout: 30_000 });
await at("#assessment");
await page.locator(".assessment-results summary").click();
await page.locator(".assessment-results").getByRole("button", { name: "查看" }).last().click();
await page.waitForTimeout(700);
await elementShot(".assessment-panel", "assessment");

await at("#quality");
await page.getByRole("button", { name: "运行质量门禁" }).click();
await page.locator(".gate-strip").waitFor({ timeout: 90_000 });
await elementShot(".quality-grid", "quality-observability");

await at("#privacy");
// Demo mode records audit events for privacy operations; make one before the shot.
const exported = await page.request.get(`${API}/api/v1/privacy/${USER}/export`);
if (!exported.ok()) throw new Error(`privacy export failed: ${exported.status()}`);
await page.getByRole("button", { name: "刷新审计日志" }).click();
await page.locator(".audit-card div p").first().waitFor({ timeout: 30_000 });
await elementShot(".privacy-grid", "data-control");

await browser.close();
console.log("done");
