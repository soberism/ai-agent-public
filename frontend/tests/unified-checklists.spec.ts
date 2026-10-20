import { expect, test } from "@playwright/test";

test("全部清单使用同一套操作，无购物类型选择，旧链接复用通用详情", async ({ page }) => {
  let items = [
    { id: "normal", title: "旅行准备", total_count: 2, completed_count: 0, pinned: false },
    { id: "migrated", title: "123", total_count: 2, completed_count: 0, pinned: false },
  ];
  await page.route("**/api/**", async (route) => {
    const request = route.request(),
      path = new URL(request.url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/planning/checklists")
      return route.fulfill({ json: request.method() === "POST" ? { id: "new" } : { items } });
    if (path === "/api/life/shopping-lists/legacy")
      return route.fulfill({ json: { checklist_url: "/checklists/migrated" } });
    if (path.endsWith("/duplicate")) return route.fulfill({ json: { id: "copy" } });
    if (request.method() === "DELETE") {
      items = items.filter((item) => !path.endsWith(item.id));
      return route.fulfill({ status: 204 });
    }
    return route.fulfill({
      json: path.startsWith("/api/planning/checklists/")
        ? {
            id: "migrated",
            title: "123",
            total_count: 2,
            completed_count: 0,
            items: [
              { id: "a", title: "牛奶", completed: false },
              { id: "b", title: "鸡蛋", completed: false },
            ],
            shared_household_ids: [],
          }
        : { items: [] },
    });
  });
  await page.goto("/checklists");
  await expect(page.getByRole("button", { name: "清单类型", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "复用123", exact: true })).toBeVisible();
  await expect(page.getByText("购物", { exact: true })).toHaveCount(0);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.screenshot({ path: `/tmp/checklists-one-kind-${width}.png`, fullPage: true });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  await page.getByRole("button", { name: "复用123", exact: true }).click();
  await expect(page).toHaveURL(/\/checklists\/copy$/);
  await page.goto("/shopping/legacy");
  await expect(page).toHaveURL(/\/checklists\/migrated$/);
  await expect(page.getByRole("button", { name: "置顶清单", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "全部完成", exact: true })).toBeVisible();
  await page.goto("/checklists/shopping/legacy");
  await expect(page).toHaveURL(/\/checklists\/migrated$/);
  await page.goto("/checklists");
  await page.getByLabel("清单名称", { exact: true }).fill("周末准备");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await expect(page).toHaveURL(/\/checklists\/new$/);
  await page.goto("/checklists");
  await page.getByRole("button", { name: "删除清单：123", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("button", { name: "复用123", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "复用旅行准备", exact: true })).toBeVisible();
});
