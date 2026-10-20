import { expect, test } from "@playwright/test";

const user = { id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" };

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: user });
    if (path === "/api/hub/search")
      return route.fulfill({
        json: {
          items: [
            { id: "todo-1", kind: "todo", title: "家庭缴费", detail: "本周", url: "/todos/todo-1" },
            { id: "meal-1", kind: "meal", title: "家庭晚餐", detail: "晚餐", url: "/meals" },
          ],
        },
      });
    if (path === "/api/mail/capabilities")
      return route.fulfill({
        json: {
          imap: true,
          smtp: true,
          third_party_calendar: false,
          notification_channels: ["email"],
        },
      });
    if (path === "/api/mail/notifications" && route.request().method() === "GET")
      return route.fulfill({ json: [] });
    if (path === "/api/assistant/voice-memos")
      return route.fulfill({
        json: [
          {
            id: "memo-1",
            transcript: "明天整理行李",
            status: "draft",
            target_type: null,
            target_id: null,
            created_at: "2026-09-16T00:00:00Z",
          },
        ],
      });
    return route.fulfill({ status: 404, json: { error: { message: "接口不存在" } } });
  });
});

test("全局搜索按分类展示且移除快捷创建", async ({ page }) => {
  await page.goto("/search");
  await page.getByPlaceholder("搜索你添加的各类事项").fill("家庭");
  await expect(page.getByText("家庭缴费")).toBeVisible();
  await expect(page.getByRole("region", { name: "待办", exact: true })).toContainText("家庭缴费");
  await expect(page.getByRole("region", { name: "餐食计划" })).toContainText("家庭晚餐");
  await expect(page.getByRole("button", { name: "立即创建" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "搜索", exact: true })).toHaveCount(0);
  await page.screenshot({ path: "/tmp/search-categories.png" });
  await page.getByPlaceholder("搜索你添加的各类事项").fill("");
  await expect(page.getByRole("region", { name: "待办", exact: true })).toHaveCount(0);
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("连接页明确只用邮件且不接第三方日历", async ({ page }) => {
  await page.goto("/connections");
  await expect(page.getByText(/不会连接第三方日历/)).toBeVisible();
  await expect(page.getByText(/邮件通知/)).toBeVisible();
});

test("必填校验使用Toast，阻止发送并支持再次提示", async ({ page }) => {
  let sends = 0;
  await page.route("**/api/workflows/email-settings", (route) =>
    route.fulfill({
      json: {
        notifications_enabled: true,
        recipient_emails: ["demo@example.com"],
        daily_enabled: false,
        daily_time: "09:00",
        reminder_enabled: false,
        reminder_minutes: 30,
        weekly_enabled: false,
        weekly_day: 0,
        weekly_time: "09:00",
        quiet_start: "22:00",
        quiet_end: "07:00",
      },
    }),
  );
  await page.route("**/api/mail/notifications", (route) => {
    if (route.request().method() === "POST") sends++;
    return route.fulfill({ json: [] });
  });
  await page.goto("/connections");
  await page.evaluate(() => {
    document.addEventListener(
      "invalid",
      (event) => {
        setTimeout(() => {
          document.body.dataset.nativeValidationSuppressed = String(event.defaultPrevented);
        });
      },
      true,
    );
  });
  const submit = page.getByRole("button", { name: "发送测试通知" });
  await submit.click();
  const toast = page.locator(".toast.error");
  await expect(toast).toHaveText(/请填写主题/);
  await expect(page.locator("body")).toHaveAttribute("data-native-validation-suppressed", "true");
  await expect(page.getByRole("textbox", { name: "主题", exact: true })).toBeFocused();
  expect(sends).toBe(0);
  await page.screenshot({ path: "/tmp/form-validation-toast.png" });
  await expect(toast).toBeHidden({ timeout: 4000 });
  await submit.click();
  await expect(toast).toHaveText(/请填写主题/);
  expect(sends).toBe(0);
});

test("语音备忘可进入确认转换", async ({ page }) => {
  await page.goto("/voice-memos");
  await expect(page.getByText("明天整理行李")).toBeVisible();
  await expect(page.getByRole("button", { name: "转为待办" })).toBeVisible();
});

test("搜索无结果时展示明确空状态", async ({ page }) => {
  await page.route("**/api/hub/search?*", (route) => route.fulfill({ json: { items: [] } }));
  await page.goto("/search");
  await page.getByPlaceholder("搜索你添加的各类事项").fill("不存在");
  await expect(page.getByRole("status")).toHaveText("没有找到匹配的事项");
});

test("快速修改输入不会显示迟到的旧结果", async ({ page }) => {
  await page.route("**/api/hub/search?*", async (route) => {
    const q = new URL(route.request().url()).searchParams.get("q");
    if (q === "旧") await new Promise((resolve) => setTimeout(resolve, 700));
    await route
      .fulfill({
        json: {
          items: [{ id: q, kind: "todo", title: `${q}结果`, detail: "", url: "/todos/test" }],
        },
      })
      .catch(() => {});
  });
  await page.goto("/search");
  const input = page.getByPlaceholder("搜索你添加的各类事项");
  const oldRequest = page.waitForRequest("**/api/hub/search?q=*");
  await input.fill("旧");
  await oldRequest;
  await input.fill("新");
  await expect(page.getByText("新结果", { exact: true })).toBeVisible();
  await page.waitForTimeout(800);
  await expect(page.getByText("旧结果", { exact: true })).toHaveCount(0);
});

test("邮件结果在当前页弹窗查看并可关闭", async ({ page }) => {
  await page.route("**/api/hub/search?*", (route) =>
    route.fulfill({
      json: {
        items: [
          { id: "in-1", kind: "mail", title: "测试来信", detail: "摘要", url: "/connections" },
          { id: "out-1", kind: "email", title: "测试通知", detail: "摘要", url: "/connections" },
        ],
      },
    }),
  );
  await page.route("**/api/hub/search/*/*", (route) =>
    route.fulfill({
      json: {
        subject: "邮件主题",
        body: "完整正文\n<script>测试内容</script>",
        sender: "demo@example.com",
        created_at: "2026-09-17T00:00:00Z",
      },
    }),
  );
  await page.goto("/search");
  await page.getByPlaceholder("搜索你添加的各类事项").fill("测试");
  for (const title of ["测试来信", "测试通知"]) {
    await page.getByRole("button", { name: title, exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "邮件详情" });
    await expect(dialog).toContainText("完整正文");
    await expect(dialog).toContainText("<script>测试内容</script>");
    await expect(page).toHaveURL(/\/search$/);
    await page.screenshot({ path: "/tmp/search-mail-dialog.png" });
    await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
  }
  await expect(page.getByPlaceholder("搜索你添加的各类事项")).toHaveValue("测试");
});

test("搜索初始布局在手机宽度下清晰且无横向溢出", async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/search");
    await expect(page.getByRole("heading", { name: "找到生活里的每一件事" })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/search-initial-${width}.png` });
    await page.getByPlaceholder("搜索你添加的各类事项").fill("家庭安排");
    await page.screenshot({ path: `/tmp/search-typed-${width}.png` });
  }
});

test("邮件设置标签与控件保留间距且免打扰列等宽", async ({ page }) => {
  let savedReminderMinutes: number | null = null;
  await page.route("**/api/workflows/email-settings", (route) => {
    if (route.request().method() === "PUT") {
      const body = route.request().postDataJSON();
      savedReminderMinutes = body.reminder_minutes;
      return route.fulfill({ json: body });
    }
    return route.fulfill({
      json: {
        notifications_enabled: true,
        recipient_emails: ["demo@example.com", "other@example.com"],
        daily_enabled: true,
        daily_time: "08:00",
        reminder_enabled: true,
        reminder_minutes: 30,
        weekly_enabled: true,
        weekly_day: 0,
        weekly_time: "20:00",
        quiet_start: "22:00",
        quiet_end: "07:00",
      },
    });
  });
  await page.goto("/connections");
  const form = page.locator(".email-schedule-form");
  await expect(form).toBeVisible();
  await form.getByLabel("提前多少分钟提醒").fill("45");
  await form.getByRole("button", { name: "保存设置" }).click();
  expect(savedReminderMinutes).toBe(45);
  for (const field of await form.locator("label > .picker-field").all()) {
    await expect(field).toHaveCSS("margin-top", "8px");
    expect(
      await field.evaluate((el) =>
        Math.abs(el.getBoundingClientRect().x - el.parentElement!.getBoundingClientRect().x),
      ),
    ).toBeLessThan(1);
  }
  const fields = await form.locator(".event-time-grid label").all();
  const boxes = await Promise.all(fields.map((field) => field.boundingBox()));
  expect(Math.abs(boxes[0]!.width - boxes[1]!.width)).toBeLessThan(1);
  await form.scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/email-settings-spacing.png" });
  await expect(form.locator(".email-setting-section")).toHaveCount(4);
  for (const width of [320, 960]) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto("/connections");
    await expect(form).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
    await page.screenshot({ path: `/tmp/email-sections-${width}.png`, fullPage: true });
  }
});
