import { expect, test } from "@playwright/test";

test("常用功能默认入口、30天排序、点击记录和账号隔离", async ({ page }) => {
  let userId = "frequent-demo";
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      return route.fulfill({
        json: { id: userId, email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/platform/home")
      return route.fulfill({
        json: {
          timezone: "Asia/Shanghai",
          server_time: new Date().toISOString(),
          today: { count: 0, items: [] },
          overdue: { count: 0, items: [] },
          recent: [],
          recent_events: [],
        },
      });
    if (path === "/api/hub/summary")
      return route.fulfill({
        json: { pending_reviews: 0, failed_emails: 0, connection_issues: 0 },
      });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "常用功能", exact: true });
  const links = nav.getByRole("link");
  await expect(links).toHaveText(["清单", "计划回顾", "随手记转待办", "全局搜索", "餐食计划"]);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await nav.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await nav.evaluate((element) => {
      element.scrollLeft = element.scrollWidth;
    });
    expect(await nav.evaluate((element) => element.scrollLeft)).toBeGreaterThan(0);
    await nav.evaluate((element) => {
      element.scrollLeft = 0;
    });
    await page.screenshot({ path: `/tmp/frequent-features-${width}.png`, fullPage: true });
  }
  await page.evaluate(() => {
    const now = Date.now();
    localStorage.setItem(
      "feature-usage:frequent-demo",
      JSON.stringify([
        ...Array.from({ length: 4 }, () => ({ to: "/meals", at: now - 1000 })),
        ...Array.from({ length: 2 }, () => ({ to: "/search", at: now - 1000 })),
        ...Array.from({ length: 8 }, () => ({ to: "/review", at: now - 31 * 86400000 })),
        { to: "/family", at: now - 1000 },
        { to: "/review", at: now + 86400000 },
        null,
      ]),
    );
  });
  await page.reload();
  await expect(links.first()).toHaveText("餐食计划");
  await expect(links.nth(1)).toHaveText("全局搜索");
  await nav.getByRole("link", { name: "全局搜索", exact: true }).click();
  await expect(page).toHaveURL(/\/search$/);
  await expect
    .poll(() =>
      page.evaluate(() => {
        const visits = JSON.parse(localStorage.getItem("feature-usage:frequent-demo")!);
        return visits.filter((visit: { to: string }) => visit.to === "/search").length;
      }),
    )
    .toBe(3);
  userId = "other-demo";
  await page.goto("/");
  await expect(links.first()).toHaveText("清单");
  await page.evaluate(() => localStorage.setItem("feature-usage:other-demo", "invalid"));
  await page.reload();
  await expect(links).toHaveCount(5);
});

test("功能中心图标统一尺寸并居中", async ({ page }) => {
  await page.route("**/api/**", (route) =>
    route.fulfill({
      json: { id: "icon-demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
    }),
  );
  await page.goto("/features");
  await expect(page.locator(".feature-intro")).toHaveCount(0);
  const icons = page.locator(".feature-menu > :is(a, button) > span > svg");
  await expect(icons).toHaveCount(14);
  for (const path of [
    "/todos",
    "/calendar",
    "/plan",
    "/assistant",
    "/shopping",
    "/connections",
    "/settings",
  ]) {
    await expect(page.locator(`.feature-menu > a[href="${path}"]`)).toHaveCount(0);
  }
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const metrics = await icons.evaluateAll((elements) =>
      elements.map((element) => {
        const icon = element.getBoundingClientRect();
        const box = element.parentElement!.getBoundingClientRect();
        return {
          width: icon.width,
          height: icon.height,
          dx: icon.x + icon.width / 2 - box.x - box.width / 2,
          dy: icon.y + icon.height / 2 - box.y - box.height / 2,
        };
      }),
    );
    for (const metric of metrics) {
      expect(metric.width).toBe(24);
      expect(metric.height).toBe(24);
      expect(Math.abs(metric.dx)).toBeLessThan(0.1);
      expect(Math.abs(metric.dy)).toBeLessThan(0.1);
    }
    await page.screenshot({ path: `/tmp/features-icons-fixed-${width}.png`, fullPage: true });
  }
});
