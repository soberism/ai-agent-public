import { expect, test } from "@playwright/test";

for (const scoped of [false, true]) {
  test(`旧购物入口${scoped ? "按餐食创建" : "列表"}进入通用清单`, async ({ page }) => {
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
        });
      if (path === "/api/life/shopping-lists") {
        expect(new URL(route.request().url()).searchParams.get("meal_id")).toBe("meal-1");
        return route.fulfill({ json: { checklist_url: "/checklists/list-1" } });
      }
      return route.fulfill({
        json: path.endsWith("/checklists/list-1")
          ? {
              id: "list-1",
              title: "餐食准备",
              items: [],
              total_count: 0,
              completed_count: 0,
              shared_household_ids: [],
            }
          : { items: [] },
      });
    });
    await page.goto(scoped ? "/shopping?meal_id=meal-1" : "/shopping");
    await expect(page).toHaveURL(scoped ? /\/checklists\/list-1$/ : /\/checklists$/);
    await expect(page.getByRole("button", { name: "清单类型", exact: true })).toHaveCount(0);
  });
}
