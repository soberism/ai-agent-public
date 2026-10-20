import { expect, test } from "@playwright/test";

test("页面顶部标题栏统一44px", async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      status: new URL(route.request().url()).pathname.includes("summary") ? 503 : 200,
      json:
        new URL(route.request().url()).pathname === "/api/auth/me"
          ? { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" }
          : { items: [] },
    }),
  );
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const path of [
      "/",
      "/calendar",
      "/todos",
      "/checklists",
      "/settings",
      "/features",
      "/calendar/new",
      "/todos/new",
    ]) {
      await page.goto(path);
      const header = page.locator(".page-header, .platform-header").first();
      await expect(header).toBeVisible();
      const dimensions = await header.evaluate((element) => {
        const style = getComputedStyle(element);
        return {
          height: element.getBoundingClientRect().height,
          top: parseFloat(style.paddingTop),
        };
      });
      expect(dimensions.top).toBe(8);
      expect(dimensions.height - dimensions.top).toBe(44);
      for (const tabs of await page.locator(".tabs").all()) {
        expect((await tabs.boundingBox())!.height).toBe(44);
        expect((await tabs.locator("button").first().boundingBox())!.height).toBe(36);
      }
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
  }
});
