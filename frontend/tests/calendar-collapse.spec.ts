import { expect, test } from "@playwright/test";
test("月历收起展开保留日期和日程列表", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      json:
        path === "/api/auth/me"
          ? { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" }
          : { items: [] },
    });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/calendar?date=2026-09-18");
    await expect(page.locator("#calendar-month-grid")).toBeVisible();
    await page.getByRole("button", { name: "收起日历", exact: true }).click();
    await expect(page.locator("#calendar-month-grid")).toBeHidden();
    await expect(page.locator("section.month-calendar")).toBeHidden();
    await expect(page.locator(".platform-header .calendar-collapse-toggle")).toBeVisible();
    expect(await page.locator(".calendar-collapse-toolbar").count()).toBe(0);
    const headerBox = await page.locator(".platform-header").boundingBox();
    const tabsBox = await page.locator(".tabs").boundingBox();
    const dateBox = await page.locator(".selected-date").boundingBox();
    expect(tabsBox!.y - headerBox!.y - headerBox!.height).toBe(16);
    expect(dateBox!.y - tabsBox!.y - tabsBox!.height).toBe(20);
    await expect(
      page.getByRole("heading", { name: "2026-09-18 的日程", exact: true }),
    ).toBeVisible();
    await expect(page.getByRole("button", { name: "展开日历", exact: true })).toHaveAttribute(
      "aria-expanded",
      "false",
    );
    await page.screenshot({ path: `/tmp/calendar-collapsed-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "展开日历", exact: true }).click();
    await expect(page.locator("#calendar-month-grid")).toBeVisible();
    await expect(page.locator(".react-calendar__tile--active abbr")).toHaveAttribute(
      "aria-label",
      "2026年9月18日",
    );
    await page.screenshot({ path: `/tmp/calendar-expanded-${width}.png`, fullPage: true });
  }
});
