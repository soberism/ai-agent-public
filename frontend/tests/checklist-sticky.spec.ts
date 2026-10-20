import { expect, test } from "@playwright/test";

test("清单新建栏滚动时吸顶", async ({ page }, testInfo) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    const user = { id: "user-1", email: "demo@example.com", timezone: "Asia/Shanghai" };
    const json =
      path === "/api/auth/me" || path === "/api/platform/settings"
        ? user
        : {
            items: Array.from({ length: 30 }, (_, i) => ({
              id: `list-${i}`,
              title: `准备清单 ${i}`,
              completed_count: 0,
              total_count: 10,
              pinned: false,
            })),
          };
    return route.fulfill({ json });
  });
  await page.goto("/checklists");
  await expect(page.getByText("准备清单 29", { exact: true })).toBeAttached();
  const input = page.getByRole("textbox", { name: "清单名称" });
  const before = await input.boundingBox();
  await page.evaluate(() => window.scrollTo(0, 600));
  await expect
    .poll(async () => (await page.locator(".checklist-sticky-header").boundingBox())?.y)
    .toBe(0);
  const after = await input.boundingBox();
  expect(after?.y).toBe(before?.y);
  await input.fill("新清单");
  await expect(page.getByRole("button", { name: "新建", exact: true })).toBeEnabled();
  await page.screenshot({ path: testInfo.outputPath("sticky.png"), fullPage: false });
});
