import { expect, test } from "@playwright/test";

const list = {
  id: "list",
  title: "旅行准备",
  items: [],
  completed_count: 0,
  total_count: 0,
  pinned: false,
  shared_household_ids: [],
};
const homes = ["第一个家庭", "第二个家庭"].map((name, i) => ({
  id: `home-${i}`,
  name,
  role: "member",
  members: [{ account_id: "member", display_name: "家人", role: "member" }],
}));

test("清单卡片权限入口，顶部移除权限表单", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "owner", email: "owner@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/planning/checklists") json = { items: [list] };
    if (path === "/api/sharing/states")
      json = { states: { "checklist:list": "private" }, editable: ["checklist:list"] };
    if (path === "/api/sharing/options") json = { households: homes };
    if (path === "/api/sharing/checklist/list")
      json =
        route.request().method() === "PUT"
          ? route.request().postDataJSON()
          : { scope: "private", household_id: null, member_ids: [] };
    await route.fulfill({ json });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/checklists");
    await expect(page.locator(".inline-create .sharing-editor")).toHaveCount(0);
    await expect(
      page.locator(".checklist-list").getByRole("button", { name: "自己可见", exact: true }),
    ).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
    await page.screenshot({ path: testInfo.outputPath(`checklist-card-${width}.png`) });
  }
  await page.getByRole("button", { name: "自己可见", exact: true }).click();
  await page.getByRole("button", { name: "谁可以访问" }).click();
  await page
    .getByRole("dialog", { name: "选择选项" })
    .getByRole("button", { name: "家庭可见", exact: true })
    .click();
  await expect(page.getByRole("button", { name: "家庭", exact: true })).toHaveText("第一个家庭");
  await page.getByRole("button", { name: "保存可见范围", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "可见范围" })).toHaveCount(0);
  await expect(
    page.locator(".checklist-list").getByRole("button", { name: "家庭可见", exact: true }),
  ).toBeVisible();
});

for (const creator of [true, false])
  test(`编辑日程回填权限，${creator ? "创建者可修改" : "接收者隐藏权限"}`, async ({
    page,
  }, testInfo) => {
    let contentWrites = 0;
    let policyWrites = 0;
    const event = {
      id: "event",
      title: "聚餐",
      start_date: "2026-09-20",
      end_date: "2026-09-20",
      start_time: "09:00",
      end_time: "10:00",
      status: "scheduled",
      description: "",
      location: "",
      todo_id: null,
    };
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      let json: unknown = { items: [] };
      if (path === "/api/auth/me")
        json = {
          id: creator ? "owner" : "member",
          email: "test@example.test",
          timezone: "Asia/Shanghai",
        };
      if (path === "/api/sharing/states")
        json = { editable: creator ? ["event:event"] : [], states: { "event:event": "household" } };
      if (path === "/api/sharing/options") json = { households: homes };
      if (path === "/api/sharing/event/event") {
        json = { scope: "household", household_id: "home-1", member_ids: [] };
        if (route.request().method() === "PUT") {
          policyWrites++;
          json = route.request().postDataJSON();
        }
      }
      if (path === "/api/calendar/events/event") {
        if (route.request().method() === "PUT") contentWrites++;
        json = event;
      }
      await route.fulfill({ json });
    });
    await page.goto("/calendar/event/edit");
    await expect(page.getByLabel("标题（可选）")).toHaveValue("聚餐");
    if (creator) {
      await expect(page.getByRole("button", { name: "家庭", exact: true })).toHaveText(
        "第二个家庭",
      );
      await page.getByRole("button", { name: "谁可以访问" }).click();
      await page
        .getByRole("dialog", { name: "选择选项" })
        .getByRole("button", { name: "自己可见", exact: true })
        .click();
      await page.setViewportSize({ width: 1280, height: 900 });
      await page.screenshot({ path: testInfo.outputPath("editing-visibility-desktop.png") });
    } else await expect(page.locator(".sharing-fields")).toHaveCount(0);
    await page.getByRole("button", { name: "保存日程", exact: true }).click();
    await expect(page).toHaveURL(/\/calendar\?date=/);
    expect(contentWrites).toBe(1);
    expect(policyWrites).toBe(creator ? 1 : 0);
  });

test("开放创建入口默认自己可见", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me")
      json = { id: "owner", email: "owner@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/life/meal-plans") json = { items: [], preferences: [], pantry: [] };
    if (path === "/api/documents/materials") json = { items: [], folders: [] };
    if (path === "/api/assistant/voice-memos") json = [];
    await route.fulfill({ json });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    for (const path of [
      "/todos/new",
      "/calendar/new",
      "/meals/new",
      "/meals/settings",
      "/daily-dump",
    ]) {
      await page.goto(path);
      await expect(page.getByRole("button", { name: "谁可以访问" })).toHaveText("自己可见");
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
        width,
      );
    }
  }
  await page.goto("/voice-memos");
  await expect(page.locator(".memo-recorder .sharing-editor")).toHaveCount(0);
  await page.goto("/documents");
  await page.getByRole("button", { name: "上传文件", exact: true }).click();
  await expect(page.getByRole("dialog").getByRole("button", { name: "谁可以访问" })).toHaveText(
    "自己可见",
  );
});
