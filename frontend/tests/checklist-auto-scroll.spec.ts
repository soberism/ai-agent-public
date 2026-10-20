import { expect, test } from "@playwright/test";

test("清单连续添加后输入框仍可见并保留焦点，失败不滚动", async ({ page }, testInfo) => {
  const items = Array.from({ length: 25 }, (_, index) => ({
    id: String(index),
    title: `项目${index}`,
    completed: false,
  }));
  let fail = false;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.test", timezone: "Asia/Shanghai" },
      });
    if (path.endsWith("/items") && route.request().method() === "POST") {
      if (fail)
        return route.fulfill({
          status: 500,
          json: { error: { code: "FAILED", message: "添加失败" } },
        });
      items.unshift({
        id: String(items.length),
        title: route.request().postDataJSON().title,
        completed: false,
      });
    }
    return route.fulfill({
      json: path.startsWith("/api/planning/checklists/list")
        ? {
            id: "list",
            title: "旅游准备",
            items,
            completed_count: 0,
            total_count: items.length,
            pinned: false,
            shared_household_ids: [],
          }
        : { items: [] },
    });
  });
  await page.goto("/checklists/list");
  const input = page.getByRole("textbox", { name: "清单项", exact: true });
  await expect(page.locator(".checklist-add")).toHaveCSS("position", "static");
  for (let index = 0; index < 3; index++) {
    await input.fill(`新增${index}`);
    await page.evaluate(() => window.scrollTo(0, 0));
    await input.press("Enter");
    await expect(input).toHaveValue("");
    await expect(input).toBeFocused();
    await expect(input).toBeInViewport();
    await expect(page.getByText(`新增${index}`, { exact: true })).toBeVisible();
    await expect(page.locator(".check-items li").first()).toContainText(`新增${index}`);
  }
  await page.screenshot({ path: testInfo.outputPath("checklist-newest-top.png") });
  fail = true;
  await input.fill("失败项目");
  await page.evaluate(() => window.scrollTo(0, 0));
  await input.press("Enter");
  await expect(page.getByRole("alert")).toContainText("添加失败");
  expect(await page.evaluate(() => scrollY)).toBe(0);
  await expect(input).toHaveValue("失败项目");
});
