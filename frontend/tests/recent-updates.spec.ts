import { expect, test } from "@playwright/test";

test("最近更新合并待办和日程，按更新时间展示五条并链接对应详情", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "recent-user", email: "demo@example.com", timezone: "Asia/Shanghai" };
    if (path === "/api/platform/settings")
      json = {
        id: "recent-user",
        email: "demo@example.com",
        timezone: "Asia/Shanghai",
        has_todos: true,
      };
    if (path === "/api/hub/summary") json = {};
    if (path === "/api/platform/home")
      json = {
        timezone: "Asia/Shanghai",
        server_time: "2026-09-17T00:00:00Z",
        today: { count: 0, items: [] },
        overdue: { count: 0, items: [] },
        recent: Array.from({ length: 5 }, (_, i) => ({
          id: `todo-${i}`,
          title: `待办${i}`,
          due_date: "2026-09-17",
          due_time: "09:00",
          updated_at: `2026-09-16T0${5 - i}:00:00Z`,
        })),
        recent_events: [
          {
            id: "event-1",
            title: "家长会",
            start_date: "2026-09-18",
            start_time: "10:00",
            updated_at: "2026-09-17T00:00:00Z",
          },
        ],
      };
    await route.fulfill({ json });
  });
  await page.goto("/");
  const section = page.getByRole("region", { name: "最近更新" });
  await expect(section.getByRole("link")).toHaveCount(5);
  await expect(section.getByRole("link").first()).toHaveAttribute("href", "/calendar/event-1/edit");
  await expect(section.getByRole("link").nth(1)).toHaveAttribute("href", "/todos/todo-0");
  await expect(section.getByText("日程 · 明天 10:00")).toBeVisible();
  await expect(section.getByText("待办4", { exact: true })).toHaveCount(0);
});
