import { expect, test } from "@playwright/test";

const threadId = "33333333-3333-3333-3333-333333333333";
const runId = "44444444-4444-4444-4444-444444444444";
const targetId = "66666666-6666-6666-6666-666666666666";
const item = {
  id: targetId,
  title: "出行准备",
  due_date: null,
  due_time: null,
  status: "active",
  kind: "checklist",
  url: `/checklists/${targetId}`,
};
const suggestions = [
  {
    id: "add",
    source_run_id: runId,
    label: "添加清单项",
    type: "follow_up",
    intent: "add_checklist_item",
    target_kind: "checklist",
    target_id: targetId,
    target_title: "出行准备",
    draft: "在清单「出行准备」添加：",
    url: null,
  },
  {
    id: "view",
    source_run_id: runId,
    label: "查看清单",
    type: "navigate",
    intent: "open_checklist",
    target_kind: "checklist",
    target_id: targetId,
    target_title: "出行准备",
    draft: null,
    url: item.url,
  },
];
const reply = {
  kind: "success",
  message: "已创建清单「出行准备」，包含2项。",
  items: [item],
  suggestions,
  action_token: null,
  action_label: null,
};

for (const width of [390, 1280]) {
  test(`结果和推荐操作统一在回复气泡内，刷新后保持一致 ${width}`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    let saved = false;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({ json: { id: "test-user", email: "demo@example.test" } });
      if (path === "/api/assistant/threads")
        return route.fulfill({
          json: { thread_id: threadId, entries: saved ? [{ role: "assistant", reply }] : [] },
        });
      if (path.includes("/agent/runs/pending/")) return route.fulfill({ json: [] });
      if (path.includes("/agent/runs/active/")) return route.fulfill({ status: 204 });
      if (path === "/api/agent/runs") {
        saved = true;
        return route.fulfill({
          json: {
            id: runId,
            thread_id: threadId,
            status: "completed",
            progress: null,
            final_answer: reply.message,
            sources: [],
            error: null,
            plan_version: 1,
            suggestions,
            actions: [
              {
                id: "action-1",
                title: "创建清单及清单项",
                description: null,
                status: "completed",
                result: reply,
                error: null,
              },
            ],
          },
        });
      }
      return route.fulfill({ status: 404 });
    });
    await page.goto("/assistant");
    await page.getByLabel("对话内容").fill("创建出行准备清单");
    await page.getByRole("button", { name: "发送" }).click();
    const bubble = page.locator(".chat-assistant");
    await expect(bubble).toHaveCount(1);
    await expect(bubble).toContainText(reply.message);
    await expect(bubble.getByRole("button", { name: "添加清单项" })).toBeVisible();
    await expect(bubble.getByRole("link", { name: "查看清单" })).toHaveAttribute("href", item.url);
    await expect(bubble.locator(`a[href="${item.url}"]`)).toHaveCount(1);
    await expect(page.getByRole("region", { name: "操作结果" })).toHaveCount(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBeTruthy();
    await page.screenshot({
      path: `../backend/.local/assistant-result-${width}.png`,
      fullPage: true,
    });
    await bubble.getByRole("button", { name: "添加清单项" }).click();
    await expect(page.getByLabel("对话内容")).toHaveValue(suggestions[0].draft);
    await page.reload();
    await expect(bubble).toHaveCount(1);
    await expect(bubble.getByRole("button", { name: "添加清单项" })).toBeVisible();
    await expect(bubble.locator(`a[href="${item.url}"]`)).toHaveCount(1);
    await expect(page.getByRole("region", { name: "操作结果" })).toHaveCount(0);
  });
}
