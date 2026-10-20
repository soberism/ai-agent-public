import { expect, test } from "@playwright/test";

test.use({
  userAgent:
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1",
});

test("iPhone 对话输入栏保持单行且录音按钮居中", async ({ page }, testInfo) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({
        json: { thread_id: "33333333-3333-3333-3333-333333333333", entries: [] },
      });
    if (path.startsWith("/api/agent/runs/active/")) return route.fulfill({ status: 204, body: "" });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");

  const form = await page.locator(".chat-input").boundingBox();
  const input = await page.getByLabel("对话内容").boundingBox();
  const microphone = await page.getByRole("button", { name: "按住说话" }).boundingBox();
  const inputBackground = await page
    .getByLabel("对话内容")
    .evaluate((element) => getComputedStyle(element).backgroundColor);
  const formBackground = await page
    .locator(".chat-input")
    .evaluate((element) => getComputedStyle(element).backgroundColor);

  expect(form && input && microphone).toBeTruthy();
  expect(form!.height).toBeLessThan(80);
  expect(
    Math.abs(input!.y + input!.height / 2 - microphone!.y - microphone!.height / 2),
  ).toBeLessThan(2);
  await expect(page.locator(".voice-haptic-switch")).toHaveCount(0);
  expect(inputBackground).toBe("rgba(0, 0, 0, 0)");
  expect(formBackground).not.toBe("rgba(0, 0, 0, 0)");
  await page.screenshot({ path: testInfo.outputPath("assistant-voice-idle.png") });
  await page.getByLabel("对话内容").focus();
  await expect(page.getByLabel("对话内容")).toHaveCSS("box-shadow", "none");
  await page.screenshot({ path: testInfo.outputPath("assistant-voice-focused.png") });
});
