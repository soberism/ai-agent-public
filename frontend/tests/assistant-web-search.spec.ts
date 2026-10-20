import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const id = "22222222-2222-2222-2222-222222222222";
const source = "https://www.gov.uk/foreign-travel-advice?reference=travel-packing-checklist";
const contents = ["护照", "签证", "机票行程单", "信用卡", "转换插头", "常用药品"];
const message = `确认创建清单“出国必备”吗？\n${contents.map((item, index) => `${index + 1}. ${item}`).join("\n")}\n\n参考来源：\n1. 出国旅行建议\n${source}`;
const draft = {
  kind: "confirm",
  message,
  items: [],
  action_token: "travel-token",
  action_label: "确认创建",
};

for (const width of [320, 390]) {
  test(`${width}px 联网草稿完整展示、确认执行及恢复历史来源`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    let confirmed = false;
    let history = false;
    await page.route("**/api/**", (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: { id, email: "demo@example.com", timezone: "Asia/Shanghai" },
        });
      if (path === "/api/assistant/threads")
        return route.fulfill({
          json: { thread_id: id, entries: history ? [{ role: "assistant", reply: draft }] : [] },
        });
      if (path === "/api/assistant/messages") return route.fulfill({ json: draft });
      if (path.endsWith("/travel-token/confirm")) {
        confirmed = true;
        return route.fulfill({
          json: {
            kind: "success",
            message: "清单已创建，共 6 项。",
            items: [{ id, title: "出国必备", kind: "checklist", url: `/checklists/${id}` }],
            action_token: null,
            action_label: null,
          },
        });
      }
      return route.fulfill({ json: {} });
    });
    await page.goto("/assistant");
    await page.getByLabel("对话内容").fill("参考网上别人的出国必备清单，帮我创建一份");
    await page.getByRole("button", { name: "发送", exact: true }).click();
    const text = page.locator(".chat-assistant > p").first();
    for (const item of contents) await expect(text).toContainText(item);
    await expect(text).toContainText("参考来源：");
    const link = page.getByRole("link", { name: source, exact: true });
    await expect(link).toHaveAttribute("href", source);
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "noopener noreferrer");
    expect(confirmed).toBe(false);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    const evidence = "openspec/changes/add-assistant-web-search/evidence";
    await mkdir(evidence, { recursive: true });
    await page.screenshot({ path: `${evidence}/draft-${width}.png`, fullPage: true });
    await page.getByRole("button", { name: "确认创建" }).click();
    await expect(page.getByText("清单已创建，共 6 项。")).toBeVisible();
    expect(confirmed).toBe(true);
    await expect(page.getByRole("link", { name: /出国必备/ })).toHaveAttribute(
      "href",
      `/checklists/${id}`,
    );
    history = true;
    await page.reload();
    await expect(link).toHaveAttribute("href", source);
    await expect(page.getByRole("button", { name: "确认创建" })).toHaveCount(0);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.route(source, (route) =>
      route.fulfill({ contentType: "text/html", body: "来源页面" }),
    );
    const popup = page.waitForEvent("popup");
    await link.click();
    const opened = await popup;
    await expect(opened).toHaveURL(source);
    await opened.close();
  });
}

test("正文网址与非法来源保留原文，普通回复保留换行", async ({ page }) => {
  const bodyUrl = "https://www.example.com/body-only";
  const unsafe = [
    "javascript:alert(1)",
    "http://localhost/admin",
    "http://localhost./admin",
    "http://127.0.0.1/admin",
    "http://2130706433/admin",
    "http://10.0.0.1/admin",
    "http://192.168.1.1/admin",
    "http://[::1]/admin",
    "http://[fc00::1]/admin",
    "https://user:password@example.com/",
    "http://printer.local/",
  ];
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    return route.fulfill({
      json:
        path === "/api/assistant/threads"
          ? {
              thread_id: id,
              entries: [
                {
                  role: "assistant",
                  reply: {
                    ...draft,
                    message: `普通回复\n保留换行\n${bodyUrl}\n\n参考来源：\n${unsafe.join("\n")}`,
                  },
                },
              ],
            }
          : { id, email: "demo@example.com", timezone: "Asia/Shanghai" },
    });
  });
  await page.goto("/assistant");
  const text = page.locator(".chat-assistant > p");
  await expect(text).toHaveCSS("white-space", "pre-wrap");
  await expect(text).toContainText(bodyUrl);
  for (const url of unsafe) await expect(text).toContainText(url);
  await expect(text.locator("a")).toHaveCount(0);
});
