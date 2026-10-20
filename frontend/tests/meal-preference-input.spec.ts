import { expect, test } from "@playwright/test";

for (const detail of [false, true]) {
  test(`${detail ? "详情" : "新建"}约束单框添加`, async ({ page }) => {
    const preferences: { id: string; label: string; kind: string }[] = [];
    const meal = {
      id: "meal-1",
      dish: "牛肉",
      date: "2026-09-20",
      meal_type: "dinner",
      diners: 2,
      notes: "",
      shopping_url: null,
      calendar_url: null,
      preferences,
    };
    await page.route("**/api/**", async (route) => {
      const request = route.request();
      const path = new URL(request.url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
        });
      if (path === "/api/life/meal-plans" && request.method() === "POST") {
        expect(request.postDataJSON().preferences).toEqual([
          { label: "花生过敏，预算50元", kind: "preference" },
        ]);
        return route.fulfill({ json: meal });
      }
      if (path === "/api/life/meal-plans/meal-1" && request.method() === "PUT") {
        expect(request.postDataJSON().preferences).toEqual([
          { label: "花生过敏，预算50元", kind: "preference" },
        ]);
        preferences.splice(0, preferences.length, {
          id: "p1",
          ...request.postDataJSON().preferences[0],
        });
      }
      return route.fulfill({ json: path.includes("/meal-plans/meal-1") ? meal : { items: [] } });
    });
    await page.goto(detail ? "/meals/meal-1" : "/meals/new");
    await expect(page.getByLabel("标题（可选）", { exact: true })).toHaveCount(0);
    const form = page.locator(".meal-preference-form");
    await expect(form.locator("input")).toHaveCount(1);
    await expect(form.getByRole("button", { name: "类型", exact: true })).toHaveCount(0);
    await form.getByLabel("偏好或限制", { exact: true }).fill("花生过敏，预算50元");
    if (!detail) {
      await expect(form.getByRole("button")).toHaveCount(0);
      await page.getByLabel("菜品", { exact: true }).fill("牛肉");
      await page.screenshot({ path: "/tmp/meal-single-preference.png", fullPage: true });
      await page.getByRole("button", { name: "保存餐食", exact: true }).click();
      await expect(page).toHaveURL(/\/meals$/);
      return;
    }
    await expect(page.getByRole("button", { name: "添加约束", exact: true })).toHaveCount(0);
    await page.getByRole("button", { name: "保存修改", exact: true }).click();
    await expect(page.getByRole("button", { name: "保存修改", exact: true })).toBeDisabled();
    await page.reload();
    await expect(page.locator(".meal-preference-form input")).toHaveValue("花生过敏，预算50元");
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      await page.screenshot({
        path: `/tmp/meal-preference-${detail}-${width}.png`,
        fullPage: true,
      });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
    }
  });
}

test("餐食安排自由文本不解析，原样保存并在列表详情展示", async ({ page }) => {
  const schedule = "周末吃，两三个人 🌧️";
  let saved: Record<string, unknown> | null = null;
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/life/meal-plans" && request.method() === "POST") {
      const body = request.postDataJSON();
      expect(body.schedule_text).toBe(schedule);
      expect(body).not.toHaveProperty("date");
      expect(body).not.toHaveProperty("meal_type");
      expect(body).not.toHaveProperty("diners");
      saved = {
        ...body,
        id: "meal-1",
        date: null,
        meal_type: null,
        diners: null,
        calendar_url: null,
        shopping_url: "/shopping/list-1",
        status: "draft",
      };
      return route.fulfill({ json: saved });
    }
    if (path === "/api/life/meal-plans")
      return route.fulfill({ json: { items: saved ? [saved] : [] } });
    if (path === "/api/life/meal-plans/meal-1") return route.fulfill({ json: saved });
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/meals/new");
  await page.getByLabel("日期、餐次和人数", { exact: true }).fill(schedule);
  await page.getByLabel("菜品", { exact: true }).fill("牛肉");
  await page.screenshot({ path: "/tmp/meal-free-input.png", fullPage: true });
  await page.getByRole("button", { name: "保存餐食", exact: true }).click();
  await expect(page).toHaveURL(/\/meals$/);
  await expect(page.getByText(schedule, { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText(schedule, { exact: true })).toBeVisible();
  await page.locator(".meal-plan-summary").click();
  await expect(page.getByLabel("日期、餐次和人数", { exact: true })).toHaveValue(schedule);
});
