import { expect, test } from "@playwright/test";
import { readFile } from "node:fs/promises";

test("剩余一小时时提醒，开始新对话后消失", async ({ page }, testInfo) => {
  const now = new Date("2026-09-22T08:00:00Z");
  await page.clock.install({ time: now });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads") {
      const fresh = route.request().postDataJSON().fresh === true;
      return route.fulfill({
        json: {
          thread_id: fresh
            ? "44444444-4444-4444-4444-444444444444"
            : "33333333-3333-3333-3333-333333333333",
          expires_at: new Date(now.getTime() + (fresh ? 24 * 60 : 61) * 60000).toISOString(),
          entries: fresh
            ? []
            : [
                { role: "user", message: "帮我找待办" },
                {
                  role: "assistant",
                  reply: {
                    kind: "result",
                    message: "找到一条待办",
                    items: [
                      {
                        id: "1",
                        title: "买牛奶",
                        due_date: null,
                        due_time: null,
                        status: "open",
                        kind: "todo",
                        url: null,
                      },
                    ],
                    action_token: "secret-token",
                    action_label: "确认",
                  },
                },
              ],
        },
      });
    }
    if (path.startsWith("/api/agent/runs/active/")) return route.fulfill({ status: 404 });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await expect(page.getByText("当前对话将在 1 小时内过期")).toHaveCount(0);
  await page.clock.fastForward(2 * 60000);
  await expect(page.getByRole("status")).toContainText("当前对话将在 1 小时内过期");
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载对话" }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^AI对话-\d{4}-\d{2}-\d{2}\.txt$/);
  const content = await readFile((await download.path())!, "utf8");
  expect(content).toContain("我：帮我找待办");
  expect(content).toContain("AI：找到一条待办\n- 买牛奶");
  expect(content).not.toContain("secret-token");
  await page.screenshot({ path: testInfo.outputPath("assistant-expiry-notice.png") });
  await page.setViewportSize({ width: 320, height: 700 });
  await expect(page.getByRole("status")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(320);
  await page.getByRole("button", { name: "开始新对话" }).click();
  await expect(page.getByText("当前对话将在 1 小时内过期")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "下载对话" })).toHaveCount(0);
});
