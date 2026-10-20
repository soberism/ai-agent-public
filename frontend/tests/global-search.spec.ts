import { expect, test } from "@playwright/test";

test("全局搜索展示开放功能并查看记录全文和餐食详情入口", async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/auth/me")
      return route.fulfill({
        json: { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" },
      });
    if (url.pathname === "/api/hub/search/assistant_message/chat")
      return route.fulfill({
        json: {
          subject: "AI 对话记录",
          body: "周末晚餐的完整对话内容",
          created_at: "2026-09-18T04:00:00Z",
          sender: null,
        },
      });
    if (url.pathname === "/api/hub/search")
      return route.fulfill({
        json: {
          items: [
            {
              id: "meal",
              kind: "meal",
              title: "周末晚餐",
              detail: "炖牛肉 · 2026-09-20 · 花生过敏",
              url: "/meals/meal",
            },
            {
              id: "chat",
              kind: "assistant_message",
              title: "周末晚餐怎么安排",
              detail: "",
              url: "",
            },
          ],
        },
      });
    return route.fulfill({ json: { items: [] } });
  });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/search");
    await expect(page.getByText("餐食标题、菜品、日期、备注、本餐偏好与食材库存")).toBeVisible();
    const input = page.getByRole("searchbox", { name: "搜索内容" });
    await input.fill("周末晚餐");
    await expect(page.getByRole("link", { name: "周末晚餐", exact: true })).toHaveAttribute(
      "href",
      "/meals/meal",
    );
    await expect(page.getByText("AI 对话记录", { exact: false })).toHaveCount(0);
    await expect(page.getByText("周末晚餐怎么安排", { exact: true })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `/tmp/global-search-${width}.png`, fullPage: true });
    await input.fill("");
    await expect(page.getByRole("link", { name: "周末晚餐", exact: true })).toHaveCount(0);
  }
});

test("搜索未转写录音并定位备忘", async ({ page }, testInfo) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      return route.fulfill({
        json: { id: "voice-search", email: "test@example.com", timezone: "Asia/Shanghai" },
      });
    if (path === "/api/hub/search")
      return route.fulfill({
        json: {
          items: [
            {
              id: "recording",
              kind: "voice_memo",
              title: "录音 · 2026-09-18 15:00",
              detail: "未转文字，可播放录音",
              url: "/voice-memos#voice-memo-recording",
            },
          ],
        },
      });
    if (path === "/api/assistant/voice-memos")
      return route.fulfill({
        json: [
          {
            id: "recording",
            transcript: "",
            status: "draft",
            created_at: "2026-09-18T07:00:00Z",
            target_id: null,
            target_type: null,
          },
        ],
      });
    return route.fulfill({ json: {} });
  });
  await page.goto("/search");
  await page.getByRole("searchbox", { name: "搜索内容" }).fill("录音");
  await expect(page.getByText("未转文字，可播放录音")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("search-recording.png") });
  await page.getByRole("link", { name: "录音 · 2026-09-18 15:00" }).click();
  await expect(page).toHaveURL(/voice-memos#voice-memo-recording$/);
  await expect(page.locator("#voice-memo-recording")).toBeVisible();
});

test("全局搜索材料和目录，点击定位", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { id: "demo", email: "demo@example.com", timezone: "Asia/Shanghai" };
    if (path === "/api/hub/search")
      json = {
        items: [
          {
            id: "file",
            kind: "document",
            title: "学校通知.pdf",
            detail: "目录：学校资料",
            url: "/documents?folder=school#material-file",
          },
          {
            id: "school",
            kind: "folder",
            title: "学校资料",
            detail: "材料目录",
            url: "/documents?folder=school#directory-school",
          },
        ],
      };
    if (path === "/api/documents/materials")
      json = {
        items: [
          {
            id: "file",
            name: "学校通知.pdf",
            kind: "file",
            status: "uploaded",
            created_at: "2026-09-18T07:00:00Z",
            folder_id: "school",
            error_message: null,
            review_count: 0,
          },
        ],
        folders: [{ id: "school", name: "学校资料", count: 1 }],
      };
    await route.fulfill({ json });
  });
  await page.goto("/search");
  await expect(page.getByText("文件名称、后缀、目录名称", { exact: true })).toBeVisible();
  await page.getByRole("searchbox", { name: "搜索内容" }).fill("学校");
  await expect(page.getByRole("heading", { name: "材料（1）", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("material-search.png"), fullPage: true });
  await page.getByRole("link", { name: "学校通知.pdf", exact: true }).click();
  await expect(page.locator("#material-file")).toBeInViewport();
  await expect(page.getByRole("button", { name: "所在目录", exact: true })).toContainText(
    "学校资料",
  );
  await page.goto("/search");
  await page.getByRole("searchbox", { name: "搜索内容" }).fill("学校");
  await page.getByRole("link", { name: "学校资料", exact: true }).click();
  await expect(page.locator("#directory-school")).toHaveAttribute("open", "");
  await expect(page.locator("#directory-school .directory-files")).toContainText("学校通知.pdf");
  await expect(page.getByRole("button", { name: "所在目录", exact: true })).toContainText(
    "学校资料",
  );
});
