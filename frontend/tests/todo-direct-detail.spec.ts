import { expect, test } from "@playwright/test";
test("列表展示详情信息，点击直接编辑，旧详情链接兼容", async ({ page }) => {
  let todo = {
    id: "todo-1",
    title: "买牛奶",
    description: "购买两盒无糖牛奶",
    due_date: "2026-09-16",
    due_time: "09:00",
    due_at: "2026-09-16T01:00:00Z",
    status: "ongoing",
    is_overdue: true,
    timezone: "Asia/Shanghai",
    source: "app",
    assignee_id: "demo",
    completed_at: null,
    created_at: "2026-09-15T00:00:00Z",
    updated_at: "2026-09-15T00:00:00Z",
  };
  await page.route("**/api/**", async (route) => {
    const req = route.request(),
      path = new URL(req.url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/todos/todo-1") {
      if (req.method() === "PATCH")
        todo = { ...todo, ...req.postDataJSON(), updated_at: "2026-09-18T00:00:00Z" };
      return route.fulfill({ json: todo });
    }
    return route.fulfill({
      json: { items: [todo], next_cursor: null, server_time: "2026-09-18T04:00:00Z" },
    });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/todos");
    const row = page.locator(".todo-row");
    await expect(row).toContainText("购买两盒无糖牛奶");
    await expect(row).toContainText("2026年9月16日 09:00");
    await expect(row).toContainText("已逾期");
    await expect(row).toContainText("进行中 · 应用内");
    await page.screenshot({ path: `/tmp/todo-list-details-${width}.png`, fullPage: true });
    await row.getByRole("link").click();
    await expect(page).toHaveURL(/\/todos\/todo-1\/edit$/);
    await expect(page.getByRole("heading", { name: "待办详情", exact: true })).toBeVisible();
    await expect(page.getByLabel("标题", { exact: true })).toHaveValue("买牛奶");
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await expect(page).toHaveURL(/\/todos$/);
  }
  await page.goto("/todos/todo-1");
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("买牛奶");
  await page.getByLabel("标题", { exact: true }).fill("买酸奶");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page).toHaveURL(/\/todos$/);
  await expect(page.locator(".todo-row")).toContainText("买酸奶");
});
