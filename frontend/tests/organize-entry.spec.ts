import { expect, test } from "@playwright/test";

test("功能中心可打开计划回顾和随手记转待办", async ({ page }, testInfo) => {
  await page.clock.install({ time: new Date("2026-09-17T04:00:00Z") });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      json = {
        id: "entry-user",
        email: "demo@example.com",
        nickname: "测试",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/planning/review") {
      const params = new URL(route.request().url()).searchParams;
      expect(params.get("date_from")).toBe("2026-09-14");
      expect(params.get("date_to")).toBe("2026-09-20");
      json = {
        summary: { completed_todos: 1, ongoing_todos: 1, events: 1, open_checklist_items: 0 },
        details: {
          completed: [{ id: "done-1", title: "完成的事项" }],
          ongoing: [{ id: "due-1", title: "期间到期事项" }],
          events: [{ id: "event-1", title: "期间会议" }],
        },
        organize: { overdue: [], unscheduled: [], conflicts: [] },
      };
    }
    await route.fulfill({ json });
  });
  await page.goto("/features");
  await expect(page.locator('a[href="/review"]')).toBeVisible();
  await expect(page.locator('a[href="/daily-dump"]')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("features-organize.png"), fullPage: true });
  await page.locator('a[href="/review"]').click();
  await expect(page).toHaveURL(/\/review$/);
  await expect(page.getByRole("button", { name: "开始日期" })).toHaveText("2026/09/14");
  await expect(page.getByRole("button", { name: "结束日期" })).toHaveText("2026/09/20");
  await expect(page.getByRole("heading", { name: "计划回顾" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "日程冲突" })).toBeVisible();
  await expect(page.getByRole("link", { name: "期间到期事项" })).toHaveAttribute(
    "href",
    "/todos/due-1",
  );
  await expect(page.getByRole("link", { name: "期间会议" })).toHaveAttribute(
    "href",
    "/calendar/event-1/edit",
  );
  await expect(page.locator('main a[href="/daily-dump"]')).toHaveCount(0);
  await expect(page.getByText("清单项", { exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "1 已完成待办" }).click();
  await expect(page).toHaveURL(/#review-completed$/);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.screenshot({ path: testInfo.outputPath("review-390.png"), fullPage: true });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.screenshot({ path: testInfo.outputPath("review-320.png"), fullPage: true });
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true);
  await page.goto("/features");
  await page.locator('a[href="/review"]').click();
  await expect(page.locator('nav a[href="/features"]')).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(/\/features$/);
  await page.locator('a[href="/daily-dump"]').click();
  await expect(page).toHaveURL(/\/daily-dump$/);
  await expect(page.getByRole("heading", { name: "随手记转待办" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "随手记" })).toBeVisible();
  await expect(page.locator('nav a[href="/features"]')).toHaveAttribute("aria-current", "page");
});

test("随手记完成后可继续整理新一轮", async ({ page }, testInfo) => {
  const drafts: string[] = [];
  const commits: string[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "entry-user", email: "demo@example.com", timezone: "Asia/Shanghai" };
    if (path === "/api/workflows/daily-dumps") {
      const { text } = route.request().postDataJSON();
      drafts.push(text);
      json = {
        id: `draft-${drafts.length}`,
        candidates: [{ id: "candidate", type: "todo", title: text, selected: true }],
      };
    }
    if (path.endsWith("/commit")) {
      commits.push(path);
      json = { created: [{ id: "todo-1", title: drafts.at(-1), url: "/todos/todo-1" }] };
    }
    await route.fulfill({ json });
  });
  await page.goto("/daily-dump");
  await page.getByRole("textbox", { name: "随手记" }).fill("预约牙医");
  await page.getByRole("button", { name: "生成待办候选" }).click();
  await page.getByRole("button", { name: "确认写入" }).click();
  await expect(page.getByRole("link", { name: "预约牙医" })).toBeVisible();
  await expect(page.getByRole("button", { name: "继续整理" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("daily-dump-complete.png"), fullPage: true });
  await page.getByRole("button", { name: "继续整理" }).click();
  await expect(page.getByRole("textbox", { name: "随手记" })).toHaveValue("");
  await expect(page.getByRole("button", { name: "生成待办候选" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "整理完成" })).toHaveCount(0);
  expect(commits).toHaveLength(1);
  await page.getByRole("textbox", { name: "随手记" }).fill("买猫粮");
  await page.getByRole("button", { name: "生成待办候选" }).click();
  await page.getByRole("button", { name: "确认写入" }).click();
  await expect(page.getByRole("link", { name: "买猫粮" })).toBeVisible();
  expect(commits).toEqual([
    "/api/workflows/daily-dumps/draft-1/commit",
    "/api/workflows/daily-dumps/draft-2/commit",
  ]);
});
