import { expect, test } from "@playwright/test";

test("家庭入口开放，联系人和其他暂停入口保持禁用", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let json: unknown = { items: [] };
    if (path === "/api/auth/me" || path === "/api/platform/settings")
      json = {
        id: "entry-user",
        email: "demo@example.com",
        nickname: "测试",
        timezone: "Asia/Shanghai",
      };
    if (path === "/api/documents/materials") json = { items: [], folders: [] };
    if (path === "/api/documents/capabilities")
      json = { local_upload: true, email: false, text_extraction: true };
    if (path === "/api/assistant/voice-memos") json = [];
    if (path === "/api/hub/summary") json = { pending_assignments: 3 };
    if (path === "/api/platform/home")
      json = {
        timezone: "Asia/Shanghai",
        server_time: "2026-09-17T00:00:00Z",
        today: { count: 0, items: [] },
        overdue: { count: 0, items: [] },
        recent: [],
        recent_events: [],
      };
    await route.fulfill({ json });
  });
  await page.goto("/");
  await expect(page.getByRole("link", { name: "家庭 家庭成员管理" })).toHaveAttribute(
    "href",
    "/family",
  );
  await expect(page.getByText("家庭任务", { exact: true })).toHaveCount(0);
  await page.goto("/features");
  await expect(page.getByRole("link", { name: "家庭空间 家庭成员管理" })).toBeVisible();
  await expect(page.getByRole("button", { name: "联系人 暂未开放" })).toBeDisabled();
  for (const title of ["档案检索", "待审核", "医疗安排"])
    await expect(page.getByRole("button", { name: `${title} 暂未开放` })).toBeDisabled();
  await expect(page.locator(".feature-menu > button strong")).toHaveText([
    "联系人",
    "档案检索",
    "待审核",
    "医疗安排",
    "站内通知",
    "实时语音对话",
  ]);
  await expect(page.locator(".feature-menu > a")).toHaveCount(8);
  await expect(page.locator('.feature-menu a[href="/"]')).toHaveCount(0);
  await expect(page.locator('a[href="/family"], a[href="/contacts"]')).toHaveCount(1);
  await page.screenshot({
    path: testInfo.outputPath("disabled-family-features.png"),
    fullPage: true,
  });
  await page.getByRole("link", { name: "家庭空间 家庭成员管理" }).click();
  await expect(page.getByRole("heading", { name: "建立家庭空间" })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("family-open.png"), fullPage: true });
  await page.goto("/features");
  await expect(page.locator('a[href="/contacts"]')).toHaveCount(0);
  for (const path of ["/appointments"]) {
    await page.goto(path);
    await expect(page).toHaveURL(/\/features$/);
  }
  await page.goto("/features");
  await page.getByRole("link", { name: "语音备忘 转写、校对和转换事项" }).click();
  await expect(page.getByRole("heading", { name: "语音备忘", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "开始实时语音对话" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "按住说话" })).toHaveText("按住说话");
  await expect(page.getByRole("heading", { name: "还没有备忘" })).toBeVisible();
  const recorder = page.locator(".memo-recorder");
  await expect(recorder).toHaveCSS("position", "fixed");
  const recorderBox = await recorder.boundingBox();
  const navBox = await page.getByRole("navigation", { name: "全局导航" }).boundingBox();
  expect(recorderBox!.y + recorderBox!.height).toBeLessThan(navBox!.y);
  await page.screenshot({ path: testInfo.outputPath("voice-memos-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.screenshot({ path: testInfo.outputPath("voice-memos-desktop.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/features");
  await expect(page.getByRole("button", { name: "实时语音对话 暂未开放" })).toBeDisabled();
  await page.goto("/voice-live");
  await expect(page).toHaveURL(/\/features$/);
  await page.getByRole("link", { name: "材料管理 上传文件、分目录整理" }).click();
  await expect(page.getByRole("heading", { name: "材料管理", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "上传文件", exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("documents-open.png"), fullPage: true });
  await page.goto("/settings");
  await expect(page.getByRole("button", { name: "查看站内通知" })).toBeDisabled();
  await expect(page.getByRole("link", { name: "管理摘要" })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("disabled-notifications-settings.png"),
    fullPage: true,
  });
});
