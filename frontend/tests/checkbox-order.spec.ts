import { expect, test } from "@playwright/test";
import { uncheckedFirst } from "../src/shared/uncheckedFirst";

test("选中项置底、同状态稳定且不修改原数组", () => {
  const items = [
    { id: "a", checked: true },
    { id: "b", checked: false },
    { id: "c", checked: true },
    { id: "d", checked: false },
  ];
  expect(uncheckedFirst(items, (item) => item.checked).map((item) => item.id)).toEqual([
    "b",
    "d",
    "a",
    "c",
  ]);
  expect(items.map((item) => item.id)).toEqual(["a", "b", "c", "d"]);
});

for (const kind of ["checklist"]) {
  test(`${kind}勾选置底、取消恢复、刷新和失败保持正确顺序`, async ({ page }) => {
    const items = [
      {
        id: "a",
        name: "甲",
        title: "甲",
        purchased: false,
        completed: false,
        quantity: 1,
        unit: "",
        category: "",
        origin: "manual",
      },
      {
        id: "b",
        name: "乙",
        title: "乙",
        purchased: false,
        completed: false,
        quantity: 1,
        unit: "",
        category: "",
        origin: "manual",
      },
      {
        id: "c",
        name: "丙",
        title: "丙",
        purchased: true,
        completed: true,
        quantity: 1,
        unit: "",
        category: "",
        origin: "manual",
      },
    ];
    let fail = false;
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
        });
      if (
        path.includes(
          kind === "shopping" ? "/life/shopping-lists/list-1" : "/planning/checklists/list-1",
        )
      ) {
        if (request.method() === "PATCH") {
          if (fail)
            return route.fulfill({
              status: 500,
              json: { error: { code: "FAILED", message: "保存失败" } },
            });
          Object.assign(
            items.find((item) => path.endsWith(`/items/${item.id}`))!,
            request.postDataJSON(),
          );
        }
        return route.fulfill({
          json: {
            id: "list-1",
            title: "测试清单",
            items,
            status: "draft",
            completed_count: items.filter((item) => item.completed).length,
            total_count: 3,
            shared_household_ids: [],
          },
        });
      }
      return route.fulfill({ json: { items: [] } });
    });
    await page.goto(kind === "shopping" ? "/shopping/list-1" : "/checklists/list-1");
    const rows = page.locator(kind === "shopping" ? ".shopping-list li" : ".check-items li");
    const titles = rows.locator(kind === "shopping" ? "strong" : "label span");
    await expect(titles).toHaveText(["甲", "乙", "丙"]);
    await rows.filter({ hasText: "甲" }).getByRole("checkbox").click();
    await expect(titles).toHaveText(["乙", "甲", "丙"]);
    await page.reload();
    await expect(titles).toHaveText(["乙", "甲", "丙"]);
    await rows.filter({ hasText: "甲" }).getByRole("checkbox").click();
    await expect(titles).toHaveText(["甲", "乙", "丙"]);
    fail = true;
    await rows.filter({ hasText: "乙" }).getByRole("checkbox").click();
    await expect(page.getByRole("alert")).toContainText("保存失败");
    await expect(titles).toHaveText(["甲", "乙", "丙"]);
    await expect(rows.filter({ hasText: "乙" }).getByRole("checkbox")).not.toBeChecked();
    await page.screenshot({ path: `test-results/checkbox-order-${kind}.png`, fullPage: true });
  });
}

test("清单项删除支持取消、失败重试、计数更新和刷新", async ({ page }) => {
  let items = [
    { id: "a", title: "买票", completed: false },
    { id: "b", title: "卫生纸", completed: true },
  ];
  let writes = 0;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path.startsWith("/api/planning/checklists/list-1")) {
      if (request.method() === "DELETE") {
        writes++;
        if (writes === 1)
          return route.fulfill({
            status: 500,
            json: { error: { code: "FAILED", message: "删除失败，请重试" } },
          });
        items = items.filter((item) => !path.endsWith(`/items/${item.id}`));
      }
      return route.fulfill({
        json: {
          id: "list-1",
          title: "出行清单",
          items,
          total_count: items.length,
          completed_count: items.filter((item) => item.completed).length,
          shared_household_ids: [],
        },
      });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/checklists/list-1");
  const remove = page.getByRole("button", { name: "删除清单项 买票", exact: true });
  await remove.click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(writes).toBe(0);
  await remove.click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("删除失败，请重试");
  await expect(page.locator(".check-items li")).toHaveCount(2);
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(remove).toHaveCount(0);
  await expect(page.getByText("1/1 已完成", { exact: true })).toBeVisible();
  await page.reload();
  await expect(remove).toHaveCount(0);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/checklist-item-delete-${width}.png`, fullPage: true });
  }
  await page.getByRole("button", { name: "删除清单项 卫生纸", exact: true }).click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".check-items li")).toHaveCount(0);
  await expect(page.getByText("0/0 已完成", { exact: true })).toBeVisible();
  expect(writes).toBe(3);
});
