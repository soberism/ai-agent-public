import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";

const account = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@example.com",
  timezone: "Asia/Shanghai",
};

async function setup(page: Page) {
  const state = {
    members: [
      {
        id: "member-1",
        display_name: "我",
        email: account.email,
        role: "owner",
        permissions: [],
        status: "active",
      },
      {
        id: "member-2",
        display_name: "保姆",
        email: "helper@example.com",
        role: "member",
        permissions: [],
        status: "active",
      },
    ],
    notifications: [
      {
        id: "notification-1",
        type: "household_invitation",
        title: "家庭邀请",
        message: "邀请你加入温暖之家",
        read: false,
        created_at: "2026-09-16T00:00:00Z",
        invitation_id: "incoming-1",
      },
    ],
    invitations: [] as Record<string, unknown>[],
    profiles: [] as Record<string, unknown>[],
    pets: [] as Record<string, unknown>[],
    contacts: [] as Record<string, unknown>[],
    groups: [] as Record<string, unknown>[],
    materials: [] as Record<string, unknown>[],
    review: [
      {
        id: "review-1",
        material_id: "material-1",
        material_name: "学校通知.png",
        target_type: "event",
        title: "家长会",
        evidence: "9月20日上午九点召开家长会",
        confidence: 0.92,
        status: "pending",
        target_url: null,
      },
    ],
    meals: [] as Record<string, unknown>[],
    preferences: [] as Record<string, unknown>[],
    pantry: [] as Record<string, unknown>[],
    shopping: [] as Record<string, unknown>[],
    shoppingConfirmed: false,
    appointments: [] as Record<string, unknown>[],
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname.replace(/^\/api/, "");
    const json = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    const body = () => request.postDataJSON() as Record<string, unknown>;
    if (path === "/auth/me") return json(account);
    if (path === "/households/home-1/audit" || path === "/collaboration/assignments")
      return json([]);
    if (path === "/households/home-1/summary") return json({ todos: [] });
    if (path === "/calendar/events") return json({ items: [] });
    if (path === "/todos") return json({ items: [], total: 0 });
    if (path === "/platform/settings") return json({ ...account });
    if (path === "/households") {
      if (request.method() === "POST") return json({ id: "home-1", ...body() }, 201);
      return json({ items: [{ id: "home-1", name: "我们的家", role: "owner", member_count: 1 }] });
    }
    if (path === "/households/home-1")
      return json({
        id: "home-1",
        name: "我们的家",
        role: "owner",
        member_count: 1,
        members: state.members,
        invitations: state.invitations,
        profiles: state.profiles,
        pets: state.pets,
      });
    if (path.endsWith("/invitations")) {
      state.invitations.push({
        id: "invite-1",
        ...body(),
        status: "pending",
        expires_at: "2026-09-17T00:00:00Z",
      });
      return json(state.invitations.at(-1), 201);
    }
    if (path.endsWith("/members/member-2") && request.method() === "PATCH") {
      Object.assign(state.members[1], body());
      return json(state.members[1]);
    }
    if (path === "/households/invitations/incoming") return json({ items: [] });
    if (path === "/notifications") return json({ items: state.notifications });
    if (path === "/households/invitations/incoming-1/accept") return json({ status: "accepted" });
    if (path === "/households/invitations/incoming-1/reject") return json({ status: "rejected" });
    if (path === "/notifications/notification-1/read") {
      state.notifications[0].read = true;
      return json(state.notifications[0]);
    }
    if (path.endsWith("/profiles")) {
      state.profiles.push({ id: "profile-1", ...body() });
      return json(state.profiles.at(-1), 201);
    }
    if (path.endsWith("/pets")) {
      state.pets.push({ id: "pet-1", ...body() });
      return json(state.pets.at(-1), 201);
    }
    if (path === "/contacts") {
      if (request.method() === "POST") {
        state.contacts.push({ id: "contact-1", ...body(), group_ids: [] });
        return json(state.contacts.at(-1), 201);
      }
      return json({ items: state.contacts });
    }
    if (path === "/contact-groups") {
      if (request.method() === "POST") {
        state.groups.push({ id: "group-1", ...body() });
        return json(state.groups.at(-1), 201);
      }
      return json({ items: state.groups });
    }
    if (path === "/documents/materials") {
      if (request.method() === "POST") {
        state.materials.push({
          id: "material-1",
          name: "通知.png",
          kind: "photo",
          status: "processing",
          created_at: "2026-09-16T00:00:00Z",
          folder_id: null,
          error_message: null,
          review_count: 0,
        });
        return json(state.materials.at(-1), 201);
      }
      return json({ items: state.materials, folders: [] });
    }
    if (path === "/documents/capabilities")
      return json({ email: false, local_upload: true, text_extraction: true });
    if (path === "/documents/review-items") return json({ items: state.review });
    if (path.endsWith("/accept")) {
      state.review = [];
      return json({ status: "accepted", target_url: "/calendar/event-1" });
    }
    if (path.includes("/documents/review-items/") && request.method() === "PATCH")
      return json({ ...state.review[0], ...body() });
    if (path === "/life/capabilities")
      return json({ delivery: false, payment: false, medical_booking: false });
    if (path === "/life/meal-plans") {
      if (request.method() === "POST") {
        state.meals.push({
          id: "meal-1",
          ...body(),
          status: "draft",
          calendar_url: null,
          shopping_url: "/shopping/shopping-1",
        });
        return json(state.meals.at(-1), 201);
      }
      return json({ items: state.meals, preferences: state.preferences, pantry: state.pantry });
    }
    if (path === "/life/meal-plans/meal-1/confirm") {
      Object.assign(state.meals[0], { status: "planned", calendar_url: "/calendar/event-1" });
      return json(state.meals[0]);
    }
    if (path === "/life/preferences") {
      state.preferences.push({ id: "preference-1", ...body() });
      return json(state.preferences.at(-1), 201);
    }
    if (path === "/life/pantry") {
      state.pantry.push({ id: "pantry-1", ...body() });
      return json(state.pantry.at(-1), 201);
    }
    if (path === "/life/shopping-lists/shopping-1")
      return json({
        id: "shopping-1",
        title: "本周采购",
        status: state.shoppingConfirmed ? "planned" : "draft",
        checklist_url: state.shoppingConfirmed ? "/checklists/list-1" : null,
        items: state.shopping,
      });
    if (path === "/life/shopping-lists/shopping-1/confirm") {
      state.shoppingConfirmed = true;
      return json({
        id: "shopping-1",
        title: "本周采购",
        status: "planned",
        checklist_url: "/checklists/list-1",
        items: state.shopping,
      });
    }
    if (path === "/life/shopping-lists/shopping-1/items") {
      state.shopping.push({ id: "shop-1", ...body(), origin: "manual", purchased: false });
      return json(
        {
          id: "shopping-1",
          title: "本周采购",
          status: "draft",
          checklist_url: null,
          items: state.shopping,
        },
        201,
      );
    }
    if (path.includes("/life/shopping-lists/shopping-1/items/") && request.method() === "PATCH") {
      Object.assign(state.shopping[0], body());
      return json({
        id: "shopping-1",
        title: "本周采购",
        status: "draft",
        checklist_url: null,
        items: state.shopping,
      });
    }
    if (path === "/life/appointments") {
      if (request.method() === "POST") {
        state.appointments.push({
          id: "appointment-1",
          ...body(),
          status: "planned",
          external_receipt: null,
          calendar_url: null,
          todo_url: null,
        });
        return json(state.appointments.at(-1), 201);
      }
      return json({ items: state.appointments });
    }
    if (path === "/life/appointments/appointment-1/confirm") {
      Object.assign(state.appointments[0], {
        status: "planned",
        calendar_url: "/calendar/event-2",
        todo_url: "/todos/todo-2",
      });
      return json(state.appointments[0]);
    }
    return json({ error: { code: "NOT_FOUND", message: path } }, 404);
  });
  return state;
}

test("功能中心和家庭关系流程在窄屏可用", async ({ page }, testInfo) => {
  const state = await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/features");
  await expect(page.getByRole("heading", { name: "功能中心" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: testInfo.outputPath("features-320.png"),
    fullPage: true,
  });
  await page.goto("/family");
  await page
    .locator("summary")
    .filter({ hasText: /^邀请成员$/ })
    .click();
  const invitationToggle = page.locator("summary").filter({ hasText: /^邀请成员$/ });
  await expect(invitationToggle).toHaveCSS("-webkit-tap-highlight-color", "rgba(0, 0, 0, 0)");
  await expect(invitationToggle).toHaveCSS("user-select", "none");
  await expect(invitationToggle).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await page.getByLabel("邀请邮箱").fill("helper@example.com");
  await page.getByRole("button", { name: "发出站内邀请" }).click();
  await page
    .locator("summary")
    .filter({ hasText: /^已发出邀请/ })
    .click();
  await expect(page.getByText(/helper@example.com · 家庭成员 · 待接受/)).toBeVisible();
  const helper = page.getByRole("article").filter({ hasText: "保姆" });
  await expect(helper.getByText("最小权限")).toHaveCount(0);
  await helper.getByRole("button", { name: "保存角色" }).click();
  expect(state.invitations).toHaveLength(1);
  for (const width of [320, 390, 1280]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: `/tmp/family-layout-${width}.png`, fullPage: true });
  }
  await expect(page.getByRole("heading", { name: "家庭协作" })).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "照护资料" })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/family");
  await expect(page.locator("summary").filter({ hasText: /^邀请成员$/ })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("family-390.png"),
    fullPage: true,
  });
});

test("联系人和分组保持通讯资料边界", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/contacts");
  await expect(page.getByText(/不会自动获得家庭或文档访问权限/)).toBeVisible();
  await page.getByLabel("姓名").fill("张老师");
  await page.getByRole("button", { name: "保存联系人" }).click();
  await expect(page.getByRole("strong").filter({ hasText: "张老师" })).toBeVisible();
  await page.getByLabel("分组名称").fill("学校");
  await page.getByLabel("张老师").check();
  await page.getByRole("button", { name: "创建分组" }).click();
  expect(state.groups).toHaveLength(1);
});

test("上传材料后可审核真实候选项", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/documents");
  await page
    .getByLabel("选择文件")
    .setInputFiles({ name: "通知.png", mimeType: "image/png", buffer: Buffer.from("fixture") });
  await page.getByRole("button", { name: "上传并开始识别" }).click();
  await expect(page.getByText("通知.png")).toBeVisible();
  await page.goto("/document-review");
  await expect(page.getByText("9月20日上午九点召开家长会")).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "openspec/changes/add-document-review-ui/evidence/review-390.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "接受并创建" }).click();
  await expect(page.getByRole("heading", { name: "没有待审核内容" })).toBeVisible();
  expect(state.review).toHaveLength(0);
});

test("餐食购物和医疗仅保存应用内状态", async ({ page }) => {
  const state = await setup(page);
  await page.clock.setFixedTime(new Date("2026-09-17T04:00:00Z"));
  await page.goto("/meals/new");
  await page.getByLabel("日期、餐次和人数", { exact: true }).fill("周末晚餐两个人");
  await page.getByLabel("菜品").fill("番茄炒蛋");
  await page.getByRole("button", { name: "保存餐食" }).click();
  await expect(page.getByText("番茄炒蛋")).toBeVisible();
  await page.getByRole("button", { name: "加入日历" }).click();
  await expect(page.getByRole("link", { name: "查看餐食日程" })).toBeVisible();
  await page.getByRole("link", { name: "购物清单", exact: true }).click();
  await page.getByLabel("商品").fill("番茄");

  await page.getByRole("button", { name: "添加商品" }).click();
  await expect(page.getByText("番茄")).toBeVisible();
  await expect(page.getByRole("button", { name: "生成计划清单" })).toHaveCount(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "openspec/changes/add-life-services-ui/evidence/shopping-390.png",
    fullPage: true,
  });
  await expect(page.getByRole("button", { name: "进入配送" })).toHaveCount(0);
  await page.goto("/appointments");
  await page.getByLabel("就诊人").fill("小明");
  await page.getByLabel("机构").fill("社区医院");
  await page.getByLabel("服务类型").fill("复诊");
  await page.getByRole("button", { name: "期望时间", exact: true }).click();
  await page.getByRole("button", { name: "2026年9月20日", exact: true }).click();
  await page.getByRole("button", { name: "确认时间", exact: true }).click();
  await page.getByRole("button", { name: "保存安排" }).click();
  await expect(page.getByText("应用内计划", { exact: true })).toBeVisible();
  expect(String(state.appointments[0].preferred_at)).toMatch(/Z$/);
  await page.getByRole("button", { name: "加入日程与准备待办" }).click();
  await expect(page.getByText("应用内计划", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "提交真实预约" })).toBeDisabled();
  expect(state.appointments).toHaveLength(1);
});

test("批量审核使用应用弹窗，取消不写入", async ({ page }, testInfo) => {
  await setup(page);
  let writes = 0;
  await page.route("**/api/workflows/document-review/batch", (route) => {
    writes++;
    return route.fulfill({
      status: 503,
      json: { error: { message: "审核暂时失败", code: "SERVICE_UNAVAILABLE" } },
    });
  });
  await page.goto("/document-review");
  await page.getByRole("button", { name: "接受全部", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "接受审核内容" })).toBeVisible();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(writes).toBe(0);
  await page.getByRole("button", { name: "接受全部", exact: true }).click();
  await page.getByRole("button", { name: "接受并写入", exact: true }).click();
  await expect(page.locator(".toast")).toHaveText(/审核暂时失败/);
  await expect(page.locator(".toast")).toBeVisible();
  expect(await page.locator(".toast").evaluate((element) => element.matches(":popover-open"))).toBe(
    true,
  );
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("review-confirm-toast.png") });
});

test("移出成员先展示影响弹窗，取消不修改", async ({ page }, testInfo) => {
  await setup(page);
  let writes = 0;
  await page.route("**/api/households/*/members/member-2/removal-impact", (route) =>
    route.fulfill({ json: { message: "移出后将失去家庭访问权限。" } }),
  );
  await page.route("**/api/households/*/members/member-2", (route) => {
    writes++;
    return route.fulfill({ json: {} });
  });
  await page.goto("/family");
  await page.getByRole("button", { name: "移出家庭", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "移出家庭" })).toBeVisible();
  await expect(page.getByText("移出后将失去家庭访问权限。", { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("member-removal-dialog.png") });
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(writes).toBe(0);
});
