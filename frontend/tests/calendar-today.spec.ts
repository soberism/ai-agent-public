import { expect, test } from "@playwright/test";

test("空日期默认今天，已选日期回填且取消不修改", async ({ page }, testInfo) => {
  await page.clock.install({ time: new Date("2026-09-18T12:00:00") });
  await page.route("**/api/**", (route) =>
    route.fulfill({
      json:
        new URL(route.request().url()).pathname === "/api/auth/me"
          ? { id: "demo", email: "demo@example.test", timezone: "Asia/Shanghai" }
          : { items: [] },
    }),
  );
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    await page.goto("/todos/new");
    const field = page.getByLabel("截止日期", { exact: true });
    await field.click();
    const dialog = page.getByRole("dialog", { name: "选择日期" });
    await expect(dialog.locator(".react-calendar__tile--active abbr")).toHaveAttribute(
      "aria-label",
      "2026年9月18日",
    );
    await expect(dialog.locator(".calendar-today")).toHaveCount(0);
    await dialog.locator("abbr[aria-label='2026年9月21日']").click();
    await expect(field).toHaveText("2026/09/21");
    await field.click();
    await expect(dialog.locator(".react-calendar__tile--active abbr")).toHaveAttribute(
      "aria-label",
      "2026年9月21日",
    );
    await page.screenshot({ path: testInfo.outputPath(`default-today-${width}.png`) });
    await page.getByRole("button", { name: "关闭选择日期" }).click();
    await expect(field).toHaveText("2026/09/21");
  }
});
