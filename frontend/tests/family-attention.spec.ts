import { expect, test } from "@playwright/test";

for (const decision of ["accept", "reject"] as const) {
  test(`首页家庭邀请${decision === "accept" ? "接受" : "拒绝"}后向邀请人展示反馈`, async ({
    page,
  }, testInfo) => {
    let creator = false;
    let pending = true;
    let read = false;
    let action = "";
    let fail = true;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let json: unknown = { items: [] };
      if (path === "/api/auth/me")
        json = {
          id: creator ? "owner" : "recipient",
          email: "demo@example.test",
          timezone: "Asia/Shanghai",
        };
      if (path === "/api/platform/home")
        json = {
          timezone: "Asia/Shanghai",
          server_time: "2026-09-18T00:00:00Z",
          today: { count: 0, items: [] },
          overdue: { count: 0, items: [] },
          recent: [],
        };
      if (path === "/api/hub/summary")
        json = { pending_reviews: 0, failed_emails: 0, connection_issues: 0 };
      if (path === "/api/households/invitations/incoming")
        json = {
          items:
            !creator && pending
              ? [{ id: "invite", household_name: "温暖之家", role: "member" }]
              : [],
        };
      if (path === "/api/notifications")
        json = {
          items:
            creator && !pending
              ? [
                  {
                    id: "feedback",
                    type: "invitation_result",
                    title: "家庭邀请已处理",
                    message: `成员已${decision === "accept" ? "接受" : "拒绝"}邀请`,
                    read,
                    invitation_id: "invite",
                    created_at: "2026-09-18T00:00:00Z",
                  },
                ]
              : [],
        };
      if (path === `/api/households/invitations/invite/${decision}`) {
        if (fail) {
          fail = false;
          return route.fulfill({
            status: 500,
            json: { error: { code: "FAILED", message: "处理失败，请重试" } },
          });
        }
        pending = false;
        action = decision;
      }
      if (path === "/api/notifications/feedback/read") read = true;
      await route.fulfill({ json });
    });
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "需要关注" })).toBeVisible();
    await page.getByRole("button", { name: "1 家庭邀请" }).click();
    await expect(page.getByRole("dialog")).toContainText("温暖之家");
    await page.screenshot({ path: testInfo.outputPath("family-invitation-mobile.png") });
    await page
      .getByRole("button", { name: decision === "accept" ? "接受邀请" : "拒绝", exact: true })
      .click();
    await expect(page.getByRole("alert")).toContainText("处理失败");
    await expect(page.getByRole("dialog")).toBeVisible();
    await page
      .getByRole("button", { name: decision === "accept" ? "接受邀请" : "拒绝", exact: true })
      .click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(action).toBe(decision);
    await expect(page.getByRole("heading", { name: "需要关注" })).toBeHidden();
    creator = true;
    await page.reload();
    await page.getByRole("button", { name: "1 邀请反馈" }).click();
    await expect(page.getByRole("dialog")).toContainText(
      `成员已${decision === "accept" ? "接受" : "拒绝"}邀请`,
    );
    await expect(page.getByRole("button", { name: "接受邀请", exact: true })).toHaveCount(0);
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.screenshot({ path: testInfo.outputPath("family-feedback-desktop.png") });
    await page.getByRole("button", { name: "标为已读" }).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
    expect(read).toBe(true);
  });
}
