import { expect, test } from "@playwright/test";

for (const role of ["owner", "admin", "member"]) {
  test(`家庭角色权限 ${role}`, async ({ page }, testInfo) => {
    const home = { id: "home", name: "权限测试家庭", role, member_count: 3 };
    let invited = false;
    let removed = false;
    let failSave = false;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let json: unknown = { items: [] };
      if (path === "/api/auth/me")
        json = { id: role, email: `${role}@example.test`, timezone: "Asia/Shanghai" };
      if (path === "/api/households") json = { items: [home] };
      if (path === "/api/households/home")
        json = {
          ...home,
          members: ["owner", "admin", "member"]
            .filter((x) => !removed || x !== "member")
            .map((x) => ({
              id: x,
              account_id: x,
              display_name: x,
              email: `${x}@example.test`,
              role: x,
              status: "active",
              permissions: [],
            })),
          invitations: [],
          profiles: [],
          pets: [],
        };
      if (path.endsWith("/invitations")) {
        invited = true;
        json = {};
      }
      if (path.endsWith("/removal-impact")) json = { message: "移出后将失去家庭访问权" };
      if (route.request().method() === "PATCH") {
        const body = route.request().postDataJSON();
        if ("role" in body) {
          if (failSave)
            return route.fulfill({
              status: 500,
              json: { error: { code: "FAILED", message: "保存失败" } },
            });
          expect(body.role).toBe("admin");
        } else {
          expect(body).toEqual({ status: "removed" });
          removed = true;
        }
        json = {};
      }
      await route.fulfill({ json });
    });
    await page.goto("/family");
    await expect(page.getByRole("heading", { name: "权限测试家庭" })).toBeVisible();
    await expect(page.getByRole("button", { name: "删除家庭", exact: true })).toHaveCount(
      role === "owner" ? 1 : 0,
    );
    await expect(page.getByRole("button", { name: "保存角色" })).toHaveCount(
      role === "owner" ? 2 : 0,
    );
    await expect(page.getByRole("button", { name: "移出家庭", exact: true })).toHaveCount(
      role === "owner" ? 2 : role === "admin" ? 1 : 0,
    );
    await expect(
      page
        .locator(".member-access-row")
        .filter({ hasText: `${role}@example.test` })
        .getByRole("button", { name: "移出家庭", exact: true }),
    ).toHaveCount(0);
    await expect(page.getByRole("button", { name: "退出家庭", exact: true })).toHaveCount(
      role === "owner" ? 0 : 1,
    );
    if (role === "owner") {
      const row = page.locator(".member-access-row").filter({ hasText: "admin@example.test" });
      await row.getByRole("button", { name: "保存角色" }).click();
      await expect(page.getByRole("status")).toContainText("角色保存成功");
      await page.waitForTimeout(300);
      await page.screenshot({ path: testInfo.outputPath("role-save-success.png") });
      failSave = true;
      await row.getByRole("button", { name: "保存角色" }).click();
      await expect(page.getByRole("alert")).toContainText("保存失败");
      await expect(page.getByText("角色保存成功", { exact: true })).toHaveCount(0);
    }
    if (role === "admin") {
      await page.getByText("邀请成员", { exact: true }).click();
      await page.getByRole("textbox", { name: "邀请邮箱" }).fill("new@example.test");
      await page.getByRole("button", { name: "发出站内邀请" }).click();
      await expect.poll(() => invited).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("family-admin.png") });
      await page
        .locator(".member-access-row")
        .filter({ hasText: "member@example.test" })
        .getByRole("button", { name: "移出家庭" })
        .click();
      await page.getByRole("button", { name: "确认移出" }).click();
      await expect.poll(() => removed).toBe(true);
      await expect(
        page.locator(".member-access-row").filter({ hasText: "member@example.test" }),
      ).toHaveCount(0);
    }
  });
}
