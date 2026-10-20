import { expect, test } from "@playwright/test";

test("功能中心通用清单创建、勾选与刷新", async ({ page }, testInfo) => {
  const list = {
    id: "trip-1",
    title: "出行准备",
    items: [] as { id: string; title: string; completed: boolean }[],
    completed_count: 0,
    total_count: 0,
    shared_household_ids: [],
    pinned: false,
  };
  let created = false;
  const copy = () => ({
    ...list,
    id: "copy-1",
    title: `${list.title}（副本）`,
    completed_count: 0,
    items: list.items.map((item) => ({ ...item, completed: false })),
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    let json: unknown = { items: [] };
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      json = {
        id: "trip-user",
        nickname: "测试",
        email: "demo@example.com",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/planning/checklists") {
      if (method === "POST") {
        list.title = route.request().postDataJSON().title;
        created = true;
        json = list;
      } else
        json = {
          items: created
            ? [
                { ...list, pinned: true },
                { ...list, id: "other", title: "普通清单" },
              ]
            : [],
        };
    }
    if (path === "/api/planning/checklists/trip-1") json = list;
    if (path === "/api/planning/checklists/trip-1/duplicate") {
      expect(method).toBe("POST");
      json = copy();
    }
    if (path === "/api/planning/checklists/copy-1") json = copy();
    if (path === "/api/planning/checklists/trip-1/items") {
      list.items.push({
        id: "item-1",
        title: route.request().postDataJSON().title,
        completed: false,
      });
      list.total_count = 1;
      json = list;
    }
    if (path.endsWith("/items/item-1")) {
      list.items[0]!.completed = route.request().postDataJSON().completed;
      list.completed_count = list.items[0]!.completed ? 1 : 0;
      json = list;
    }
    await route.fulfill({ json });
  });
  await page.goto("/features");
  await expect(page.getByRole("link", { name: /旅游清单/ })).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath("features.png"), fullPage: true });
  await page.locator('.feature-menu a[href="/checklists"]').click();
  await expect(page).toHaveURL(/\/checklists$/);
  await expect(page.getByText("还没有清单")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("checklists-empty.png"), fullPage: true });
  await page.getByRole("button", { name: "旅行准备", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "清单名称" })).toHaveValue("旅行准备");
  await expect(page.getByRole("textbox", { name: "清单名称" })).toBeFocused();
  await expect(page.getByRole("heading", { name: "还没有清单" })).toBeVisible();
  await page.getByRole("textbox", { name: "清单名称" }).fill("出行准备");
  await page.getByRole("button", { name: "新建", exact: true }).click();
  await expect(page.getByRole("heading", { name: "出行准备" })).toBeVisible();
  await expect(page.getByRole("button", { name: "复用此清单" })).toHaveCount(0);
  await page.getByRole("textbox", { name: "清单项", exact: true }).fill("身份证");
  await page.getByRole("button", { name: "添加", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "清单项", exact: true })).toHaveValue("");
  await expect(page.getByRole("textbox", { name: "清单项", exact: true })).toBeFocused();
  await page.getByRole("checkbox", { name: "身份证" }).click();
  await expect(page.getByRole("checkbox", { name: "身份证" })).toBeChecked();
  await expect(page.getByText("1/1 已完成")).toBeVisible();
  await page.goto("/checklists");
  await page.reload();
  await expect(page.getByRole("link", { name: "出行准备 置顶 1/1 已完成" })).toBeVisible();
  await expect(page.locator(".checklist-pin")).toHaveCount(1);
  await expect(page.getByRole("link", { name: "普通清单 1/1 已完成" })).toBeVisible();
  await expect(page.getByText("普通清单")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("checklists-list.png"), fullPage: true });
  await page.getByRole("button", { name: "复用出行准备", exact: true }).click();
  await expect(page).toHaveURL(/\/checklists\/copy-1$/);
  await expect(page.getByRole("heading", { name: "出行准备（副本）" })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "身份证" })).not.toBeChecked();
});

test("旅游专用路由已移除", async ({ page }) => {
  await page.goto("/travel-checklists");
  await expect(page.getByRole("heading", { name: "页面不存在" })).toBeVisible();
});

test("添加清单项后恢复焦点", async ({ page }) => {
  const list = {
    id: "focus-list",
    title: "测试清单",
    items: [] as { id: string; title: string; completed: boolean }[],
    completed_count: 0,
    total_count: 0,
    shared_household_ids: [],
    pinned: false,
  };
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      return route.fulfill({
        json: { id: "focus-user", email: "test@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/planning/checklists/focus-list/items") {
      list.items.push({
        id: String(list.items.length),
        title: route.request().postDataJSON().title,
        completed: false,
      });
      list.total_count = list.items.length;
      return route.fulfill({ json: list });
    }
    if (path === "/api/planning/checklists/focus-list") return route.fulfill({ json: list });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/checklists/focus-list");
  const input = page.getByRole("textbox", { name: "清单项", exact: true });
  for (const title of ["身份证", "充电器"]) {
    await input.fill(title);
    await page.getByRole("button", { name: "添加", exact: true }).click();
    await expect(input).toHaveValue("");
    await expect(input).toBeFocused();
    await expect(page.getByRole("checkbox", { name: title, exact: true })).toBeVisible();
  }
});
