import { expect, test } from "@playwright/test";

const id = "22222222-2222-2222-2222-222222222222";
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({ json: { id, email: "demo@example.com", timezone: "Asia/Shanghai" } });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: id, entries: [] } });
    if (path === "/api/assistant/messages") {
      const message = route.request().postDataJSON().message as string;
      if (message.includes("餐食"))
        return route.fulfill({
          json: {
            kind: "confirm",
            message:
              "确认创建餐食计划吗？菜品：番茄炒蛋；日期：2026-09-19；餐次：晚餐；用餐人数：2",
            items: [],
            action_token: "meal-token",
            action_label: "确认执行",
          },
        });
      return route.fulfill({
        json: {
          kind: "result",
          message: "查询材料与目录结果。名称：示例.txt；状态：已上传",
          items: [
            { id, title: "示例.txt", kind: "document", status: "uploaded", url: "/documents" },
          ],
          action_token: null,
          action_label: null,
        },
      });
    }
    if (path.endsWith("/meal-token/confirm"))
      return route.fulfill({
        json: {
          kind: "success",
          message: "创建餐食计划已执行。菜品：番茄炒蛋",
          items: [{ id, title: "明日晚餐", kind: "meal", status: "draft", url: `/meals/${id}` }],
          action_token: null,
          action_label: null,
        },
      });
    return route.fulfill({ json: {} });
  });
});

test("开放能力提示、材料入口和手机布局", async ({ page }) => {
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/assistant");
    await expect(page.getByText(/整理随手记、回顾计划/)).toBeVisible();
    await expect(page.locator(".assistant-empty > span")).toBeInViewport();
    for (const label of [
      "查看餐食计划",
      "回顾本周的计划",
      "查看我的材料",
      "查看语音备忘",
      "查看家庭成员",
    ])
      await expect(page.getByRole("button", { name: label })).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/assistant-capabilities-${width}.png`, fullPage: true });
  }
  await page.getByRole("button", { name: "查看我的材料" }).click();
  const material = page.getByRole("link", { name: /示例.txt/ });
  await expect(material).toHaveAttribute("href", "/documents");
  await expect(material).toContainText("打开查看");
});

test("餐食草稿展示关键参数，点击确认后才显示执行结果", async ({ page }) => {
  const actions: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/actions/")) actions.push(request.url());
  });
  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("创建明晚两人的番茄炒蛋餐食计划");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText(/餐次：晚餐；用餐人数：2/)).toBeVisible();
  expect(actions).toHaveLength(0);
  await page.getByRole("button", { name: "确认执行" }).click();
  expect(actions).toHaveLength(1);
  await expect(page.getByText("创建餐食计划已执行。菜品：番茄炒蛋")).toBeVisible();
  await expect(page.getByRole("link", { name: /明日晚餐/ })).toHaveAttribute(
    "href",
    `/meals/${id}`,
  );
  await expect(page.getByRole("button", { name: "确认执行" })).toHaveCount(0);
});

test("隐藏库存页不会从 AI 历史消息产生入口", async ({ page }) => {
  await page.route("**/api/assistant/threads", (route) =>
    route.fulfill({
      json: {
        thread_id: id,
        entries: [
          {
            role: "assistant",
            reply: {
              kind: "result",
              message: "在 /meals/settings 查看",
              items: [{ id, title: "胡萝卜", kind: "pantry", status: "available", url: null }],
            },
          },
        ],
      },
    }),
  );
  await page.goto("/assistant");
  await expect(page.locator(".assistant-item")).toContainText("胡萝卜");
  await expect(page.locator(".chat-assistant a[href='/meals/settings']")).toHaveCount(0);
});
