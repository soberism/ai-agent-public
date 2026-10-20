import { expect, test } from "@playwright/test";

test("PRD02 真实计划闭环", async ({ page }) => {
  test.skip(process.env.PLANNING_LIVE_E2E !== "1", "仅对隔离测试服务运行");
  const email = process.env.PLANNING_LIVE_EMAIL!;
  const password = process.env.PLANNING_LIVE_PASSWORD!;
  await page.goto("/login");
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page).toHaveURL("/");

  await page.goto("/todos/new");
  await page.getByLabel("标题").fill("真实验收待办");
  await page.getByLabel("截止日期").fill("2026-09-16");
  await page.getByRole("button", { name: "添加待办" }).click();
  await page
    .getByRole("link", { name: /真实验收待办/ })
    .first()
    .click();
  await page.getByLabel("提醒日期").fill("2026-09-16");
  await page.getByLabel("提醒时间").fill("09:00");
  await page.getByRole("button", { name: "保存提醒" }).click();
  await expect(page.getByText("2026/9/16 09:00:00").first()).toBeVisible();
  const reminderToggle = page.getByLabel("开启提醒").first();
  await reminderToggle.click();
  await expect(reminderToggle).not.toBeChecked();
  await page.getByRole("link", { name: "安排到日历" }).click();
  await page.getByLabel("开始时间").fill("08:00");
  await page.getByLabel("结束时间").fill("09:00");
  await page.getByRole("button", { name: "保存日程" }).click();
  await expect(page.getByText("真实验收待办").first()).toBeVisible();

  await page.goto("/checklists");
  await page.getByLabel("清单名称").fill("真实验收清单");
  await page.getByRole("button", { name: "新建" }).click();
  await page.getByLabel("清单项").fill("核对日程");
  await page.getByRole("button", { name: "添加" }).click();
  await page.getByRole("checkbox").click();
  await expect(page.getByText("1/1 已完成")).toBeVisible();
  await page.goto("/checklists");
  await page.getByRole("button", { name: "复用真实验收清单", exact: true }).click();
  await expect(page.getByRole("heading", { name: "真实验收清单（副本）" })).toBeVisible();
  await expect(page.getByRole("checkbox")).not.toBeChecked();

  await page.goto("/calendar/new?date=2026-09-16");
  await page.getByLabel("标题").fill("真实验收日程");
  await page.getByLabel("开始日期").fill("2026-09-16");
  await page.getByLabel("开始时间").fill("10:00");
  await page.getByLabel("结束日期").fill("2026-09-16");
  await page.getByLabel("结束时间").fill("11:00");
  await page.getByLabel("重复").selectOption("daily");
  await page.getByLabel("重复至").fill("2026-09-17");
  await page.getByRole("button", { name: "保存日程" }).click();
  await page.goto("/calendar?date=2026-09-17");
  await expect(page.getByText("真实验收日程").first()).toBeVisible();

  await page.goto("/review");
  await page.getByLabel("起始日期").fill("2026-09-16");
  await expect(page.getByRole("heading", { name: "计划回顾" })).toBeVisible();
  await expect(page.getByText("日程", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
