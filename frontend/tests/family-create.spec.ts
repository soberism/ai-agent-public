import { expect, test } from "@playwright/test";

for (const initialCount of [0, 1]) {
  test(`已有${initialCount}个家庭时仍可创建并切换新家庭`, async ({ page }, testInfo) => {
    const home = (id: string, name: string) => ({
      id,
      name,
      role: "owner",
      member_count: 1,
      members: [
        {
          id: "owner",
          account_id: "user",
          display_name: "测试创建者",
          email: "test@example.test",
          role: "owner",
          status: "active",
          permissions: [],
        },
      ],
      invitations: [],
      profiles: [],
      pets: [],
    });
    const homes = initialCount ? [home("first", "原有家庭")] : [];
    let fail = initialCount === 1;
    let posts = 0;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: { id: "user", email: "test@example.test", timezone: "Asia/Shanghai" },
        });
      if (path === "/api/households") {
        if (route.request().method() === "POST") {
          posts++;
          if (fail) {
            fail = false;
            return route.fulfill({
              status: 500,
              json: { error: { code: "FAILED", message: "创建失败，请重试" } },
            });
          }
          const created = home("new", route.request().postDataJSON().name);
          homes.push(created);
          return route.fulfill({ status: 201, json: created });
        }
        return route.fulfill({ json: { items: homes } });
      }
      const found = homes.find((item) => path === `/api/households/${item.id}`);
      return route.fulfill({ json: found ?? { items: [] } });
    });
    await page.goto("/family");
    if (initialCount) {
      await page.getByRole("button", { name: "创建家庭", exact: true }).click();
      await page.getByRole("button", { name: "取消", exact: true }).click();
      expect(posts).toBe(0);
      await expect(page.getByRole("button", { name: "创建家庭", exact: true })).toBeVisible();
      await page.getByRole("button", { name: "创建家庭", exact: true }).click();
    }
    await expect(page.getByRole("region", { name: "家庭选择" })).toHaveCount(0);
    await page.screenshot({
      path: testInfo.outputPath("family-form-mobile.png"),
      animations: "disabled",
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({
      path: testInfo.outputPath("family-form-desktop.png"),
      animations: "disabled",
      fullPage: true,
    });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.getByLabel("家庭名称", { exact: true }).fill("新家庭");
    if (initialCount) {
      await page.getByRole("button", { name: "创建家庭", exact: true }).click();
      await expect(page.getByRole("alert")).toContainText("创建失败");
      await expect(page.getByLabel("家庭名称", { exact: true })).toHaveValue("新家庭");
    }
    await page.getByRole("button", { name: "创建家庭", exact: true }).click();
    await expect(page.getByLabel("家庭名称", { exact: true })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "创建家庭", exact: true })).toBeVisible();
    if (initialCount)
      await expect(page.getByRole("button", { name: "当前家庭", exact: true })).toContainText(
        "新家庭",
      );
    expect(posts).toBe(initialCount ? 2 : 1);
    await page.screenshot({
      path: testInfo.outputPath("family-create-mobile.png"),
      fullPage: true,
    });
    await page.setViewportSize({ width: 1280, height: 900 });
    await expect(page.getByRole("button", { name: "创建家庭", exact: true })).toBeVisible();
    await page.screenshot({
      path: testInfo.outputPath("family-create-desktop.png"),
      fullPage: true,
    });
  });
}
