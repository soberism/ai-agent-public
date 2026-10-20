import { expect, test } from "@playwright/test";

test("成员列表短时缓存，条目策略实时读取且加载与长表单高度稳定", async ({ page }, testInfo) => {
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  let optionsReads = 0;
  let policyReads = 0;
  await page.clock.install();
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/sharing/states") {
      const keys = new URL(route.request().url()).searchParams.get("resources")!.split(",");
      json = {
        states: Object.fromEntries(keys.map((key) => [key, "private"])),
        editable: keys,
      };
    }
    if (path === "/api/auth/me")
      json = { id: "cache-owner", email: "test@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/hub/search")
      json = { items: [{ id: "todo", kind: "todo", title: "缓存测试", url: "/todos/todo" }] };
    if (path === "/api/sharing/options") {
      optionsReads++;
      json = {
        households: [
          {
            id: "home",
            name: "测试家庭",
            role: "owner",
            members: Array.from({ length: 40 }, (_, i) => ({
              account_id: `member-${i}`,
              display_name: `成员${i}`,
              role: "member",
            })),
          },
        ],
      };
    }
    if (path === "/api/sharing/todo/todo") {
      policyReads++;
      if (policyReads === 1) await waiting;
      json = { scope: "private", household_id: null, member_ids: [] };
    }
    await route.fulfill({ json });
  });
  await page.goto("/search");
  await page.getByRole("searchbox").fill("缓存");
  await page.clock.runFor(350);
  await page.getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "可见范围" });
  await expect(dialog.getByRole("status")).toBeVisible();
  const loadingHeight = (await dialog.boundingBox())!.height;
  expect(loadingHeight).toBe(460);
  await page.screenshot({ path: testInfo.outputPath("sharing-loading-mobile.png") });
  release();
  await expect(dialog.getByRole("button", { name: "谁可以访问", exact: true })).toBeVisible();
  expect((await dialog.boundingBox())!.height).toBe(loadingHeight);
  const saveBox = (await dialog.getByRole("button", { name: "保存可见范围" }).boundingBox())!;
  const dialogBox = (await dialog.boundingBox())!;
  expect(dialogBox.y + dialogBox.height - saveBox.y - saveBox.height).toBeLessThanOrEqual(24);
  await page.screenshot({ path: testInfo.outputPath("sharing-private-mobile.png") });
  await dialog.getByRole("button", { name: "谁可以访问", exact: true }).click();
  await page
    .getByRole("dialog", { name: "选择选项" })
    .getByRole("button", { name: "部分可见", exact: true })
    .click();
  await expect(dialog.getByRole("checkbox")).toHaveCount(40);
  expect(
    await dialog.locator("form").evaluate((node) => node.scrollHeight > node.clientHeight),
  ).toBe(true);
  expect((await dialog.boundingBox())!.height).toBe(loadingHeight);
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("sharing-members-desktop.png") });
  await page.getByRole("button", { name: "关闭可见范围" }).click();
  await page.getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true }).click();
  await expect(dialog.getByRole("button", { name: "谁可以访问", exact: true })).toBeVisible();
  expect(policyReads).toBe(2);
  expect(optionsReads).toBe(1);
  await page.getByRole("button", { name: "关闭可见范围" }).click();
  await page.clock.fastForward(61000);
  await page.getByRole("button", { name: /^(…|自己可见|家庭可见|部分可见)$/, exact: true }).click();
  await expect(dialog.getByRole("button", { name: "谁可以访问", exact: true })).toBeVisible();
  expect(policyReads).toBe(3);
  expect(optionsReads).toBe(2);
  await page.setViewportSize({ width: 320, height: 500 });
  expect((await dialog.boundingBox())!.height).toBe(425);
});

test("按钮显示实际可见范围，列表合并读取，保存后同步文案", async ({ page }) => {
  let batches = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/sharing/states") {
      const keys = new URL(route.request().url()).searchParams.get("resources")!.split(",");
      json = {
        states: Object.fromEntries(keys.map((key) => [key, "private"])),
        editable: keys,
      };
    }
    if (path === "/api/auth/me")
      json = { id: "labels", email: "test@example.test", timezone: "Asia/Shanghai" };
    if (path === "/api/hub/search")
      json = {
        items: ["private", "household", "members"].map((scope) => ({
          id: scope,
          kind: "todo",
          title: scope,
          url: `/todos/${scope}`,
        })),
      };
    if (path === "/api/sharing/states") {
      batches++;
      expect(new URL(route.request().url()).searchParams.get("resources")?.split(",")).toHaveLength(
        3,
      );
      json = {
        editable: ["todo:private", "todo:household", "todo:members"],
        states: {
          "todo:private": "private",
          "todo:household": "household",
          "todo:members": "members",
        },
      };
    }
    if (path === "/api/sharing/options") json = { households: [] };
    if (path === "/api/sharing/todo/members")
      json =
        route.request().method() === "PUT"
          ? { scope: "private", household_id: null, member_ids: [] }
          : { scope: "members", household_id: "home", member_ids: ["member"] };
    await route.fulfill({ json });
  });
  await page.goto("/search");
  await page.getByRole("searchbox").fill("范围");
  await expect(page.getByRole("button", { name: "自己可见", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "家庭可见", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "部分可见", exact: true }).click();
  expect(batches).toBe(1);
  const dialog = page.getByRole("dialog", { name: "可见范围" });
  await dialog.getByRole("button", { name: "谁可以访问", exact: true }).click();
  await page
    .getByRole("dialog", { name: "选择选项" })
    .getByRole("button", { name: "自己可见", exact: true })
    .click();
  await dialog.getByRole("button", { name: "保存可见范围" }).click();
  await expect(page.getByRole("button", { name: "自己可见", exact: true })).toHaveCount(2);
  await expect(page.getByRole("button", { name: "部分可见", exact: true })).toHaveCount(0);
});

test("共享接收者不显示权限入口", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me") json = { id: "member", email: "member@example.test" };
    if (path === "/api/hub/search")
      json = { items: [{ id: "shared", kind: "todo", title: "共享任务", url: "/todos/shared" }] };
    if (path === "/api/sharing/states")
      json = { states: { "todo:shared": "household" }, editable: [] };
    await route.fulfill({ json });
  });
  await page.goto("/search");
  await page.getByRole("searchbox").fill("共享");
  await expect(page.getByText("共享任务", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: /^(自己可见|家庭可见|部分可见)$/ })).toHaveCount(0);
});

test("返回列表时先显示上次确认的权限文案", async ({ page }) => {
  let reads = 0;
  let release!: () => void;
  const waiting = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "return-owner", email: "test@example.test", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/hub/search")
      return route.fulfill({
        json: { items: [{ id: "todo", kind: "todo", title: "车队任务", url: "/todos/todo" }] },
      });
    if (path === "/api/platform/home")
      return route.fulfill({
        json: {
          timezone: "Asia/Shanghai",
          server_time: new Date().toISOString(),
          today: { count: 0, items: [] },
          overdue: { count: 0, items: [] },
          recent: [],
        },
      });
    if (path === "/api/sharing/states") {
      reads++;
      if (reads === 2) await waiting;
      return route.fulfill({
        json: { states: { "todo:todo": "household" }, editable: ["todo:todo"] },
      });
    }
    return route.fulfill({ json: { items: [] } });
  });
  await page.goto("/search");
  await page.getByRole("searchbox").fill("车队");
  await expect(page.getByRole("button", { name: "家庭可见" })).toBeVisible();
  await page.getByRole("link", { name: "首页" }).click();
  await page.getByRole("link", { name: "全局搜索" }).first().click();
  await page.getByRole("searchbox").fill("车队");
  await expect.poll(() => reads).toBe(2);
  await expect(page.getByRole("button", { name: "家庭可见" })).toBeVisible();
  release();
});
