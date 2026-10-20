import { expect, test } from "@playwright/test";

test("调整冲突日程使用应用内确认，取消不写入", async ({ page }, testInfo) => {
  let writes = 0;
  page.on("dialog", () => {
    throw new Error("不能使用系统确认弹窗");
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      json = {
        id: "user-1",
        nickname: "测试",
        email: "demo@example.com",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/planning/review")
      json = {
        summary: { completed_todos: 0, ongoing_todos: 0, events: 2 },
        details: { completed: [], ongoing: [], events: [] },
        organize: {
          overdue: [],
          unscheduled: [],
          conflicts: [{ left: { id: "a", title: "开会" }, right: { id: "b", title: "看牙医" } }],
        },
      };
    if (path.endsWith("/suggestions"))
      json = {
        suggestions: [{ starts_at: "2026-09-17T06:00:00Z", ends_at: "2026-09-17T07:00:00Z" }],
      };
    if (path.endsWith("/apply")) {
      writes++;
      json = {};
    }
    await route.fulfill({ json });
  });
  await page.goto("/review");
  await page.getByRole("button", { name: "推荐空闲时间" }).click();
  const trigger = page.getByRole("button", { name: /调整到这里/ });
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "调整日程时间" });
  await expect(dialog).toBeVisible();
  expect(writes).toBe(0);
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect(writes).toBe(0);
  await trigger.click();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  expect(writes).toBe(0);
  await trigger.click();
  await page.screenshot({ path: testInfo.outputPath("review-confirm.png") });
  await dialog.getByRole("button", { name: "确认调整", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(writes).toBe(1);
});
