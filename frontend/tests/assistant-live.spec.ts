import { expect, test } from "@playwright/test";

test.use({ trace: "off", screenshot: "off", video: "off" });

test("PRD03 真实模型、页面、接口和数据库闭环", async ({ page }) => {
  test.skip(process.env.ASSISTANT_LIVE_E2E !== "1", "仅对隔离测试服务运行");
  test.setTimeout(90000);
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(process.env.ASSISTANT_LIVE_EMAIL!);
  await page.getByLabel("密码", { exact: true }).fill(process.env.ASSISTANT_LIVE_PASSWORD!);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL("/");

  await page.goto("/assistant/preferences");
  await page.getByLabel("称呼、表达偏好和稳定习惯").fill("回答保持简短");
  await page.getByRole("button", { name: "保存指令" }).click();
  await expect(page.getByText("AI 偏好已保存")).toBeVisible();
  await page.getByPlaceholder("例如：我周末习惯早起跑步").fill("我喜欢早晨安排任务");
  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.getByText("我喜欢早晨安排任务")).toBeVisible();

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("我现在有待办吗？");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText(/没有找到|找到 \d+ 条待办/)).toBeVisible({ timeout: 30000 });

  await page.getByLabel("对话内容").fill("创建待办：PRD03浏览器真实联调");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("button", { name: "确认创建" })).toBeVisible({ timeout: 30000 });
  await page.getByRole("button", { name: "确认创建" }).click();
  await expect(page.getByText("待办已创建。")).toBeVisible();
  await expect(page.getByRole("link", { name: /PRD03浏览器真实联调/ })).toBeVisible();

  await page.reload();
  await expect(page.getByText("待办已创建。")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
