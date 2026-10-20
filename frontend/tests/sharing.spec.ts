import { expect, test } from "@playwright/test";

test("所有共享业务种类使用统一可见范围，家庭成员按账号选择", async ({ page }, testInfo) => {
  const kinds = [
    "todo",
    "event",
    "checklist",
    "reminder",
    "material",
    "meal",
    "shopping",
    "voice_memo",
    "daily_dump",
    "contact",
    "contact_group",
    "pantry",
    "preference",
    "appointment",
  ];
  const policies = new Map<string, unknown>();
  let fail = false;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/sharing/states") {
      const keys = new URL(route.request().url()).searchParams.get("resources")!.split(",");
      json = { states: Object.fromEntries(keys.map((key) => [key, "private"])), editable: keys };
    }
    if (path === "/api/auth/me")
      json = {
        id: "owner",
        email: "demo@example.com",
        nickname: "测试",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/hub/search")
      json = {
        items: kinds.map((kind) => ({
          kind,
          id: kind,
          title: `${kind}共享项`,
          detail: "",
          url: "/search",
        })),
      };
    if (path === "/api/sharing/options")
      json = {
        households: [
          {
            id: "home",
            name: "测试家庭",
            role: "owner",
            members: [{ account_id: "account-member", display_name: "家人", role: "member" }],
          },
        ],
      };
    if (path.startsWith("/api/sharing/") && !path.endsWith("options") && !path.endsWith("states")) {
      if (route.request().method() === "PUT") {
        if (fail) {
          await route.fulfill({
            status: 422,
            json: { error: { code: "INVALID", message: "成员已被移除" } },
          });
          return;
        }
        policies.set(path, route.request().postDataJSON());
      }
      json = policies.get(path) ?? { scope: "private", household_id: null, member_ids: [] };
    }
    await route.fulfill({ json });
  });
  await page.goto("/search");
  await page.getByRole("searchbox").fill("共享");
  await expect(
    page.getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true }),
  ).toHaveCount(kinds.length);
  for (const kind of kinds) {
    await page
      .locator("li")
      .filter({ hasText: `${kind}共享项` })
      .getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true })
      .click();
    const dialog = page.getByRole("dialog", { name: "可见范围", exact: true });
    await expect(dialog.getByRole("button", { name: "谁可以访问", exact: true })).toHaveText(
      "自己可见",
    );
    await dialog.getByRole("button", { name: "谁可以访问", exact: true }).click();
    await page
      .getByRole("dialog", { name: "选择选项" })
      .getByRole("button", { name: "部分可见", exact: true })
      .click();
    await dialog.getByRole("checkbox", { name: "家人", exact: true }).check();
    await expect(dialog.getByRole("checkbox", { name: "协作者甲", exact: true })).toHaveCount(0);
    await dialog.getByRole("button", { name: "保存可见范围" }).click();
    await expect(dialog).toHaveCount(0);
    expect(policies.get(`/api/sharing/${kind}/${kind}`)).toEqual({
      scope: "members",
      household_id: "home",
      member_ids: ["account-member"],
    });
  }
  await page
    .locator("li")
    .filter({ hasText: "todo共享项" })
    .getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true })
    .click();
  const dialog = page.getByRole("dialog", { name: "可见范围", exact: true });
  await dialog.getByRole("button", { name: "谁可以访问", exact: true }).click();
  await expect(page.getByRole("button", { name: "指定协作者可见", exact: true })).toHaveCount(0);
  await page
    .getByRole("dialog", { name: "选择选项" })
    .getByRole("button", { name: "部分可见", exact: true })
    .click();
  await dialog.getByRole("checkbox", { name: "家人", exact: true }).check();

  fail = true;
  await dialog.getByRole("button", { name: "保存可见范围" }).click();
  await expect(dialog.getByRole("alert")).toHaveText("成员已被移除");
  await page.screenshot({ path: testInfo.outputPath("sharing-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("sharing-desktop.png"), fullPage: true });
});

test("普通成员只查看家庭，收到的邀请可接受", async ({ page }, testInfo) => {
  let accepted = false;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/sharing/states") {
      const keys = new URL(route.request().url()).searchParams.get("resources")!.split(",");
      json = { states: Object.fromEntries(keys.map((key) => [key, "private"])), editable: keys };
    }
    if (path === "/api/auth/me")
      json = {
        id: "member",
        email: "demo@example.com",
        nickname: "成员",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/households")
      json = { items: [{ id: "home", name: "测试家庭", role: "member", member_count: 2 }] };
    if (path === "/api/households/home")
      json = {
        id: "home",
        name: "测试家庭",
        role: "member",
        member_count: 2,
        invitations: [],
        profiles: [],
        pets: [],
        members: [
          {
            id: "owner",
            account_id: "owner",
            display_name: "创建者",
            email: "owner@example.com",
            role: "owner",
            permissions: [],
            status: "active",
          },
          {
            id: "member",
            account_id: "member",
            display_name: "成员",
            email: "demo@example.com",
            role: "member",
            permissions: [],
            status: "active",
          },
        ],
      };
    if (path === "/api/households/invitations/incoming")
      json = {
        items: accepted
          ? []
          : [{ id: "invite", household_name: "新家庭", role: "member", expires_at: null }],
      };
    if (path === "/api/households/invitations/invite/accept") {
      accepted = true;
      json = { status: "accepted" };
    }
    await route.fulfill({ json });
  });
  await page.goto("/family");
  await expect(page.getByRole("heading", { name: "家庭成员", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "保存角色" })).toHaveCount(0);
  await expect(page.getByText("邀请成员", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "家庭协作" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "照护资料" })).toHaveCount(0);
  await page.getByRole("button", { name: "接受邀请", exact: true }).click();
  await expect(page.getByRole("heading", { name: "收到的家庭邀请" })).toHaveCount(0);
  expect(accepted).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("family-members-mobile.png"), fullPage: true });
});
