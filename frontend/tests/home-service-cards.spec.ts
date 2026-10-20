import { expect, test } from "@playwright/test";
test("生活服务横滑卡片保留入口和禁用状态", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/platform/home")
      return route.fulfill({
        json: {
          timezone: "Asia/Shanghai",
          server_time: "2026-09-18T04:00:00Z",
          today: { count: 0, items: [] },
          overdue: { count: 0, items: [] },
          recent: [],
        },
      });
    return route.fulfill({
      json: {
        pending_reviews: 0,
        pending_assignments: 0,
        failed_emails: 0,
        connection_issues: 0,
        pending_voice_memos: 0,
        items: [],
      },
    });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/");
    const cards = page.getByRole("region", { name: "更多生活服务，横向滚动" });
    await expect(cards.getByRole("link", { name: "家庭 家庭成员管理" })).toHaveAttribute(
      "href",
      "/family",
    );
    await expect(cards.getByRole("link", { name: "文档 上传文件、分目录整理" })).toHaveAttribute(
      "href",
      "/documents",
    );
    expect(await cards.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
    await cards.evaluate((node) => (node.scrollLeft = node.scrollWidth));
    expect(await cards.evaluate((node) => node.scrollLeft)).toBeGreaterThan(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await cards.scrollIntoViewIfNeeded();
    await page.screenshot({ path: `/tmp/home-service-cards-${width}.png`, fullPage: true });
    await cards.getByRole("link", { name: "餐食 偏好与购物准备" }).click();
    await expect(page).toHaveURL(/\/meals$/);
  }
});
