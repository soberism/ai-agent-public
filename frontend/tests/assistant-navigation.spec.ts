import { expect, test } from "@playwright/test";

test("AI 对话保留来源 Tab，关闭返回来源页面", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (!["/api/auth/me", "/api/platform/settings", "/api/assistant/threads"].includes(path))
      return route.fulfill({ status: 503, json: { message: "测试中暂不可用" } });
    const json =
      path === "/api/assistant/threads"
        ? { thread_id: "demo", entries: [] }
        : {
            id: "demo",
            email: "demo@example.com",
            timezone: "Asia/Shanghai",
          };
    return route.fulfill({ json });
  });
  for (const [path, label] of [
    ["/", "首页"],
    ["/calendar", "日程"],
    ["/todos", "待办"],
    ["/features", "功能"],
    ["/settings", "我的"],
  ]) {
    await page.goto(`${path}?source=test`);
    if (path === "/") {
      const button = page.getByRole("link", { name: "打开 AI 对话" });
      const outer = await button.boundingBox();
      const inner = await button.locator("svg").boundingBox();
      if (!outer || !inner) throw new Error("AI 悬浮按钮或图标未显示");
      expect(Math.abs(outer.y + outer.height / 2 - inner.y - inner.height / 2)).toBeLessThan(1);
      await button.screenshot({ path: "/tmp/ai-assistant-fab-centered.png" });
    }
    await page.getByRole("link", { name: "打开 AI 对话" }).click();
    if (path === "/")
      await expect(page.locator(".assistant-page")).toHaveCSS("animation-name", "assistant-rise");
    const nav = page.getByRole("navigation", { name: "全局导航" });
    await expect(nav.locator(".active")).toHaveCount(1);
    await expect(nav.locator(".active")).toHaveText(label);
    await expect(nav.getByRole("link", { name: label })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("button", { name: "关闭 AI 对话" })).toBeVisible();
    await page.getByRole("button", { name: "关闭 AI 对话" }).click();
    if (path === "/")
      await expect(page.locator(".assistant-page-closing")).toHaveCSS(
        "animation-name",
        "assistant-lower",
      );
    await expect(page).toHaveURL(new RegExp(`${path.replaceAll("/", "\\/")}\\?source=test$`));
  }
  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "AI 对话" })).toBeVisible();
  await expect(page.locator(".bottom-nav .active")).toHaveCount(0);
  await page.screenshot({ path: "/tmp/ai-assistant-navigation.png" });
  await page.getByRole("button", { name: "关闭 AI 对话" }).click();
  await expect(page).toHaveURL(/\/$/);
});

test("关闭动画被禁用时仍能返回来源页面", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const json =
      path === "/api/assistant/threads"
        ? { thread_id: "demo", entries: [] }
        : { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" };
    return route.fulfill({ json });
  });
  await page.goto("/assistant");
  await expect(page.getByRole("button", { name: "关闭 AI 对话" })).toBeVisible();
  await page.addStyleTag({ content: ".assistant-page-closing { animation: none !important; }" });
  await page.getByRole("button", { name: "关闭 AI 对话" }).click();
  await expect(page).toHaveURL(/\/$/);
});
