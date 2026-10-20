import type { DietaryPreference } from "../src/features/life_services/types";
import { expect, test } from "@playwright/test";

test.use({ hasTouch: true, isMobile: true });

for (const width of [320, 390]) {
  test(`${width}px餐食列表进入新建，失败保留表单，保存回到列表`, async ({ page }) => {
    const meals: Record<string, unknown>[] = [];
    let writes = 0;
    const preferences: DietaryPreference[] = [];
    let preferenceDeletes = 0;
    await page.clock.setFixedTime(new Date("2026-09-17T04:00:00Z"));
    await page.setViewportSize({ width, height: 844 });
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      const json = (body: unknown) => route.fulfill({ json: body });
      if (path === "/api/auth/me")
        return json({ id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" });
      if (path === "/api/planning/checklists")
        return json({
          items: [
            { id: "list-1", title: "周末采购", meal_id: null },
            { id: "list-used", title: "已关联清单", meal_id: "other-meal" },
          ],
        });
      if (path === "/api/life/meal-plans") {
        if (request.method() === "POST") {
          writes++;
          if (writes === 1)
            return route.fulfill({
              status: 500,
              json: { error: { code: "FAILED", message: "保存失败，请重试" } },
            });
          expect(request.postDataJSON().checklist_id).toBe("list-1");
          expect(request.postDataJSON().dish).toContain("、紫菜汤");
          preferences.push(
            ...request
              .postDataJSON()
              .preferences.map((item: Omit<DietaryPreference, "id">, index: number) => ({
                ...item,
                id: `pref-${index}`,
              })),
          );
          meals.push({
            id: "meal-1",
            ...request.postDataJSON(),
            preferences,
            status: "draft",
            calendar_url: null,
            shopping_url: "/checklists/list-1",
          });
          return route.fulfill({ status: 201, json: meals[0] });
        }
        return json({ items: meals, preferences: [], pantry: [] });
      }
      if (path === "/api/life/meal-plans/meal-1/preferences" && request.method() === "POST") {
        preferences.push({ ...request.postDataJSON(), id: "pref-new" });
        return json(meals[0]);
      }
      if (
        path === "/api/life/meal-plans/meal-1/preferences/pref-0" &&
        request.method() === "DELETE"
      ) {
        preferenceDeletes++;
        preferences.splice(0, 1);
        return json(meals[0]);
      }
      if (path === "/api/life/meal-plans/meal-2")
        return json({ ...meals[0], id: "meal-2", dish: "牛肉面", preferences: [] });
      if (path === "/api/life/meal-plans/meal-1") return json(meals[0]);
      if (path === "/api/life/meal-plans/missing")
        return route.fulfill({
          status: 404,
          json: { error: { code: "MEAL_NOT_FOUND", message: "餐食计划不存在或无法访问" } },
        });
      return json({ items: [] });
    });
    await page.goto("/meals");
    await expect(page.getByRole("link", { name: "新建餐食计划", exact: true })).toBeVisible();
    await expect(page.getByText("还没有餐食安排")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "餐食安排", exact: true })).toHaveCount(0);
    await expect(page.getByRole("link", { name: "全部清单", exact: true })).toHaveCount(0);
    await expect(page.locator(".feature-card")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "把每一餐，安排得刚刚好" })).toBeVisible();
    await expect(page.getByLabel("菜品")).toHaveCount(0);
    await expect(page.getByRole("heading", { name: "现有库存" })).toHaveCount(0);
    await page.screenshot({ path: `test-results/meals-empty-${width}.png`, fullPage: true });
    await page.getByRole("link", { name: "新建餐食计划", exact: true }).click();
    await expect(page).toHaveURL(/\/meals\/new$/);
    await page.getByLabel("日期、餐次和人数", { exact: true }).fill("2026-09-20 晚餐 3人");
    await page.getByLabel("菜品").fill("番茄炒蛋和清蒸鲈鱼，搭配杂粮饭与时令蔬菜");
    await page.getByRole("button", { name: "关联清单", exact: true }).click();
    await expect(page.getByRole("button", { name: "已关联清单", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "周末采购", exact: true }).click();
    await page.getByRole("button", { name: "添加菜品", exact: true }).click();
    await page.getByLabel("菜品", { exact: true }).fill("紫菜汤");
    await page.getByRole("button", { name: "添加菜品", exact: true }).click();
    await page.getByLabel("菜品", { exact: true }).fill("临时菜品");
    await page.getByRole("button", { name: "添加菜品", exact: true }).click();
    await page.getByRole("button", { name: "移除菜品 临时菜品", exact: true }).click();
    await page.getByLabel("备注").fill("少盐，不放花生");
    for (const label of ["少辣", "花生过敏", "50元以内", "清淡"]) {
      await page.getByLabel("偏好或限制", { exact: true }).fill(label);
      await page.getByRole("button", { name: "添加约束", exact: true }).click();
    }
    await page.getByRole("button", { name: "移除约束 清淡", exact: true }).click();
    await expect(page.getByText("清淡", { exact: true })).toHaveCount(0);
    await page.screenshot({ path: `test-results/meals-new-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "保存餐食", exact: true }).click();
    await expect(page.getByRole("alert").locator("span")).toHaveText("保存失败，请重试");
    await expect(page).toHaveURL(/\/meals\/new$/);
    await expect(page.getByRole("button", { name: "移除菜品 紫菜汤", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "保存餐食", exact: true }).click();
    await expect(page).toHaveURL(/\/meals$/);
    await expect(page.getByText("2026-09-20 晚餐 3人", { exact: true })).toBeVisible();
    await expect(page.locator(".meal-welcome")).toHaveCount(0);
    await expect(page.getByRole("link", { name: "清单", exact: true })).toHaveAttribute(
      "href",
      "/checklists/list-1",
    );
    await page.reload();
    await expect(page.getByText("2026-09-20 晚餐 3人", { exact: true })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/meals-list-${width}.png`, fullPage: true });
    await page.locator(".meal-plan-summary").click();
    await expect(page).toHaveURL(/\/meals\/meal-1$/);
    await expect(page.getByRole("heading", { name: "餐食详情", exact: true })).toBeVisible();
    await expect(page.getByText("餐食安排：2026-09-20 晚餐 3人", { exact: true })).toBeVisible();
    await expect(page.getByText("备注：少盐，不放花生", { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "查看清单", exact: true })).toHaveAttribute(
      "href",
      "/checklists/list-1",
    );
    await page.reload();
    await expect(page.getByText("餐食安排：2026-09-20 晚餐 3人", { exact: true })).toBeVisible();
    await expect(page.getByText("50元以内", { exact: true })).toBeVisible();
    await page.getByRole("button", { name: "删除偏好或限制 少辣", exact: true }).click();
    expect(preferenceDeletes).toBe(0);
    await page.getByRole("button", { name: "取消", exact: true }).click();
    expect(preferenceDeletes).toBe(0);
    await page.getByRole("button", { name: "删除偏好或限制 少辣", exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "删除偏好或限制 少辣", exact: true }),
    ).toHaveCount(0);
    await page.getByRole("button", { name: "添加约束", exact: true }).click();
    await expect(page.locator(".toast.error")).toContainText("请填写偏好或限制");
    await page.getByRole("button", { name: "关闭提示", exact: true }).click();
    await page.getByLabel("偏好或限制", { exact: true }).fill("清淡");
    await page.getByRole("button", { name: "添加约束", exact: true }).click();
    await expect(page.getByText("清淡", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByText("清淡", { exact: true })).toBeVisible();
    await page.screenshot({ path: `test-results/meals-detail-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await expect(page).toHaveURL(/\/meals$/);
    await expect(page.getByRole("link", { name: "现有库存", exact: true })).toHaveCount(0);
    expect(meals).toHaveLength(1);
    await page.goto("/meals/meal-2");
    await expect(page.getByRole("heading", { name: "牛肉面", exact: true })).toBeVisible();
    await expect(page.getByText("花生过敏", { exact: true })).toHaveCount(0);
    await expect(page.getByText("清淡", { exact: true })).toHaveCount(0);
    await page.goto("/meals/missing");
    await expect(page.getByRole("alert").locator("span")).toHaveText("餐食计划不存在或无法访问");
    await expect(page.getByRole("link", { name: "查看清单", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "返回", exact: true }).click();
    await expect(page).toHaveURL(/\/meals$/);
  });
}

test("加入日历重复失败时，每次都显示同一条提示", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path.endsWith("/confirm"))
      return route.fulfill({
        status: 422,
        json: { error: { code: "INVALID", message: "请先设置用餐时间" } },
      });
    await route.fulfill({
      json:
        path === "/api/auth/me"
          ? { id: "toast-user", timezone: "Asia/Shanghai" }
          : path === "/api/life/meal-plans"
            ? { items: [{ id: "meal-toast", dish: "测试餐食", schedule_text: "未定" }] }
            : { items: [] },
    });
  });
  await page.goto("/meals");
  const add = page.getByRole("button", { name: "加入日历", exact: true });
  const toast = page.getByRole("alert");
  await add.click();
  await expect(toast).toHaveText(/请先设置用餐时间/);
  await expect(toast).toHaveCount(0, { timeout: 5000 });
  await add.click();
  await expect(toast).toHaveText(/请先设置用餐时间/);
  await page.getByRole("button", { name: "关闭提示" }).click();
  await expect(toast).toHaveCount(0);
  await add.click();
  await expect(toast).toHaveText(/请先设置用餐时间/);
});
