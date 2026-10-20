import { expect, test } from "@playwright/test";

for (const kind of ["preferences", "pantry"]) {
  test(`${kind}删除需确认，失败保留，成功移除`, async ({ page }) => {
    let deleted = false;
    let writes = 0;
    let unit = "盒";
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      const json = (body: unknown) => route.fulfill({ json: body });
      if (path === "/api/life/pantry" && route.request().method() === "POST") {
        expect(route.request().postDataJSON().unit).toBe("");
        unit = "";
        deleted = false;
        return route.fulfill({
          status: 201,
          json: { id: "item-1", name: "牛奶", quantity: 2, unit },
        });
      }
      if (route.request().method() === "DELETE") {
        expect(path).toBe(`/api/life/${kind}/item-1`);
        writes++;
        if (writes === 1)
          return route.fulfill({
            status: 500,
            json: { error: { code: "FAILED", message: "删除失败，请重试" } },
          });
        deleted = true;
        return route.fulfill({ status: 204, body: "" });
      }
      if (path === "/api/auth/me")
        return json({ id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" });
      if (path === "/api/life/meal-plans")
        return json({
          items: [],
          preferences:
            kind === "preferences" && !deleted
              ? [{ id: "item-1", label: "少辣", kind: "preference" }]
              : [],
          pantry:
            kind === "pantry" && !deleted
              ? [{ id: "item-1", name: "牛奶", quantity: 2, unit }]
              : [],
        });
      return json({ items: [] });
    });
    await page.setViewportSize({ width: kind === "preferences" ? 320 : 390, height: 1800 });
    await page.goto("/meals/settings");
    if (kind === "preferences")
      await page.getByText("历史全局偏好（未关联餐食）", { exact: true }).click();
    const name = kind === "preferences" ? "删除偏好或限制 少辣" : "删除库存 牛奶";
    await expect(page.getByRole("button", { name, exact: true })).toBeVisible();
    expect(
      await page.getByLabel("库存食材").evaluate((el) => el.getBoundingClientRect().height),
    ).toBe(44);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `test-results/meal-delete-entry-${kind}.png`, fullPage: true });
    await page.getByRole("button", { name, exact: true }).click();
    await expect(page.getByRole("dialog")).toBeVisible();
    expect(writes).toBe(0);
    await page.getByRole("button", { name: "取消", exact: true }).click();
    expect(writes).toBe(0);
    await page.getByRole("button", { name, exact: true }).click();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.getByRole("alert")).toContainText("删除失败，请重试");
    await expect(page.getByRole("button", { name, exact: true })).toBeAttached();
    await page.getByRole("button", { name: "确认删除", exact: true }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
    await page.reload();
    await expect(page.getByRole("heading", { name: "现有库存" })).toBeVisible();
    await expect(page.getByRole("button", { name, exact: true })).toHaveCount(0);
    if (kind === "pantry") {
      await page.getByLabel("库存食材").fill("牛奶");
      await page.getByLabel("数量", { exact: true }).last().fill("2");
      await expect(page.getByLabel("单位", { exact: true })).not.toHaveAttribute("required");
      await page.getByRole("button", { name: "加入库存", exact: true }).click();
      await expect(page.getByRole("button", { name: "删除库存 牛奶", exact: true })).toBeVisible();
      await expect(page.locator(".meal-setting-items").last()).toContainText("2");
    }
    await page.screenshot({ path: `test-results/meal-delete-${kind}.png`, fullPage: true });
  });
}
