import { expect, test, type Page } from "@playwright/test";

/**
 * The one path every other feature depends on:
 * evidence in -> profile -> JD match -> versioned report.
 *
 * Assertions are about observable product behaviour (a profile row appears, a
 * score is a percentage, the report has a version), not internal class names,
 * so a visual refactor does not break the suite.
 *
 * Job analysis and report generation are background runs by design, so the test
 * drives the real confirmation flow instead of pretending it is synchronous.
 */

const STATEMENT =
  "我希望寻找 AI Agent 或 LLM 应用开发岗位。使用 Python、FastAPI 和 LangGraph 构建过多轮 Agent；" +
  "使用 Qdrant 实现 RAG 检索，并通过 Docker 完成服务部署。熟悉 PostgreSQL、React 和 TypeScript。";

const JD =
  "AI Agent 开发实习生：要求熟悉 Python、FastAPI、LangGraph、RAG、PostgreSQL；了解 Docker。" +
  "具备 Kubernetes 或 MCP 项目经验者优先。";

/** Approve the pending run, wait for the worker, then open its result. */
async function completeRun(page: Page, label: string) {
  const runs = page.locator("#runs");
  // Most operations queue straight away; some wait for an explicit approval.
  // Handle both instead of hard-coding one policy.
  const approve = runs.getByRole("button", { name: "确认执行" });
  await approve.waitFor({ state: "visible", timeout: 4_000 }).catch(() => undefined);
  if (await approve.isVisible()) await approve.click();
  await expect(runs.getByRole("heading", { name: new RegExp(label) })).toContainText(
    "已完成",
    { timeout: 90_000 },
  );
  await runs.getByRole("button", { name: "打开结果" }).click();
}

test.describe("workbench happy path", () => {
  test.beforeEach(async ({ page }) => {
    page.on("pageerror", (error) => {
      throw new Error(`uncaught page error: ${error.message}`);
    });
  });

  test("evidence becomes a profile, a match score and a report", async ({ page }) => {
    await page.goto("/workspace");
    await expect(page.getByRole("heading", { name: "职业工作台" })).toBeVisible();

    // A fresh user id per run keeps tasks and profiles isolated between runs.
    await page.getByLabel("用户标识").fill(`e2e-${Date.now()}`);
    await page.getByLabel("个人经历与自述").fill(STATEMENT);
    await page.getByRole("button", { name: /导入并生成画像/ }).click();

    // A skill row appears, with a level scale rather than a bare percentage.
    const firstSkill = page.locator(".skill-list article").first();
    await expect(firstSkill).toBeVisible();
    await expect(firstSkill.locator(".level-scale i.on")).not.toHaveCount(0);
    await expect(page.locator(".profile-panel")).toContainText("条证据");

    // Profile insights replace the empty placeholder.
    await expect(page.locator(".insight-grid")).toBeVisible();
    await expect(page.getByText("导入第一段经历后，这里会生成画像洞察")).toHaveCount(0);

    // Job match runs in the background: approve it, then open the result.
    await page.getByLabel("岗位名称").fill("AI Agent 开发实习生");
    await page.getByLabel("岗位描述").fill(JD);
    await page.getByRole("button", { name: "分析匹配度" }).click();
    await completeRun(page, "岗位分析");

    await expect(page.locator(".score-card strong")).toContainText("%");
    await expect(page.locator(".score-disclaimer")).toContainText("不是录用概率");
    await expect(page.locator(".match-table .table-row").nth(1)).toBeVisible();

    // Report, same async flow.
    await page.getByRole("button", { name: /生成职业报告|生成新版本/ }).click();
    await completeRun(page, "职业报告");
    await expect(page.locator(".report-meta")).toContainText("VERSION");
    await expect(page.locator(".report-preview article")).toHaveCount(4);
    await expect(page.locator(".report-preview")).toContainText("个人职业画像");
  });

  test("empty states tell the user what to do next", async ({ page }) => {
    await page.goto("/workspace");
    const copilotEmpty = page.locator("#copilot .empty").first();
    const seed = copilotEmpty.getByRole("button", { name: /用这个问题开始/ });
    await expect(seed).toBeVisible();
    await seed.click();
    await expect(page.getByPlaceholder("询问你的职业画像…")).toHaveValue(/Agent/);
  });
});

test("marketing pages reach the workbench", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1 })).toContainText("职业选择");
  await page.getByRole("link", { name: /进入工作台/ }).first().click();
  await expect(page).toHaveURL(/\/workspace$/);
});

test("unknown routes render the 404 page instead of a blank screen", async ({ page }) => {
  const response = await page.goto("/this-route-does-not-exist");
  expect(response?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "没有这个页面" })).toBeVisible();
});
