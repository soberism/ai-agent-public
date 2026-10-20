import { expect, test } from "@playwright/test";

test("餐食关联清单使用通用详情，添加和完成共享数据", async ({ page }) => {
  const items: { id: string; title: string; completed: boolean }[] = [];
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/life/meal-plans")
      return route.fulfill({
        json: {
          items: [
            {
              id: "meal-1",
              dish: "牛肉",
              schedule_text: "明晚",
              shopping_url: "/checklists/list-1",
              calendar_url: null,
            },
          ],
        },
      });
    if (path.startsWith("/api/planning/checklists/list-1")) {
      if (request.method() === "POST" && path.endsWith("/items"))
        items.push({ id: "item-1", ...request.postDataJSON(), completed: false });
      if (request.method() === "PATCH") Object.assign(items[0], request.postDataJSON());
      return route.fulfill({
        json: {
          id: "list-1",
          title: "牛肉采购",
          items,
          completed_count: items.filter((item) => item.completed).length,
          total_count: items.length,
          shared_household_ids: [],
        },
      });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/meals");
  await page.getByRole("link", { name: "清单", exact: true }).click();
  await expect(page).toHaveURL(/\/checklists\/list-1$/);
  await page.getByLabel("清单项", { exact: true }).fill("鸡蛋 6个");
  await page.getByRole("button", { name: "添加", exact: true }).click();
  await page.getByRole("checkbox").click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await page.reload();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await expect(page.getByText("1/1 已完成", { exact: true })).toBeVisible();
});
