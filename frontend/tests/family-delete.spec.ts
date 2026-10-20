import { expect, test } from "@playwright/test";

test("家庭删除确认、取消、失败恢复及成功刷新", async ({ page }, testInfo) => {
  let deleted = false;
  let fail = true;
  let requests = 0;
  const home = { id: "home", name: "测试家庭", role: "owner", member_count: 1 };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "owner", email: "owner@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/households") json = { items: deleted ? [] : [home] };
    if (path === "/api/households/home") {
      if (route.request().method() === "DELETE") {
        requests++;
        if (fail)
          return route.fulfill({
            status: 500,
            json: { error: { code: "FAILED", message: "删除失败，请重试" } },
          });
        deleted = true;
        return route.fulfill({ status: 204 });
      }
      json = {
        ...home,
        members: [
          {
            id: "owner",
            account_id: "owner",
            display_name: "创建者",
            email: "owner@example.test",
            role: "owner",
            status: "active",
            permissions: [],
          },
        ],
        invitations: [],
        profiles: [],
        pets: [],
      };
    }
    await route.fulfill({ json });
  });
  await page.goto("/family");
  await page.getByRole("button", { name: "删除家庭", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "删除家庭" });
  await expect(dialog).toContainText("业务内容保留");
  await page.screenshot({ path: testInfo.outputPath("family-delete-mobile.png") });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect(requests).toBe(0);
  await page.getByRole("button", { name: "删除家庭", exact: true }).click();
  await dialog.getByRole("button", { name: "删除家庭", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("删除失败");
  await expect(dialog).toBeVisible();
  fail = false;
  await dialog.getByRole("button", { name: "删除家庭", exact: true }).click();
  await expect(page.getByRole("heading", { name: "建立家庭空间" })).toBeVisible();
  await expect(dialog).toHaveCount(0);
  expect(requests).toBe(2);
});
