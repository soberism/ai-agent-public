import { expect, test } from "@playwright/test";
test("餐食列表独立显示所选日期和自由文本安排", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    return route.fulfill({
      json: {
        items: [
          {
            id: "meal-1",
            dish: "番茄炒蛋",
            date: "2026-09-20",
            schedule_text: "两个人，少辣",
            meal_type: null,
            diners: null,
            notes: null,
            shopping_url: "/checklists/list-1",
            calendar_url: null,
          },
        ],
      },
    });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/meals");
    await expect(page.locator(".meal-plan-summary time")).toHaveText("2026-09-20");
    await expect(page.getByText("两个人，少辣", { exact: true })).toBeVisible();
    await expect(page.getByText(/null/)).toHaveCount(0);
    await page.screenshot({ path: `/tmp/meal-list-date-${width}.png`, fullPage: true });
  }
});
