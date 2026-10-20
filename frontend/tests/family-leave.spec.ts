import { expect, test } from "@playwright/test";

test("成员退出确认、失败重试及退出后刷新", async ({ page }, testInfo) => {
  let left = false;
  let attempts = 0;
  const home = { id: "home", name: "测试家庭", role: "member", member_count: 2 };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "member", email: "member@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/households") json = { items: left ? [] : [home] };
    if (path === "/api/households/home")
      json = { ...home, members: [], invitations: [], profiles: [], pets: [] };
    if (path === "/api/households/home/leave") {
      attempts++;
      if (attempts === 1)
        return route.fulfill({
          status: 500,
          json: { error: { code: "FAILED", message: "退出失败，请重试" } },
        });
      left = true;
      return route.fulfill({ status: 204 });
    }
    await route.fulfill({ json });
  });
  await page.goto("/family");
  await expect(page.getByRole("button", { name: "删除家庭", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "退出家庭", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "退出家庭" });
  await expect(dialog).toContainText("你创建的内容会保留");
  await page.screenshot({ path: testInfo.outputPath("family-leave-mobile.png") });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "退出家庭", exact: true }).click();
  await dialog.getByRole("button", { name: "退出家庭", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("退出失败");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "退出家庭", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "建立家庭空间" })).toBeVisible();
});
