import { expect, test } from "@playwright/test";

const user = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@example.com",
  timezone: "Asia/Shanghai",
};

test.beforeEach(async ({ page }) => {
  let preferences = { custom_instructions: "", memory_enabled: true, updated_at: null };
  let memories = [
    {
      id: "memory-1",
      content: "我周末习惯晨跑",
      source: "user",
      enabled: true,
      created_at: "2026-09-16T00:00:00Z",
      updated_at: "2026-09-16T00:00:00Z",
    },
  ];
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/auth/me") return route.fulfill({ json: user });
    if (path === "/api/platform/settings") return route.fulfill({ json: { ...user } });
    if (path === "/api/assistant/preferences") {
      if (method === "PATCH") preferences = { ...preferences, ...route.request().postDataJSON() };
      return route.fulfill({ json: preferences });
    }
    if (path === "/api/assistant/memories" && method === "GET")
      return route.fulfill({ json: memories });
    if (path === "/api/assistant/memories" && method === "POST") {
      const content = route.request().postDataJSON().content as string;
      if (content.includes("密码"))
        return route.fulfill({
          status: 422,
          json: {
            error: { code: "SENSITIVE_MEMORY_REJECTED", message: "敏感信息不会保存为长期记忆" },
          },
        });
      const created = { ...memories[0], id: "memory-2", content };
      memories = [created, ...memories];
      return route.fulfill({ status: 201, json: created });
    }
    const memory = memories.find((item) => path.endsWith(item.id));
    if (memory && method === "PATCH") {
      Object.assign(memory, route.request().postDataJSON());
      return route.fulfill({ json: memory });
    }
    if (memory && method === "DELETE") {
      memories = memories.filter((item) => item.id !== memory.id);
      return route.fulfill({ status: 204, body: "" });
    }
    return route.fulfill({ status: 404, json: { error: { message: "接口不存在" } } });
  });
});

test("管理自定义指令、记忆开关与长期记忆", async ({ page }) => {
  await page.goto("/assistant/preferences");
  const instructions = page.getByLabel("称呼、表达偏好和稳定习惯");
  await instructions.fill("请称呼我为小周");
  await page.getByRole("button", { name: "保存指令" }).click();
  await expect(page.getByText("AI 偏好已保存")).toBeVisible();

  const memorySwitch = page.getByLabel("启用", { exact: true }).first();
  await memorySwitch.click();
  await expect(memorySwitch).not.toBeChecked();
  await expect(page.getByText("关闭后保留现有内容，但不提供给 AI。")).toBeVisible();

  await page.getByPlaceholder("例如：我周末习惯早起跑步").fill("我喜欢简短回答");
  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.getByText("我喜欢简短回答")).toBeVisible();

  await page.getByRole("button", { name: "编辑" }).first().click();
  await page.getByLabel("记忆内容").fill("我喜欢一句话回答");
  await page.getByRole("button", { name: "保存", exact: true }).click();
  await expect(page.getByText("我喜欢一句话回答")).toBeVisible();
  await expect(page.getByText("来源：用户添加").first()).toBeVisible();
  await expect(page.getByLabel("启用", { exact: true })).toHaveCount(1);
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    const card = page.locator(".memory-item").first();
    expect((await card.boundingBox())!.height).toBeLessThan(100);
    await page.screenshot({ path: `/tmp/memory-compact-${width}.png`, fullPage: true });
  }
});

test("敏感记忆失败后不追加列表", async ({ page }) => {
  await page.goto("/assistant/preferences");
  await page.getByPlaceholder("例如：我周末习惯早起跑步").fill("我的密码是 123456");
  await page.getByRole("button", { name: "添加" }).click();
  await expect(page.getByText("敏感信息不会保存为长期记忆")).toBeVisible();
  await expect(page.getByText("我的密码是 123456")).toHaveCount(0);
});
