import { expect, test } from "@playwright/test";
import type { Page } from "@playwright/test";
test("首页独立展示今天日程，排序并过滤取消事项", async ({ page }) => {
  const state = await setup(page);
  const day = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai" }).format(new Date());
  await page.clock.install({ time: new Date(`${day}T00:30:00Z`) });
  state.events = [
    {
      id: "late",
      title: "下午安排",
      status: "scheduled",
      start_date: day,
      end_date: day,
      start_time: "15:00",
      end_time: "16:00",
      starts_at: `${day}T07:00:00Z`,
    },
    { id: "cancelled", title: "取消安排", status: "cancelled", starts_at: `${day}T00:00:00Z` },
    {
      id: "early",
      title: "上午安排",
      status: "scheduled",
      start_date: day,
      end_date: day,
      start_time: "09:00",
      end_time: "10:00",
      starts_at: `${day}T01:00:00Z`,
    },
  ];
  await page.goto("/");
  const section = page.locator('section[aria-labelledby="schedule-title"]');
  await expect(section.getByText("2 项日程")).toBeVisible();
  await expect(section.locator("li strong")).toHaveText(["上午安排", "下午安排"]);
  await expect(section.getByText("取消安排")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "今天的待办" })).toBeVisible();
  const attention = page.locator('section[aria-labelledby="attention-title"]');
  await expect(attention.getByRole("link")).toHaveCount(2);
  await expect(attention.getByRole("link", { name: "7 语音备忘" })).toBeVisible();
  for (const name of [
    "文档与材料",
    "餐食计划",
    "购物清单",
    "医疗安排",
    "清单",
    "站内通知",
    "联系人",
    "档案检索",
    "AI 助手",
  ])
    await expect(attention.getByText(name, { exact: true })).toHaveCount(0);
  const upcoming = page.getByRole("link", { name: "1 日程即将开始" });
  await expect(upcoming).toBeVisible();
  await expect(upcoming).toHaveAttribute("href", `/calendar?date=${day}`);
  await page.screenshot({ path: "/tmp/home-today-schedule.png", fullPage: true });
  await page.clock.fastForward(31 * 60 * 1000);
  await expect(page.getByRole("link", { name: "0 日程即将开始" })).toHaveCount(0);
  await expect(attention.getByRole("link")).toHaveCount(1);
});
test("首页关注统计全部为零时隐藏整个区域", async ({ page }) => {
  await setup(page);
  await page.route("**/api/hub/summary", (route) =>
    route.fulfill({
      json: {
        pending_reviews: 0,
        pending_assignments: 0,
        failed_emails: 0,
        connection_issues: 0,
        pending_voice_memos: 0,
      },
    }),
  );
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今天的日程" })).toBeVisible();
  await expect(page.locator('section[aria-labelledby="attention-title"]')).toHaveCount(0);
  await page.screenshot({ path: "/tmp/home-no-attention.png", fullPage: true });
});
test("返回按钮回到实际上一页，直接打开时使用默认入口", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  await page
    .getByRole("link", { name: /^买牛奶/ })
    .first()
    .click();
  await expect(page).toHaveURL(/\/todos\/22222222/);
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.getByRole("link", { name: "全局搜索" }).click();
  await expect(page.getByRole("heading", { name: "全局搜索" })).toBeVisible();
  await page.screenshot({ path: "/tmp/history-back-search.png" });
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  await page.goto("/search");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
});
const account = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@example.com",
  nickname: null as string | null,
  timezone: "Asia/Shanghai",
};
const item = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "买牛奶",
  description: null,
  due_date: null,
  due_time: null,
  timezone: "Asia/Shanghai",
  due_at: null,
  status: "ongoing",
  completed_at: null,
  created_at: "2026-09-14T00:00:00Z",
  updated_at: "2026-09-14T00:00:00Z",
  is_overdue: false,
};
async function setup(page: Page, authenticated = true) {
  const state = {
    authenticated,
    items: [item],
    writes: [] as { key?: string; body: unknown }[],
    unknown: false,
    expire: false,
    toggleDelay: undefined as Promise<void> | undefined,
    timezone: "Asia/Shanghai",
    nickname: null as string | null,
    events: [] as Record<string, unknown>[],
    checklists: [] as Record<string, unknown>[],
  };
  await page.route("**/api/**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    const respond = (body: unknown, status = 200) => route.fulfill({ status, json: body });
    if (path === "/api/hub/summary")
      return respond({
        pending_reviews: 0,
        pending_assignments: 0,
        failed_emails: 0,
        connection_issues: 0,
        pending_voice_memos: 7,
      });
    if (path === "/api/auth/me")
      return state.authenticated
        ? respond({ ...account, nickname: state.nickname })
        : respond({ error: { code: "SESSION_EXPIRED", message: "登录已失效" } }, 401);
    if (path === "/api/auth/login") {
      state.authenticated = true;
      return respond({ ...account, nickname: state.nickname });
    }
    if (path === "/api/auth/logout") {
      state.authenticated = false;
      return route.fulfill({ status: 204 });
    }
    if (state.expire) {
      state.authenticated = false;
      return respond({ error: { code: "SESSION_EXPIRED", message: "登录已失效" } }, 401);
    }
    if (path === "/api/platform/settings") {
      if (request.method() === "PATCH") {
        const body = request.postDataJSON() as {
          timezone?: string;
        };
        if (body.timezone) state.timezone = body.timezone;
        if (body.nickname) state.nickname = body.nickname;
      }
      return respond({
        ...account,
        nickname: state.nickname,
        timezone: state.timezone,
        has_todos: state.items.length > 0,
      });
    }
    if (path === "/api/platform/home")
      return respond({
        timezone: state.timezone,
        server_time: "2026-09-14T04:00:00Z",
        today: { count: state.items.length, items: state.items },
        overdue: { count: 0, items: [] },
        recent: state.items,
      });
    if (path === "/api/calendar/events" && request.method() === "POST") {
      const event = {
        id: "33333333-3333-3333-3333-333333333333",
        ...request.postDataJSON(),
        timezone: state.timezone,
        starts_at: "2026-09-16T01:00:00Z",
        ends_at: "2026-09-16T02:00:00Z",
        created_at: "2026-09-16T00:00:00Z",
        updated_at: "2026-09-16T00:00:00Z",
      };
      state.events = [event];
      return respond(event, 201);
    }
    if (path === "/api/calendar/events") return respond({ items: state.events });
    if (path === "/api/planning/review")
      return respond({
        summary: {
          completed_todos: 1,
          ongoing_todos: 1,
          events: 0,
          checklists: 0,
          open_checklist_items: 0,
        },
        details: { completed: [], ongoing: [], events: [] },
        organize: { overdue: [item], unscheduled: [], conflicts: [] },
      });
    if (path === "/api/planning/reminders") return respond([]);
    if (path === "/api/planning/checklists" && request.method() === "POST") {
      const checklist = {
        id: "44444444-4444-4444-4444-444444444444",
        title: (request.postDataJSON() as { title: string }).title,
        items: [],
        completed_count: 0,
        total_count: 0,
        created_at: "2026-09-16T00:00:00Z",
        updated_at: "2026-09-16T00:00:00Z",
      };
      state.checklists = [checklist];
      return respond(checklist, 201);
    }
    if (path === "/api/planning/checklists") return respond({ items: state.checklists });
    if (path === "/api/planning/checklists/44444444-4444-4444-4444-444444444444")
      return respond(state.checklists[0]);
    if (path.endsWith("/items") && request.method() === "POST") {
      const current = state.checklists[0] as Record<string, unknown>;
      const next = {
        ...current,
        items: [
          {
            id: "55555555-5555-5555-5555-555555555555",
            title: (request.postDataJSON() as { title: string }).title,
            completed: false,
            position: 0,
          },
        ],
        total_count: 1,
      };
      state.checklists = [next];
      return respond(next, 201);
    }
    if (path === "/api/todos" && request.method() === "POST") {
      state.writes.push({
        key: request.headers()["idempotency-key"],
        body: request.postDataJSON(),
      });
      if (state.unknown && state.writes.length === 1) return route.abort("failed");
      return respond({ ...item, ...request.postDataJSON() }, 201);
    }
    if (path === `/api/todos/${item.id}` && request.method() === "PATCH") {
      await state.toggleDelay;
      const result = { ...item, ...request.postDataJSON() };
      state.items = state.items.map((todo) => (todo.id === item.id ? result : todo));
      return respond(result);
    }
    if (path === `/api/todos/${item.id}` && request.method() === "DELETE")
      return request.headers()["content-type"] === "application/json"
        ? route.fulfill({ status: 204 })
        : respond({ error: { code: "UNSUPPORTED_MEDIA_TYPE", message: "请使用JSON请求" } }, 415);
    if (path === "/api/todos")
      return respond({
        items: state.items,
        next_cursor: null,
        server_time: "2026-09-14T04:00:00Z",
      });
    return respond(item);
  });
  return state;
}
test("只接受安全返回地址，未知登录不会显示待办", async ({ page }) => {
  await setup(page, false);
  await page.goto("/login?returnTo=//evil.example");
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
});
test("登录返回保留站内查询和锚点", async ({ page }) => {
  await setup(page, false);
  await page.goto("/login?returnTo=%2Fsettings%3Ftab%3Daccount%23timezone");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL(/\/settings\?tab=account#timezone$/);
});
test("首页使用真实摘要并开放生活功能入口", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今天，一起安排好" })).toBeVisible();
  await expect(page.getByText("1 项待办")).toBeVisible();
  await expect(page.getByRole("button", { name: /全局搜索/ })).toBeDisabled();
  await expect(page.getByRole("link", { name: /家庭/ })).toHaveAttribute("href", "/family");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test("账号头像使用稳定首字和配色", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  const avatar = page.getByRole("link", { name: "打开设置" }).locator(".avatar");
  await expect(avatar).toHaveText("D");
  await expect(avatar).toHaveClass(/avatar-tone-1/);
});

test("设置昵称后头像立即使用昵称首字", async ({ page }) => {
  await setup(page);
  await page.goto("/settings");
  await page.getByLabel("昵称").fill("小赵");
  await page.getByRole("button", { name: "保存设置" }).click();
  await expect(page.getByRole("status")).toHaveText("设置已更新");
  await page.goto("/");
  await expect(page.getByRole("link", { name: "打开设置" }).locator(".avatar")).toHaveText("小");
});
test("修改密码校验并重新登录", async ({ page }) => {
  await setup(page);
  let submitted: Record<string, string> | undefined;
  await page.route("**/api/auth/password", async (route) => {
    submitted = route.request().postDataJSON() as Record<string, string>;
    await route.fulfill({ status: 204 });
  });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/settings");
  const change = await page.getByRole("button", { name: "修改密码" }).boundingBox();
  const deactivate = await page.getByRole("button", { name: "注销账号" }).boundingBox();
  expect(change?.y).toBe(deactivate?.y);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "修改密码" }).click();
  await expect(page.getByRole("dialog", { name: "修改密码" })).toBeVisible();
  await page.getByLabel("原密码").fill("原密码1234567890");
  await page.getByLabel("新密码", { exact: true }).fill("新密码1234567890");
  await page.getByLabel("确认新密码").fill("不同密码1234567890");
  await page.getByRole("button", { name: "确认修改" }).click();
  await expect(page.getByRole("alert")).toContainText("两次密码输入不一致");
  expect(submitted).toBeUndefined();
  await page.getByLabel("确认新密码").fill("新密码1234567890");
  await page.getByRole("button", { name: "确认修改" }).click();
  await expect(page).toHaveURL(/\/login/);
  expect(submitted).toEqual({
    current_password: "原密码1234567890",
    new_password: "新密码1234567890",
    confirm_password: "新密码1234567890",
  });
});
test("平台首页与设置在手机视口保持完整", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "今天，一起安排好" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: "openspec/changes/add-platform-app-shell/evidence/home-320.png",
  });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/settings");
  await expect(page.getByRole("heading", { name: "设置" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({
    path: "openspec/changes/add-platform-app-shell/evidence/settings-390.png",
  });
});
test("计划入口可创建本地日程且手机视口无溢出", async ({ page }) => {
  const state = await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/plan");
  await page.getByRole("link", { name: /日程/ }).click();
  await expect(page.getByRole("heading", { name: "日程", exact: true })).toBeVisible();
  await page.getByRole("link", { name: "新建日程" }).first().click();
  await page.getByLabel("标题").fill("社区读书会");
  await page.getByLabel("开始日期").fill("2026-09-16");
  await page.getByLabel("结束日期").fill("2026-09-16");
  await page.getByRole("button", { name: "保存日程" }).click();
  await expect(page).toHaveURL(/\/calendar\?date=2026-09-16$/);
  expect(state.events).toHaveLength(1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test("日程支持日周和当月全部，周视图纵向复用日程列表", async ({ page }) => {
  const state = await setup(page);
  state.events = [
    {
      id: "overlap",
      title: "跨月日程",
      start_date: "2026-08-31",
      end_date: "2026-09-01",
      start_time: "22:00",
      end_time: "08:00",
      status: "scheduled",
    },
    {
      id: "prior-week",
      title: "周末跨周日程",
      start_date: "2026-09-13",
      end_date: "2026-09-14",
      start_time: "22:00",
      end_time: "08:00",
      status: "scheduled",
    },
    {
      id: "early",
      title: "早餐",
      start_date: "2026-09-16",
      end_date: "2026-09-16",
      start_time: "07:00",
      end_time: "08:00",
      status: "scheduled",
      location: "厨房",
    },
    {
      id: "long",
      title: "长标题日程".repeat(8),
      start_date: "2026-09-17",
      end_date: "2026-09-18",
      start_time: "09:00",
      end_time: "10:00",
      status: "cancelled",
    },
  ];
  await page.goto("/calendar?date=2026-09-16");
  await expect(page.getByRole("group", { name: "日历视图" }).getByRole("button")).toHaveText([
    "日",
    "周",
    "全部",
  ]);
  await expect(page.locator(".event-list strong")).toHaveText(["早餐"]);
  await page.getByRole("button", { name: "周", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "2026-09-14 至 2026-09-20 的日程" }),
  ).toBeVisible();
  const week = page.getByLabel("周日历", { exact: true });
  await expect(week.locator("section")).toHaveCount(7);
  await expect(week.getByText("暂无日程", { exact: true })).toHaveCount(4);
  await expect(week.locator("section").first().getByText("周末跨周日程")).toBeVisible();
  await expect(week.locator(".event-list strong")).toHaveText([
    "周末跨周日程",
    "早餐",
    "长标题日程".repeat(8),
  ]);
  await expect(week.getByText("已取消")).toBeVisible();
  await expect(week.getByText("09:00–2026-09-18 10:00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "全部", exact: true }).click();
  await expect(page.getByRole("heading", { name: "2026-09 全部日程" })).toBeVisible();
  await expect(page.locator(".event-list strong")).toHaveText([
    "跨月日程",
    "周末跨周日程",
    "早餐",
    "长标题日程".repeat(8),
  ]);
  await page.getByRole("button", { name: "周", exact: true }).click();
  for (const width of [320, 390, 960]) {
    await page.setViewportSize({ width, height: 844 });
    const sections = await week.locator("section").first().boundingBox();
    expect(sections).not.toBeNull();
    const boxes = await week.locator("section").evaluateAll((nodes) =>
      nodes.map((node) => {
        const rect = node.getBoundingClientRect();
        return { x: rect.x, y: rect.y, bottom: rect.bottom };
      }),
    );
    for (let index = 1; index < boxes.length; index++) {
      expect(boxes[index].x).toBe(boxes[0].x);
      expect(boxes[index].y).toBeGreaterThanOrEqual(boxes[index - 1].bottom);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/calendar-week-${width}.png`, fullPage: true });
  }
  await week.getByRole("link", { name: /早餐/ }).click();
  await expect(page).toHaveURL(/\/calendar\/early\/edit$/);
});
test("自定义必填校验使用Toast，重复提交仍提示", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/todos/new");
  const submit = page.getByRole("button", { name: "添加待办", exact: true });
  await submit.click();
  const toast = page.locator(".toast.error");
  await expect(toast).toBeVisible();
  expect(state.writes).toHaveLength(0);
  await page.getByRole("button", { name: "关闭提示" }).click();
  await expect(toast).toBeHidden();
  await submit.click();
  await expect(toast).toBeVisible();
  expect(state.writes).toHaveLength(0);
});

test("计划入口可创建清单和清单项", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/checklists");
  await page.getByLabel("清单名称").fill("旅行准备");
  await page.getByRole("button", { name: "新建" }).click();
  await page.getByLabel("清单项").fill("带护照");
  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.getByText("带护照")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
test("待办可安排时间块且整理页展示真实统计", async ({ page }) => {
  const state = await setup(page);
  await page.goto(`/todos/${item.id}`);
  await page.getByRole("link", { name: "安排到日历" }).click();
  await expect(page.getByLabel("标题")).toHaveValue(item.title);
  await page.getByLabel("开始日期").fill("2026-09-16");
  await page.getByLabel("结束日期").fill("2026-09-16");
  await page.getByRole("button", { name: "保存日程" }).click();
  expect(state.events).toHaveLength(1);
  await page.goto("/review");
  await expect(page.getByRole("heading", { name: "计划回顾" })).toBeVisible();
  await expect(page.getByText("买牛奶")).toBeVisible();
});
test("离线时显示全局状态且不伪装成功", async ({ context, page }) => {
  await setup(page);
  await page.goto("/");
  await context.setOffline(true);
  await expect(page.getByText("当前处于离线状态，部分内容可能无法更新。")).toBeVisible();
  await context.setOffline(false);
  await expect(page.getByText("当前处于离线状态，部分内容可能无法更新。")).toHaveCount(0);
});
test("账号登录后直接进入首页", async ({ page }) => {
  await setup(page);
  await page.goto("/");
  await expect(page).toHaveURL(/\/$/);
  await expect(page.getByRole("heading", { name: "今天，一起安排好" })).toBeVisible();
  await page.screenshot({ path: "/tmp/home-without-onboarding.png" });
});
test("不存在页面精简文案并垂直居中", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/not-found");
  await expect(page.getByText("这个地址暂时没有内容。")).toHaveCount(0);
  const [headingBox, linkBox] = await Promise.all([
    page.getByRole("heading", { name: "页面不存在" }).boundingBox(),
    page.getByRole("button", { name: "返回" }).boundingBox(),
  ]);
  expect(Math.abs((headingBox!.y + linkBox!.y + linkBox!.height) / 2 - 422)).toBeLessThan(2);
  await page.screenshot({ path: "/tmp/not-found-centered.png" });
});
test("触屏按钮点击后不保留焦点选中态", async ({ browser }) => {
  const context = await browser.newContext({
    hasTouch: true,
    viewport: { width: 390, height: 844 },
  });
  const page = await context.newPage();
  await setup(page);
  await page.goto("/todos");
  const filter = page.getByRole("button", { name: "筛选", exact: true });
  await filter.tap();
  await page.getByRole("button", { name: "关闭筛选待办", exact: true }).tap();
  await expect(filter).toBeFocused();
  await expect(filter).toHaveCSS("outline-style", "none");
  await page.screenshot({ path: "/tmp/mobile-button-without-focus-state.png" });
  await context.close();
});
test("创建响应未知锁定原载荷，同键核对只展示确认结果", async ({ page }) => {
  const state = await setup(page);
  state.unknown = true;
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: false }).fill("买牛奶");
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page.getByRole("button", { name: "核对并重试" })).toBeVisible();
  await expect(page.getByLabel("标题", { exact: false })).toBeDisabled();
  await page.getByRole("button", { name: "核对并重试" }).click();
  await expect(page).toHaveURL(/\/todos$/);
  expect(state.writes).toHaveLength(2);
  expect(state.writes[0]).toEqual(state.writes[1]);
  expect(state.writes[0].key).toMatch(/^[0-9a-f-]{36}$/);
});
test("浏览器后退经过脏表单确认，继续编辑保留内容", async ({ page }) => {
  await setup(page);
  await page.goto("/todos");
  await page.getByRole("link", { name: "新建待办" }).click();
  await page.getByLabel("标题", { exact: false }).fill("未保存");
  await page.goBack();
  await expect(page.getByRole("dialog", { name: "放弃本次修改？" })).toBeVisible();
  await page.getByRole("button", { name: "继续编辑", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: false })).toHaveValue("未保存");
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await page.getByRole("button", { name: "放弃修改", exact: true }).click();
  await expect(page).toHaveURL(/\/todos$/);
});
test("过期后同账号不恢复未保存内容，不自动重发写请求", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: false }).fill("会话草稿");
  state.expire = true;
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  state.expire = false;
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: false })).toHaveValue("");
  await expect(page.getByRole("dialog", { name: "恢复未保存的草稿？" })).toHaveCount(0);
  expect(state.writes).toHaveLength(0);
});

test("局域网HTTP环境不支持randomUUID时仍可添加待办", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(globalThis.crypto, "randomUUID", { value: undefined });
  });
  const state = await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: true }).fill("局域网新建待办");
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page).toHaveURL(/\/todos$/);
  expect(state.writes).toHaveLength(1);
  expect(state.writes[0].key).toMatch(
    /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
  );
});
test("月历周一开始、Unicode校验、清日期同时清时间", async ({ page }) => {
  await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: false }).fill("😀".repeat(100));
  await expect(page.getByRole("button", { name: "添加待办", exact: true })).toBeEnabled();
  await page.getByLabel("标题", { exact: false }).fill("😀".repeat(101));
  await expect(page.getByRole("button", { name: "添加待办", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "明天", exact: true }).click();
  await page.getByLabel("截止时间", { exact: false }).fill("18:00");
  await page.getByRole("button", { name: "不设截止日期", exact: true }).click();
  await expect(page.getByLabel("截止时间", { exact: false })).toHaveValue("");
  await expect(page.getByLabel("截止时间", { exact: false })).toBeDisabled();
  await page.getByRole("button", { name: "打开周一开始的月历" }).click();
  await expect(page.locator(".calendar > span").first()).toHaveText("周一");
  await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
  await expect(page.getByRole("dialog", { name: "选择截止日期" })).toHaveCSS(
    "overscroll-behavior",
    "contain",
  );
});
test("详情页左上角统一显示返回", async ({ page }) => {
  await setup(page);
  await page.goto(`/todos/${item.id}`);
  await expect(page.locator(".page-header .back")).toHaveAccessibleName("返回");
});
test("编辑后保留列表并用接口结果直接更新", async ({ page }) => {
  await setup(page);
  await page.goto("/todos");
  await page.getByRole("link", { name: /买牛奶/ }).press("Enter");
  await page.getByRole("link", { name: "编辑", exact: true }).click();
  await page.getByLabel("标题", { exact: true }).fill("买鲜奶");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await page.getByRole("button", { name: "返回", exact: true }).click();
  await expect(page.getByText("买鲜奶", { exact: true })).toBeVisible();
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0);
});
test("状态首次切换显示加载，后续切换保留各自旧数据并刷新", async ({ page }) => {
  await setup(page);
  await page.goto("/todos");
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  let release: (() => void) | undefined;
  await page.route("**/api/todos?**", async (route) => {
    if (new URL(route.request().url()).searchParams.get("status") !== "completed")
      return route.fallback();
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({
      json: {
        items: [{ ...item, title: "已完成事项", status: "completed" }],
        next_cursor: null,
        server_time: "2026-09-14T04:00:00Z",
      },
    });
  });
  await page.getByRole("button", { name: "已完成", exact: true }).click();
  await expect(page.getByRole("status")).toContainText("加载中");
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0);
  await expect.poll(() => Boolean(release)).toBe(true);
  release?.();
  await expect(page.getByText("已完成事项", { exact: true })).toBeVisible();
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "进行中", exact: true }).click();
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  release = undefined;
  await page.getByRole("button", { name: "已完成", exact: true }).click();
  await expect(page.getByText("已完成事项", { exact: true })).toBeVisible();
  await expect(page.getByRole("status")).toHaveCount(0);
  await expect.poll(() => Boolean(release)).toBe(true);
  release?.();
});
test("失败不是空列表，320px长标题不溢出", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/todos");
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.route("**/api/todos?**", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: "SERVICE_UNAVAILABLE", message: "服务不可用" } },
    }),
  );
  await page.reload();
  await expect(page.getByText("待办加载失败，请重试", { exact: true })).toBeVisible();
  await expect(page.getByText("暂时没有待办", { exact: true })).toHaveCount(0);
});

test("标记完成处理中按钮仅置灰", async ({ page }) => {
  const state = await setup(page);
  state.items.push({ ...item, id: "33333333-3333-3333-3333-333333333333", title: "倒垃圾" });
  let release!: () => void;
  state.toggleDelay = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.goto("/todos");
  const control = page.getByRole("button", { name: "标记完成：买牛奶", exact: true });
  await control.press("Enter");
  const loading = page.getByRole("button", { name: "标记完成：买牛奶", exact: true });
  await expect(loading).toBeDisabled();
  await expect(loading.locator(".status-spinner")).toHaveCount(0);
  await page.screenshot({ path: "/tmp/todo-toggle-disabled.png" });
  release();
  const toast = page.getByRole("status").filter({ hasText: "已标记完成" });
  await expect(toast).toBeVisible();
  const completed = page.getByRole("button", { name: "恢复未完成：买牛奶", exact: true });
  await expect(completed).toHaveAttribute("aria-pressed", "true");
  expect(
    await completed.evaluate((element) => getComputedStyle(element, "::before").backgroundColor),
  ).toBe("rgb(101, 83, 166)");
  await page.screenshot({ path: "/tmp/todo-checked-before-removal.png" });
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0, { timeout: 2000 });
  await expect(page.getByText("倒垃圾", { exact: true })).toBeVisible();
  await expect(toast).toHaveCSS("position", "fixed");
  const [headerBox, toastBox] = await Promise.all([
    page.locator(".page-header").boundingBox(),
    toast.boundingBox(),
  ]);
  expect(toastBox!.y).toBeGreaterThanOrEqual(headerBox!.y + headerBox!.height);
  expect(toastBox!.height).toBeLessThanOrEqual(46);
  await page.waitForTimeout(200);
  await page.screenshot({ path: "/tmp/todo-success-toast.png" });
  await expect(toast).toBeHidden({ timeout: 4000 });
});
test("已完成待办显示实心对勾", async ({ page }) => {
  await setup(page);
  await page.route("**/api/todos?**", (route) =>
    route.fulfill({
      status: 200,
      json: {
        items: [{ ...item, status: "completed", completed_at: "2026-09-14T05:00:00Z" }],
        next_cursor: null,
        server_time: "2026-09-14T04:00:00Z",
      },
    }),
  );
  await page.goto("/todos?status=completed");
  const control = page.getByRole("button", { name: "恢复未完成：买牛奶", exact: true });
  await expect(control).toHaveAttribute("aria-pressed", "true");
  expect(
    await control.evaluate((element) => {
      const style = getComputedStyle(element, "::before");
      return { background: style.backgroundColor, content: style.content };
    }),
  ).toEqual({ background: "rgb(101, 83, 166)", content: '"✓"' });
  await page.screenshot({ path: "/tmp/completed-todo-control.png" });
});
test("页面滚动时导航栏保持吸顶", async ({ page }) => {
  await setup(page);
  await page.route("**/api/todos?**", (route) =>
    route.fulfill({
      json: {
        items: Array.from({ length: 20 }, (_, index) => ({
          ...item,
          id: `22222222-2222-2222-2222-${String(index).padStart(12, "0")}`,
          title: `待办 ${index + 1}`,
        })),
        next_cursor: null,
        server_time: "2026-09-14T04:00:00Z",
      },
    }),
  );
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/todos");
  await expect(page.getByText("待办 20", { exact: true })).toBeVisible();
  await page.evaluate(() => scrollTo(0, document.body.scrollHeight));

  const header = page.locator(".page-header");
  await expect(header).toBeInViewport();
  await expect.poll(() => header.evaluate((node) => node.getBoundingClientRect().top)).toBe(0);
  await page.screenshot({ path: "/tmp/todo-sticky-header.png" });
});
test("再次进入待办时保留旧数据并后台刷新", async ({ page }) => {
  await setup(page);
  let release!: () => void;
  let requests = 0;
  let blockRefresh = false;
  await page.route("**/api/todos?**", async (route) => {
    requests += 1;
    if (blockRefresh)
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    await route.fulfill({
      json: { items: [item], next_cursor: null, server_time: "2026-09-14T04:00:00Z" },
    });
  });
  await page.goto("/todos");
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  const initialRequests = requests;
  blockRefresh = true;
  await page.getByRole("link", { name: "功能", exact: true }).click();
  await page.getByRole("link", { name: "待办", exact: true }).click();

  await expect(page.getByText("加载中", { exact: true })).toHaveCount(0);
  await expect(page.getByText("暂时没有待办", { exact: true })).toHaveCount(0);
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "进行中", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "已完成", exact: true })).toBeVisible();
  release();
  await expect.poll(() => requests).toBeGreaterThan(initialRequests);
});
test("登录限流倒计时及注册部分成功不会假登录", async ({ page }) => {
  await setup(page, false);
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "3" },
      json: { error: { code: "RATE_LIMITED", message: "操作过于频繁，请稍后再试" } },
    }),
  );
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: /秒后重试/ })).toBeDisabled();
  await expect(page.getByRole("button", { name: "登录", exact: true })).toBeEnabled({
    timeout: 5000,
  });
  await page.getByRole("link", { name: "去注册" }).click();
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: { code: "ACCOUNT_CREATED_LOGIN_REQUIRED", message: "账号已创建，请重新登录" },
      },
    }),
  );
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("确认密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("邮箱验证码", { exact: true }).fill("012345");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByText("账号已创建，请重新登录", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "创建账号", exact: true })).toBeDisabled();
});
test("切换账号后不恢复草稿，受保护视图重新激活先验证", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: true }).fill("原账号秘密草稿");
  state.expire = true;
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  state.expire = false;
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({
      json: { ...account, id: "33333333-3333-3333-3333-333333333333", email: "other@example.com" },
    }),
  );
  await page.getByLabel("邮箱", { exact: true }).fill("other@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("");
  await expect(page.getByRole("dialog", { name: "恢复未保存的草稿？" })).toHaveCount(0);
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
});
test("筛选立即生效且迟到旧查询不覆盖新筛选", async ({ page }) => {
  await setup(page);
  let release: (() => void) | undefined;
  await page.route("**/api/todos?**", async (route) => {
    const due = new URL(route.request().url()).searchParams.get("due");
    if (due === "today")
      await new Promise<void>((resolve) => {
        release = resolve;
      });
    await route.fulfill({
      json: {
        items: due === "none" ? [{ ...item, title: "无日期新查询" }] : [item],
        next_cursor: null,
        server_time: "2026-09-14T04:00:00Z",
      },
    });
  });
  await page.goto("/todos");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await page.getByRole("button", { name: "今天", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "筛选待办" })).toHaveCount(0);
  await expect(page.locator(".list-toolbar")).toContainText("今天");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await page.getByRole("button", { name: "不设截止日期", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "筛选待办" })).toHaveCount(0);
  await expect(page.getByText("无日期新查询", { exact: true })).toBeVisible();
  release?.();
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0);
});
test("列表筛选样式轻量且右侧按钮确认后删除", async ({ page }) => {
  await setup(page);
  await page.goto("/todos");
  await expect(page.locator(".todo-list")).toHaveCSS("overflow", "hidden");
  const assistantLink = page.getByRole("link", { name: "AI 对话", exact: true });
  await expect(assistantLink).toHaveCSS("text-decoration-line", "none");
  await expect(assistantLink).toHaveCSS("min-height", "44px");
  await expect(page.getByText("›", { exact: true })).toHaveCount(0);
  const summary = page.locator(".filter-summary");
  await expect(summary).toHaveCSS("background-color", "rgb(238, 233, 251)");
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "筛选待办" })).toBeFocused();
  await expect(page.getByRole("button", { name: "关闭筛选待办" })).not.toBeFocused();
  for (const option of await page.locator(".filter-options button").all()) {
    expect((await option.boundingBox())!.height).toBe(44);
  }
  await page.screenshot({ path: "/tmp/modal-without-close-focus-ring.png" });
  await page.keyboard.press("Tab");
  await expect(page.getByRole("button", { name: "关闭筛选待办" })).toBeFocused();
  const modalActions = page.locator(".modal-actions");
  await expect(modalActions).toHaveCSS("display", "flex");
  await expect(page.getByRole("button", { name: "应用筛选", exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "重置", exact: true })).toBeVisible();
  const selectedFilter = page.getByRole("button", { name: "全部", exact: true });
  await expect(selectedFilter).toHaveCSS("background-color", "rgb(238, 233, 251)");
  await expect(selectedFilter).not.toContainText("✓");
  await page.getByRole("button", { name: "关闭筛选待办", exact: true }).click();
  const remove = page.getByRole("button", { name: "删除待办“买牛奶”" });
  await expect(remove).toBeVisible();
  await expect(remove).toHaveCSS("min-height", "44px");
  await page.screenshot({
    path: "openspec/changes/add-authenticated-todos/evidence/todos-delete-button-390.png",
  });
  await remove.click();
  await expect(page.getByRole("dialog", { name: "删除待办" })).toBeVisible();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.getByText("待办已删除", { exact: true })).toBeVisible();
  await expect(page.getByText("买牛奶", { exact: true })).toHaveCount(0);
});
test("删除失败关闭确认框并使用Toast提示", async ({ page }) => {
  await setup(page);
  await page.route(`**/api/todos/${item.id}`, (route) =>
    route.fulfill({
      status: 403,
      json: { error: { code: "FORBIDDEN", message: "请求被拒绝" } },
    }),
  );
  await page.goto("/todos");
  await page.getByRole("button", { name: "删除待办“买牛奶”" }).focus();
  await page.getByRole("button", { name: "删除待办“买牛奶”" }).click();
  await page.getByRole("button", { name: "确认删除" }).click();
  await expect(page.getByRole("dialog", { name: "删除待办" })).toHaveCount(0);
  await expect(page.getByRole("alert")).toContainText("删除失败，请重试");
  await expect(page.getByRole("alert")).toHaveCSS("background-color", "rgb(255, 240, 239)");
  await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
  await page.screenshot({ path: "/tmp/todo-delete-error-toast.png" });
});
test("具体截止时间随创建载荷保存，下周一按自然周计算", async ({ page }) => {
  const state = await setup(page);
  await page.clock.install({ time: new Date("2026-09-13T04:00:00Z") });
  await page.goto("/todos/new");
  await page.getByRole("button", { name: "下周一", exact: true }).click();
  await expect(page.getByLabel("截止日期", { exact: true })).toHaveValue("2026-09-14");
  await page.clock.setFixedTime(new Date("2026-09-14T04:00:00Z"));
  await page.getByRole("button", { name: "下周一", exact: true }).click();
  await expect(page.getByLabel("截止日期", { exact: true })).toHaveValue("2026-09-21");
  await page.getByLabel("标题", { exact: true }).fill("明天十八点");
  await page.getByLabel("截止时间", { exact: true }).fill("18:00");
  await page.getByLabel("截止时间", { exact: true }).blur();
  await expect(page.getByLabel("截止时间", { exact: true })).toHaveValue("18:00");
  await expect(page.getByRole("button", { name: "清空", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page).toHaveURL(/\/todos$/);
  expect(state.writes[0].body).toMatchObject({ due_time: "18:00", due_date: "2026-09-21" });
});
test("登录切换注册后立即输入不会落到旧表单", async ({ page }) => {
  await setup(page, false);
  let submitted: Record<string, string> | undefined;
  await page.route("**/api/auth/register", (route) => {
    submitted = route.request().postDataJSON();
    return route.fulfill({ status: 201, json: account });
  });
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  await page.screenshot();
  await page.getByRole("link", { name: "去注册", exact: true }).click();
  await page.getByLabel("邮箱", { exact: true }).fill("immediate@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("确认密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("邮箱验证码", { exact: true }).fill("012345");
  await expect(page.getByLabel("邮箱", { exact: true })).toHaveValue("immediate@example.com");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page).toHaveURL(/\/$/);
  expect(submitted?.email).toBe("immediate@example.com");
});
test("登录等待时禁止链接切换，浏览器后退后迟到成功不建立旧账号", async ({ page }) => {
  await setup(page, false);
  let release: (() => void) | undefined;
  let requested = false;
  await page.route("**/api/auth/login", async (route) => {
    requested = true;
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({ json: account }).catch(() => {});
  });
  await page.goto("/register");
  await page.getByRole("link", { name: "去登录", exact: true }).click();
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect.poll(() => requested).toBe(true);
  await expect(page.getByRole("link", { name: "去注册", exact: true })).toHaveAttribute(
    "aria-disabled",
    "true",
  );
  await page.goBack();
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  release?.();
  await expect(page.getByRole("heading", { name: "创建你的账号" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "待办", exact: true })).toHaveCount(0);
});
test("越界日期显示中文错误且不可提交", async ({ page }) => {
  await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: true }).fill("日期边界");
  await page.getByLabel("截止日期", { exact: true }).fill("0001-01-01");
  await expect(page.getByText("请选择有效的日期和时间", { exact: true })).toBeVisible();
  await expect(page.getByLabel("截止日期", { exact: true })).toHaveCSS(
    "border-color",
    "rgb(101, 83, 166)",
  );
  await expect(page.getByLabel("截止日期", { exact: true })).toHaveCSS("outline-style", "none");
  await expect(page.getByLabel("截止日期", { exact: true })).toHaveCSS(
    "box-shadow",
    "rgba(101, 83, 166, 0.18) 0px 0px 0px 3px",
  );
  await page.screenshot({ path: "/tmp/input-focus-ring.png" });
  await expect(page.getByRole("button", { name: "添加待办", exact: true })).toBeDisabled();
  await page.getByRole("heading", { name: "新建待办" }).click();
  await page.screenshot({ path: "/tmp/input-error-without-border.png" });
});
test("登录POST期间焦点核验延后，Cookie成功后以me同步身份", async ({ page }) => {
  const state = await setup(page, false);
  let release: (() => void) | undefined;
  let requested = false;
  let meChecks = 0;
  await page.route("**/api/auth/me", (route) => {
    meChecks++;
    return route.fulfill({
      status: state.authenticated ? 200 : 401,
      json: state.authenticated
        ? account
        : { error: { code: "SESSION_EXPIRED", message: "登录已失效" } },
    });
  });
  await page.route("**/api/auth/login", async (route) => {
    requested = true;
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    state.authenticated = true;
    await route.fulfill({ json: account });
  });
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect.poll(() => requested).toBe(true);
  const before = meChecks;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  expect(meChecks).toBe(before);
  release?.();
  await expect(page.getByRole("heading", { name: "今天，一起安排好" })).toBeVisible();
  await expect.poll(() => meChecks).toBeGreaterThan(before);
});

for (const path of ["/todos/new", `/todos/${item.id}/edit`]) {
  test(`统一日期月历：${path}`, async ({ page }) => {
    await setup(page);
    await page.goto(path);
    const date = page.getByLabel("截止日期", { exact: true });
    await date.fill("2026-09-21");
    await date.click();
    const calendar = page.getByRole("dialog", { name: "选择截止日期" });
    await expect(calendar).toBeVisible();
    await expect(page.locator('input[type="date"]')).toHaveCount(0);
    await expect(calendar.locator(".calendar > span").first()).toHaveText("周一");
    await expect(
      calendar.getByRole("button", { name: "2026-09-21日", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    await calendar.getByRole("button", { name: "2026-09-22日", exact: true }).click();
    await expect(date).toHaveValue("2026-09-22");
    await expect(date).not.toBeFocused();
    await date.focus();
    await date.press("ArrowDown");
    await expect(calendar).toBeVisible();
    await page.keyboard.press("Escape");
    const calendarButton = page.getByRole("button", { name: "打开周一开始的月历" });
    await calendarButton.click();
    await expect(
      calendar.getByRole("button", { name: "2026-09-22日", exact: true }),
    ).toHaveAttribute("aria-pressed", "true");
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      if (path === "/todos/new")
        await page.screenshot({
          path: `openspec/changes/add-authenticated-todos/evidence/calendar-unified-${width}.png`,
        });
    }
    await page.keyboard.press("Escape");
    await expect(calendarButton).toBeFocused();
    await page.getByLabel("截止时间", { exact: true }).fill("18:00");
    await page.getByRole("button", { name: "不设截止日期", exact: true }).click();
    await expect(date).toHaveValue("");
    await expect(page.getByLabel("截止时间", { exact: true })).toHaveValue("");
    await expect(page.getByLabel("截止时间", { exact: true })).toBeDisabled();
    await date.fill("invalid");
    await date.click();
    await expect(calendar).toBeVisible();
    await expect(calendar).not.toContainText("NaN");
  });
}

test("已登录后台校验不卸载表单，保持输入焦点；401仍跳转登录", async ({ page }) => {
  await setup(page);
  await page.goto("/todos/new");
  const title = page.getByLabel("标题", { exact: true });
  await title.fill("切回窗口继续编辑");
  await title.focus();
  let release!: () => void;
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/auth/me", async (route) => {
    await held;
    await route.fulfill({ json: account });
  });
  const started = page.waitForRequest("**/api/auth/me");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await started;
  await expect(title).toBeVisible();
  await expect(title).toBeFocused();
  await expect(title).toHaveValue("切回窗口继续编辑");
  const response = page.waitForResponse("**/api/auth/me");
  release();
  await response;
  await expect(title).toBeFocused();
  await expect(title).toHaveValue("切回窗口继续编辑");
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ status: 401, json: { error: { message: "登录已失效" } } }),
  );
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
});

test("后台校验识别账号变化时清除原账号表单", async ({ page }) => {
  await setup(page);
  await page.goto("/todos/new");
  await page.getByLabel("标题", { exact: true }).fill("原账号内容");
  await page.route("**/api/auth/me", (route) =>
    route.fulfill({ json: { ...account, id: "other-account" } }),
  );
  const response = page.waitForResponse("**/api/auth/me");
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await response;
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue("");
});

for (const [path, heading, authenticated, field] of [
  ["/login", "登录安排儿", false, "邮箱"],
  ["/register", "创建你的账号", false, "邮箱"],
  ["/todos", "待办", true, ""],
  [`/todos/${item.id}`, "待办详情", true, ""],
  ["/todos/new", "新建待办", true, "标题"],
  [`/todos/${item.id}/edit`, "编辑待办", true, "标题"],
] as const) {
  test(`页面稳定性：${path}`, async ({ page }) => {
    await setup(page, authenticated);
    await page.goto(path);
    const title = page.getByRole("heading", { name: heading, exact: true });
    await expect(title).toBeVisible();
    if (path === "/todos") await expect(page.getByText("买牛奶", { exact: true })).toBeVisible();
    if (path === `/todos/${item.id}`) await expect(page.locator("article.detail")).toBeVisible();
    const input = field ? page.getByLabel(field, { exact: true }) : null;
    if (path === "/todos/new") {
      await expect(page.getByText("请输入待办标题", { exact: true })).toHaveCount(0);
    }
    if (input) {
      await input.fill(field === "邮箱" ? "demo@example.com" : "保留正在编辑的内容");
      await input.click();
    }
    const node = await (input || title).elementHandle();
    let release!: () => void;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/auth/me", async (route) => {
      await held;
      await route.fulfill({
        status: authenticated ? 200 : 401,
        json: authenticated ? account : { error: { message: "未登录" } },
      });
    });
    const started = page.waitForRequest("**/api/auth/me");
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await started;
    await expect(title).toBeVisible();
    expect(await node!.evaluate((element) => element.isConnected)).toBe(true);
    if (input) {
      await input.click();
      await expect(input).toBeFocused();
    }
    const response = page.waitForResponse("**/api/auth/me");
    release();
    await response;
    await expect(title).toBeVisible();
    expect(await node!.evaluate((element) => element.isConnected)).toBe(true);
    if (input) {
      await expect(input).toBeFocused();
      await expect(input).toHaveValue(field === "邮箱" ? "demo@example.com" : "保留正在编辑的内容");
    }
    await expect(page.getByText("正在确认登录状态…", { exact: true })).toHaveCount(0);
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
        true,
      );
      if (path === "/login") {
        expect(await page.evaluate(() => getComputedStyle(document.body).overscrollBehaviorY)).toBe(
          "none",
        );
      }
    }
    await page.screenshot({
      path: `/tmp/ai-agent-stability-${path.replaceAll("/", "-")}.png`,
      fullPage: true,
    });
  });
}

for (const path of ["/todos/new", `/todos/${item.id}/edit`]) {
  test(`统一时间选择：${path}`, async ({ page }) => {
    await setup(page);
    await page.goto(path);
    const trigger = page.getByLabel("截止时间", { exact: true });
    const input = page.locator("#due-time-native");
    await page.getByRole("button", { name: "今天", exact: true }).click();
    await input.fill("18:22");
    await trigger.click();
    const dialog = page.getByRole("dialog", { name: "选择时间", exact: true });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('input[type="time"]')).toHaveCount(0);
    await expect(dialog.getByRole("button", { name: "18时", exact: true })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    await dialog.getByRole("button", { name: "23时", exact: true }).click();

    await dialog.getByLabel("精确分钟（00–59）").fill("59");
    await expect(input).toHaveValue("18:22");
    for (const width of [320, 390, 900]) {
      await page.setViewportSize({ width, height: 844 });
      const box = await dialog.boundingBox();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(width);
      await page.screenshot({ path: `/tmp/time-picker-${width}.png` });
    }
    await page.setViewportSize({ width: 320, height: 568 });
    await expect(dialog.getByRole("button", { name: "确认时间" })).toBeInViewport();
    await page.screenshot({ path: "/tmp/time-picker-short-320.png" });
    await dialog.getByRole("button", { name: "确认时间" }).click();
    await expect(input).toHaveValue("23:59");
    await expect(input).not.toBeFocused();
    await trigger.click();
    await dialog.getByRole("button", { name: "00时", exact: true }).click();
    await page.keyboard.press("Escape");
    await expect(input).toHaveValue("23:59");
    await expect(input).not.toBeFocused();
    await page.getByRole("button", { name: "清空", exact: true }).click();
    await expect(input).toHaveValue("");
  });
}

test("月历显示农历初一月份与普通日期，保留公历选日", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/calendar?date=2026-02-17");
  const month = page.getByRole("region", { name: "选择日期" });
  await expect(month.getByLabel("农历正月", { exact: true })).toBeVisible();
  await expect(month.getByLabel("农历初二", { exact: true })).toBeVisible();
  await month
    .locator("button")
    .filter({ has: page.getByLabel("农历初二", { exact: true }) })
    .click();
  await expect(page.getByRole("heading", { name: "2026-02-18 的日程" })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/calendar-lunar-320.png" });
});

test("新建日程不再提供重复设置", async ({ page }) => {
  await setup(page);
  await page.goto("/calendar/new?date=2026-09-29");
  await expect(page.getByRole("heading", { name: "新建日程" })).toBeVisible();
  await expect(page.getByText("重复", { exact: true })).toHaveCount(0);
  await expect(page.getByText("重复至", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: "/tmp/calendar-new-no-recurrence.png", fullPage: true });
});

test("日程按时长自动计算结束，跨月与自定义校验正确", async ({ page }) => {
  const state = await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/calendar/new?date=2026-09-30");
  await page.getByLabel("标题（可选）", { exact: true }).fill("夜间安排");
  await expect(page.locator(".event-duration button")).toHaveText([
    "30 分钟",
    "1 小时",
    "2 小时",
    "4 小时",
    "8 小时",
    "12 小时",
  ]);
  await expect(page.getByRole("button", { name: "1 小时", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText("结束于 10:00", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "结束日期", exact: true })).toHaveCount(0);
  await selectEventTime(page, "开始时间", "23:45");
  await expect(page.getByText("结束于 2026-10-01 00:45", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "30 分钟", exact: true }).click();
  await expect(page.getByText("结束于 2026-10-01 00:15", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "自定义结束时间" }).click();
  await expect(page.getByRole("button", { name: "结束日期", exact: true })).toBeVisible();
  await selectEventTime(page, "结束时间", "02:00");
  await selectEventTime(page, "开始时间", "23:30");
  await expect(page.getByText("结束于 2026-10-01 02:00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "按时长设置" }).click();
  await expect(page.getByText("结束于 2026-10-01 00:00", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.getByRole("button", { name: "开始时间", exact: true }).click();
  await page.screenshot({ path: "/tmp/calendar-shared-time-320.png" });
  await page.getByRole("button", { name: "确认时间", exact: true }).click();
  await page.screenshot({ path: "/tmp/calendar-simple-time-320.png", fullPage: true });
  await page.getByRole("button", { name: "保存日程", exact: true }).click();
  await expect(page).toHaveURL(/\/calendar\?date=2026-09-30$/);
  expect(state.events[0]).toMatchObject({
    start_date: "2026-09-30",
    start_time: "23:30",
    end_date: "2026-10-01",
    end_time: "00:00",
    recurrence: "none",
  });
});

test("编辑非预设时长保留结束时间，自定义非法时间阻止保存", async ({ page }) => {
  await setup(page);
  let writes = 0;
  await page.route("**/api/calendar/events/custom", (route) => {
    if (route.request().method() !== "GET") writes++;
    return route.fulfill({
      json: {
        id: "custom",
        title: "原安排",
        start_date: "2026-09-29",
        start_time: "09:00",
        end_date: "2026-09-29",
        end_time: "10:35",
        status: "scheduled",
      },
    });
  });
  await page.goto("/calendar/custom/edit");
  await expect(page.getByRole("button", { name: "结束时间", exact: true })).toContainText("10:35");
  await selectEventTime(page, "开始时间", "10:00");
  await expect(page.getByRole("button", { name: "结束时间", exact: true })).toContainText("10:35");
  await selectEventTime(page, "结束时间", "09:00");
  await page.getByRole("button", { name: "保存日程", exact: true }).click();
  await expect(page.locator(".toast.error")).toContainText("结束时间必须晚于开始时间");
  expect(writes).toBe(0);
});

test("日期选择弹窗统一显示农历与闰月，公历回填正常", async ({ page }) => {
  await setup(page);
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/calendar/new?date=2025-07-25");
  await page.getByRole("button", { name: "日期", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择日期", exact: true });
  await expect(dialog.getByLabel("农历闰六月", { exact: true })).toBeVisible();
  await dialog
    .getByRole("button")
    .filter({ has: page.getByLabel("农历初二", { exact: true }) })
    .click();
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("button", { name: "日期", exact: true })).toContainText("2025/07/26");
  await page.goto("/todos/new");
  await page.locator("#due-date").click();
  await expect(dialog.locator(".calendar-lunar").first()).toBeVisible();
  expect(await dialog.locator(".calendar-lunar").count()).toBeGreaterThanOrEqual(28);
  await expect(page.locator("#due-date-native")).toHaveAttribute("min", "0002-01-01");
  await expect(page.locator("#due-date-native")).toHaveAttribute("max", "9999-12-30");
  await page.screenshot({ path: "/tmp/date-picker-lunar-320.png" });
});

async function selectEventTime(page: Page, label: string, value: string) {
  await page.getByRole("button", { name: label, exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择时间", exact: true });
  const [hour, minute] = value.split(":");
  await dialog.getByRole("button", { name: `${hour}时`, exact: true }).click();
  if (["00", "15", "30", "45"].includes(minute)) {
    await dialog.getByRole("button", { name: `${minute}分`, exact: true }).click();
  } else {
    await dialog.getByLabel("精确分钟（00–59）").fill(minute);
  }
  await dialog.getByRole("button", { name: "确认时间", exact: true }).click();
}

test("时间网格支持直接输入与精确分钟，非法时间不可确认", async ({ page }) => {
  await setup(page);
  await page.goto("/calendar/new?date=2026-09-29");
  await page.getByRole("button", { name: "开始时间", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "选择时间", exact: true });
  await expect(dialog.getByLabel("精确分钟（00–59）")).toBeVisible();
  await expect(dialog.getByRole("group", { name: "小时" }).getByRole("button")).toHaveCount(24);
  await dialog.getByLabel("直接输入时间").fill("2560");
  await expect(dialog.getByRole("button", { name: "确认时间" })).toBeDisabled();
  await dialog.getByLabel("直接输入时间").fill("1845");
  await expect(dialog.getByLabel("直接输入时间")).toHaveValue("18:45");
  await dialog.getByLabel("精确分钟（00–59）").fill("60");
  await expect(dialog.getByRole("button", { name: "确认时间" })).toBeDisabled();
  await dialog.getByLabel("精确分钟（00–59）").fill("7");
  await dialog.getByRole("button", { name: "确认时间" }).click();
  await expect(page.getByRole("button", { name: "开始时间", exact: true })).toContainText("18:07");
});

test("日程空白标题保存时生成默认标题", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/calendar/new?date=2026-09-29");
  await page.getByLabel("标题（可选）", { exact: true }).fill("   ");
  await page.getByRole("button", { name: "保存日程", exact: true }).click();
  await expect(page).toHaveURL(/\/calendar\?date=2026-09-29$/);
  expect(state.events[0]).toMatchObject({ title: "未命名日程", start_date: "2026-09-29" });
  await expect(page.getByText("未命名日程", { exact: true })).toBeVisible();
  await page.screenshot({ path: "/tmp/calendar-default-title.png", fullPage: true });
});

test("日程说明框随内容增高并在清空后缩回", async ({ page }) => {
  await setup(page);
  await page.goto("/calendar/new?date=2026-09-29");
  const description = page.getByRole("textbox", { name: "说明（可选）", exact: true });
  const initial = (await description.boundingBox())!.height;
  expect(initial).toBe(44);
  expect(
    (await page.getByRole("textbox", { name: "地点（可选）", exact: true }).boundingBox())!.height,
  ).toBe(44);
  await page.screenshot({ path: "/tmp/calendar-compact-fields.png", fullPage: true });
  await description.fill(
    Array.from({ length: 8 }, (_, index) => `第${index + 1}行说明`).join("\n"),
  );
  await expect.poll(async () => (await description.boundingBox())!.height).toBeGreaterThan(initial);
  await page.screenshot({ path: "/tmp/calendar-growing-description.png", fullPage: true });
  await description.fill("");
  await expect.poll(async () => (await description.boundingBox())!.height).toBe(initial);
});

test("各页面单行字段与选择器统一高度", async ({ page }) => {
  await setup(page);
  for (const path of ["/calendar/new", "/todos/new"]) {
    await page.goto(path);
    const fields = page.locator(
      'input:not([type="checkbox"]):not([type="radio"]):not([type="hidden"]):not(.picker-native):visible, select:not(.picker-native):visible, .picker-trigger:visible, .event-status-trigger:visible',
    );
    await expect(fields.first()).toBeVisible();
    expect(await fields.count(), path).toBeGreaterThan(0);
    for (const field of await fields.all())
      expect((await field.boundingBox())!.height, path).toBe(44);
  }
});

test("日程卡片删除可取消、失败保留、成功移除", async ({ page }) => {
  const state = await setup(page);
  state.events = [
    {
      id: "delete-card",
      title: "待删除日程",
      start_date: "2026-09-18",
      end_date: "2026-09-18",
      start_time: "18:00",
      end_time: "19:00",
      status: "scheduled",
    },
  ];
  let attempts = 0;
  await page.route("**/api/calendar/events/delete-card", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    attempts++;
    if (attempts === 1)
      return route.fulfill({
        status: 500,
        json: { error: { code: "FAILED", message: "删除失败，请重试" } },
      });
    state.events = [];
    return route.fulfill({ status: 204 });
  });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/calendar?date=2026-09-18");
  const remove = page.getByRole("button", { name: "删除日程：待删除日程", exact: true });
  await expect(remove).toBeVisible();
  await page.screenshot({ path: "/tmp/calendar-card-delete-320.png", fullPage: true });
  await remove.click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(attempts).toBe(0);
  await remove.click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("删除失败，请重试");
  await expect(page.locator(".event-list strong")).toHaveText("待删除日程");
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.locator(".event-list strong")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "当前范围还没有日程" })).toBeVisible();
  expect(attempts).toBe(2);
  await expect(page).toHaveURL(/calendar\?date=2026-09-18/);
});

test("设置退出登录需要确认，取消保持会话", async ({ page }) => {
  const state = await setup(page);
  await page.goto("/settings");
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "退出登录", exact: true });
  await expect(dialog).toBeVisible();
  expect(state.authenticated).toBe(true);
  await page.screenshot({ path: "/tmp/logout-confirmation.png", fullPage: true });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  expect(state.authenticated).toBe(true);
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await dialog.getByRole("button", { name: "确认退出", exact: true }).click();
  await expect(page).toHaveURL(/\/login(?:\?|$)/);
  expect(state.authenticated).toBe(false);
});

test("注销账号说明数据保留，取消与失败不退出，成功退出", async ({ page }) => {
  const state = await setup(page);
  let attempts = 0;
  await page.route("**/api/auth/account", async (route) => {
    expect(route.request().method()).toBe("DELETE");
    attempts++;
    if (attempts === 1)
      return route.fulfill({
        status: 503,
        json: { error: { code: "SERVICE_UNAVAILABLE", message: "注销失败，请重试" } },
      });
    state.authenticated = false;
    return route.fulfill({ status: 204 });
  });
  await page.goto("/settings");
  await page.getByRole("button", { name: "注销账号", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "注销账号", exact: true });
  await expect(dialog).toContainText("业务数据保留");
  await expect(dialog).toContainText("同一邮箱重新注册");
  await page.screenshot({ path: "/tmp/account-deactivation-confirm.png", fullPage: true });
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  expect(attempts).toBe(0);
  await page.getByRole("button", { name: "注销账号", exact: true }).click();
  await dialog.getByRole("button", { name: "确认注销", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("注销失败，请重试");
  expect(state.authenticated).toBe(true);
  await dialog.getByRole("button", { name: "确认注销", exact: true }).click();
  await expect(page).toHaveURL(/\/login(?:\?|$)/);
  expect(state.authenticated).toBe(false);
});

test("待办接近底部自动分页，失败停止自动请求且可重试", async ({ page }) => {
  await setup(page);
  let nextCalls = 0;
  await page.route("**/api/todos?*", (route) => {
    const cursor = new URL(route.request().url()).searchParams.get("cursor");
    if (cursor) {
      nextCalls++;
      if (nextCalls === 1)
        return route.fulfill({ status: 503, json: { error: { message: "暂不可用" } } });
      return route.fulfill({
        json: {
          items: [{ ...item, id: "next-todo", title: "第二页待办" }],
          next_cursor: null,
          server_time: "2026-09-18T00:00:00Z",
        },
      });
    }
    return route.fulfill({
      json: {
        items: Array.from({ length: 20 }, (_, i) => ({ ...item, id: `first-${i}` })),
        next_cursor: "next",
        server_time: "2026-09-18T00:00:00Z",
      },
    });
  });
  await page.goto("/todos");
  await expect(page.locator(".todo-row")).toHaveCount(20);
  expect(nextCalls).toBe(0);
  await page.locator(".load-more").scrollIntoViewIfNeeded();
  const retry = page.getByRole("button", { name: "重试加载更多" });
  await expect(retry).toBeVisible();
  await page.screenshot({ path: "/tmp/todo-auto-load-retry.png", fullPage: true });
  expect(nextCalls).toBe(1);
  await retry.click();
  await expect(page.locator(".todo-row")).toHaveCount(21);
  await expect(page.getByText("第二页待办", { exact: true })).toBeVisible();
  await expect(page.locator(".load-more")).toHaveCount(0);
  expect(nextCalls).toBe(2);
});

test("清单列表确认删除，失败保留记录，成功移除", async ({ page }) => {
  const state = await setup(page);
  state.checklists = [
    { id: "delete-list", title: "旅行准备清单", pinned: true, completed_count: 1, total_count: 10 },
  ];
  let attempts = 0;
  await page.route("**/api/planning/checklists/delete-list", (route) => {
    expect(route.request().method()).toBe("DELETE");
    attempts++;
    if (attempts === 1)
      return route.fulfill({ status: 503, json: { error: { message: "删除失败" } } });
    return route.fulfill({ status: 204 });
  });
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/checklists");
  const remove = page.getByRole("button", { name: "删除清单：旅行准备清单" });
  await expect(remove).toBeVisible();
  await page.screenshot({ path: "/tmp/checklist-delete-320.png", fullPage: true });
  await remove.click();
  await page.getByRole("button", { name: "取消", exact: true }).click();
  expect(attempts).toBe(0);
  await remove.click();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("删除失败");
  await expect(remove).toBeVisible();
  await page.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("heading", { name: "还没有清单" })).toBeVisible();
  expect(attempts).toBe(2);
  await expect(page).toHaveURL(/\/checklists$/);
});
