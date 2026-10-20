import { expect, test } from "@playwright/test";

test("聊天内容可滚到导航后方，最后一条仍停在输入栏上方", async ({ page }, testInfo) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({
        json: {
          thread_id: "33333333-3333-3333-3333-333333333333",
          entries: [
            { role: "user", message: "帮我整理清单" },
            {
              role: "assistant",
              reply: {
                kind: "message",
                message: Array.from({ length: 40 }, (_, index) => `第 ${index + 1} 条安排`).join(
                  "\n",
                ),
                items: [],
                action_token: null,
                action_label: null,
              },
            },
          ],
        },
      });
    if (path.startsWith("/api/agent/runs/active/")) return route.fulfill({ status: 404 });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  const content = page.locator(".assistant-content");
  const message = page.locator(".chat-assistant");
  await expect(message).toBeVisible();
  const lastLine = await message.boundingBox();
  const input = await page.locator(".chat-input").boundingBox();
  const navigation = await page.locator(".bottom-nav").boundingBox();
  const scrollArea = await content.boundingBox();
  expect(lastLine && input && lastLine.y + lastLine.height < input.y).toBeTruthy();
  expect(scrollArea && navigation && scrollArea.y + scrollArea.height > navigation.y).toBeTruthy();
  expect(
    await page
      .locator(".chat-input")
      .evaluate((element) => getComputedStyle(element).backgroundColor),
  ).toBe("rgb(243, 240, 235)");
  expect(
    await page.locator(".chat-input").evaluate((element) => getComputedStyle(element).position),
  ).toBe("absolute");
  await content.evaluate((element) => (element.scrollTop = 0));
  await expect(message.locator("p").first()).toBeVisible();
  await content.evaluate((element) => {
    const last = element.querySelector(".chat-assistant")!;
    const nav = document.querySelector(".bottom-nav")!;
    element.scrollTop += last.getBoundingClientRect().bottom - nav.getBoundingClientRect().top - 20;
  });
  const behindNav = await message.boundingBox();
  expect(behindNav && navigation && behindNav.y + behindNav.height > navigation.y).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("assistant-nav-overlay.png") });
  await page.setViewportSize({ width: 320, height: 700 });
  await content.evaluate((element) => (element.scrollTop = element.scrollHeight));
  const smallMessage = await message.boundingBox();
  const smallInput = await page.locator(".chat-input").boundingBox();
  expect(
    smallMessage && smallInput && smallMessage.y + smallMessage.height < smallInput.y,
  ).toBeTruthy();
});
