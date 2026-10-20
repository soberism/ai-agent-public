import { expect, test } from "@playwright/test";
test("清单长标题换行且不覆盖返回按钮", async ({ page }) => {
  const title = "2026-09-17 · 214234、4234234、234234";
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    return route.fulfill({
      json:
        path === "/api/planning/checklists/list-1"
          ? {
              id: "list-1",
              title,
              completed_count: 0,
              total_count: 0,
              items: [],
              shared_household_ids: [],
              pinned: false,
            }
          : { items: [] },
    });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/checklists/list-1");
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    const heading = await page.getByRole("heading", { name: title }).boundingBox();
    const back = await page.getByRole("button", { name: "返回", exact: true }).boundingBox();
    expect(heading!.x).toBeGreaterThanOrEqual(back!.x + back!.width);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/checklist-header-${width}.png`, fullPage: true });
  }
});
