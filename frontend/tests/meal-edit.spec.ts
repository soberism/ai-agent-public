import { expect, test } from "@playwright/test";
test("餐食直接编辑、失败保留、保存刷新和偏好保留", async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-18T04:00:00Z"));
  let meal = {
    id: "meal-1",
    dish: "番茄炒蛋",
    schedule_text: "明晚两个人",
    date: null,
    meal_type: null,
    diners: null,
    notes: "少盐",
    status: "draft",
    shopping_url: "/checklists/list-1",
    calendar_url: null,
    preferences: [{ id: "pref-1", label: "不吃花生", kind: "preference" }],
  };
  let writes = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/life/meal-plans/meal-1") {
      if (route.request().method() === "PUT") {
        const body = route.request().postDataJSON();
        expect(body.date).toBe("2026-09-20");
        expect(body).not.toHaveProperty("preferences");
        if (++writes === 1)
          return route.fulfill({
            status: 500,
            json: { error: { code: "FAILED", message: "保存失败，请重试" } },
          });
        meal = { ...meal, ...body };
      }
      return route.fulfill({ json: meal });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/meals/meal-1");
  await expect(page.getByRole("button", { name: "编辑", exact: true })).toHaveCount(0);
  await page.getByLabel("菜品", { exact: true }).fill("临时菜品");
  await page.getByRole("button", { name: "添加菜品", exact: true }).click();
  await page.getByRole("button", { name: "移除菜品 临时菜品", exact: true }).click();
  await page.getByRole("button", { name: "移除菜品 番茄炒蛋", exact: true }).click();
  await page.getByLabel("菜品", { exact: true }).fill("清蒸鱼");
  await page.getByRole("button", { name: "餐食日期", exact: true }).click();
  await page.locator('.react-calendar abbr[aria-label="2026年9月20日"]').click();
  await expect(page.getByRole("button", { name: "餐食日期", exact: true })).toContainText(
    "2026/09/20",
  );
  await page.getByLabel("日期、餐次和人数").fill("周末三个人");
  await page.getByLabel("备注", { exact: true }).fill("少辣");
  await page.getByRole("button", { name: "保存修改" }).click();
  await expect(page.getByRole("alert")).toContainText("保存失败，请重试");
  await expect(page.getByLabel("菜品", { exact: true })).toHaveValue("清蒸鱼");
  await page.screenshot({ path: "test-results/meal-edit-390.png", fullPage: true });
  await page.getByRole("button", { name: "保存修改" }).click();
  await page.reload();
  await expect(page.getByRole("button", { name: "餐食日期", exact: true })).toContainText(
    "2026/09/20",
  );
  await expect(page.getByRole("button", { name: "移除菜品 清蒸鱼", exact: true })).toBeVisible();
  await expect(page.getByLabel("日期、餐次和人数")).toHaveValue("周末三个人");
  await expect(page.getByLabel("备注", { exact: true })).toHaveValue("少辣");
  await expect(page.getByLabel("偏好或限制", { exact: true })).toHaveValue("不吃花生");
});
