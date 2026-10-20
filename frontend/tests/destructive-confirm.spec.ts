import { expect, test } from "@playwright/test";

for (const scenario of [
  {
    url: "/checklists/list-1",
    button: "删除清单",
    title: "删除清单",
    endpoint: "/api/planning/checklists/list-1",
  },
  {
    url: "/calendar/event-1/edit",
    button: "删除日程",
    title: "删除日程",
    endpoint: "/api/calendar/events/event-1",
  },
  {
    url: "/documents",
    button: "删除",
    title: "删除材料",
    endpoint: "/api/documents/materials/material-1",
  },
  {
    url: "/assistant/preferences",
    button: "删除",
    title: "删除记忆",
    endpoint: "/api/assistant/memories/memory-1",
  },
  { url: "/settings", button: "退出登录", title: "退出登录", endpoint: "/api/auth/logout" },
  { url: "/connections", button: "删除收件邮箱 2", title: "删除收件邮箱", endpoint: "" },
]) {
  test(`${scenario.title}需要确认`, async ({ page }, testInfo) => {
    let writes = 0;
    let deleted = false;
    page.on("dialog", () => {
      throw new Error("不能使用浏览器原生确认");
    });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const method = route.request().method();
      if (path === scenario.endpoint && (method === "DELETE" || method === "POST")) {
        writes++;
        deleted = true;
        return route.fulfill({ status: 204, body: "" });
      }
      const todo = {
        id: "todo-1",
        title: "测试待办",
        status: "ongoing",
        due_date: null,
        due_time: null,
        description: "",
        created_at: "2026-09-17T00:00:00Z",
        updated_at: "2026-09-17T00:00:00Z",
      };
      const data: Record<string, unknown> = {
        "/api/auth/me": {
          id: "user-1",
          nickname: "测试",
          email: "demo@example.com",
          timezone: "Asia/Shanghai",
        },
        "/api/platform/settings": { nickname: "测试", timezone: "Asia/Shanghai" },
        "/api/planning/checklists/list-1": {
          id: "list-1",
          title: "旅行准备",
          items: [],
          completed_count: 0,
          total_count: 0,
          shared_household_ids: [],
        },
        "/api/calendar/events/event-1": {
          id: "event-1",
          title: "测试日程",
          start_date: "2026-09-17",
          end_date: "2026-09-17",
          start_time: "09:00",
          end_time: "10:00",
          status: "scheduled",
        },
        "/api/todos/todo-1": todo,
        "/api/todos": { items: [], server_time: "2026-09-17T00:00:00Z" },
        "/api/planning/reminders": deleted
          ? []
          : [
              {
                id: "reminder-1",
                todo_id: "todo-1",
                remind_at: "2026-09-17T01:00:00Z",
                timezone: "Asia/Shanghai",
                status: "scheduled",
              },
            ],
        "/api/documents/materials": {
          items: deleted
            ? []
            : [
                {
                  id: "material-1",
                  name: "测试材料.txt",
                  kind: "file",
                  status: "uploaded",
                  created_at: "2026-09-17T00:00:00Z",
                  folder_id: null,
                  review_count: 0,
                },
              ],
          folders: [],
        },
        "/api/documents/capabilities": {},
        "/api/assistant/preferences": { custom_instructions: "", memory_enabled: true },
        "/api/assistant/memories": [
          { id: "memory-1", content: "周末晨跑", source: "user", enabled: true },
        ],
        "/api/mail/capabilities": { smtp: false },
        "/api/mail/notifications": [],
        "/api/workflows/email-settings": {
          notifications_enabled: false,
          recipient_emails: ["demo@example.com", "other@example.com"],
          daily_enabled: false,
          daily_time: "09:00",
          reminder_enabled: false,
          reminder_minutes: 30,
          weekly_enabled: false,
          weekly_day: 0,
          weekly_time: "09:00",
          quiet_start: "22:00",
          quiet_end: "08:00",
        },
      };
      await route.fulfill({ json: data[path] ?? { items: [] } });
    });
    await page.goto(scenario.url);
    const trigger = page.getByRole("button", { name: scenario.button, exact: true });
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: scenario.title, exact: true });
    await expect(dialog).toBeVisible();
    expect(writes).toBe(0);
    await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(writes).toBe(0);
    await trigger.click();
    await page.screenshot({ path: testInfo.outputPath("confirm.png"), fullPage: true });
    await dialog
      .getByRole("button", {
        name: scenario.title === "退出登录" ? "确认退出" : "确认删除",
        exact: true,
      })
      .click();
    await expect(dialog).toHaveCount(0);
    if (scenario.endpoint) expect(writes).toBe(1);
    else await expect(page.getByRole("textbox", { name: "收件邮箱 2" })).toHaveCount(0);
  });
}
