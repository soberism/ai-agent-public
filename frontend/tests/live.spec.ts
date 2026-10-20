import { test, expect } from "@playwright/test";
import { randomUUID } from "node:crypto";

test.use({ trace: "off", screenshot: "off", video: "off" });

// 仅对显式启动、连接隔离测试库的 API 执行，不把测试账号写入日常开发库。
test("真实注册到待办持久化、双账号隔离与手机布局", async ({ page, browser }, testInfo) => {
  test.skip(process.env.LIVE_E2E !== "1", "需显式 LIVE_E2E=1 与隔离测试 API");
  test.skip(
    !process.env.LIVE_EMAIL ||
      !process.env.LIVE_VERIFICATION_CODE ||
      !process.env.LIVE_OTHER_EMAIL ||
      !process.env.LIVE_OTHER_VERIFICATION_CODE,
    "需两个专用邮箱及经真实发送接口获取的未过期验证码；不得用固定码绕过验证",
  );
  test.setTimeout(90000);
  const baseURL = testInfo.project.use.baseURL as string;
  const password = `Test-${randomUUID()}`;
  const email = process.env.LIVE_EMAIL!;
  const title = "买牛奶，准备明天的早餐";
  await page.goto("/login");
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  await page.getByRole("link", { name: "去注册", exact: true }).click();
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByLabel("确认密码", { exact: true }).fill(password);
  await page.getByLabel("邮箱验证码", { exact: true }).fill(process.env.LIVE_VERIFICATION_CODE!);
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByRole("heading", { name: "暂时没有待办" })).toBeVisible();
  await page.getByRole("button", { name: "已完成", exact: true }).click();
  await expect(page.getByRole("heading", { name: "还没有已完成的待办" })).toBeVisible();
  await page.getByRole("button", { name: "进行中", exact: true }).click();
  await page.getByRole("link", { name: "添加第一条待办", exact: true }).click();
  await page.getByLabel("标题", { exact: true }).fill(title);
  await page.getByLabel("描述", { exact: true }).fill("纯文本 <b>不会执行</b>\n带上购物袋。");
  await page.getByRole("button", { name: "明天", exact: true }).click();
  await page.getByLabel("截止时间", { exact: true }).fill("18:00");
  await page.getByLabel("截止时间", { exact: true }).press("Tab");
  await expect(page.getByLabel("截止时间", { exact: true })).toHaveValue("18:00");
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page.getByRole("link", { name: new RegExp(title) })).toContainText("18:00");
  await page.reload();
  await expect(page.getByRole("link", { name: new RegExp(title) })).toBeVisible();
  for (const width of [390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
  }
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "筛选", exact: true }).click();
  await page.getByRole("button", { name: "明天", exact: true }).click();
  await expect(page.getByRole("dialog", { name: "筛选待办" })).toHaveCount(0);
  await page.getByRole("link", { name: new RegExp(title) }).click();
  await expect(page.getByRole("heading", { name: title })).toBeVisible();
  const detailPath = new URL(page.url()).pathname;
  await expect(page.getByText("纯文本 <b>不会执行</b>", { exact: false })).toBeVisible();
  await expect(page.locator("article b")).toHaveCount(0);
  await page.getByRole("link", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "不设截止日期", exact: true }).click();
  await expect(page.getByLabel("截止时间", { exact: true })).toHaveValue("");
  await page.getByRole("button", { name: "保存修改", exact: true }).click();
  await expect(page.getByText("不设截止日期", { exact: true })).toBeVisible();
  await expect(page.getByText("已保存，该待办不符合当前筛选条件", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回" }).click();
  await expect(page.getByRole("heading", { name: "没有符合条件的待办" })).toBeVisible();
  await page.getByRole("link", { name: "新建待办", exact: true }).click();
  const longTitle = "准备早餐".repeat(25);
  await page.getByLabel("标题", { exact: true }).fill(longTitle);
  await page.getByRole("button", { name: "添加待办", exact: true }).click();
  await expect(page.getByRole("link", { name: new RegExp(longTitle) })).toBeVisible();
  await expect(page.locator(".list-toolbar")).toContainText("全部");
  await page.setViewportSize({ width: 320, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("link", { name: new RegExp(title) }).click();
  await page.getByRole("button", { name: "标记完成", exact: true }).click();
  await expect(page.getByRole("button", { name: "标记为未完成", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "标记为未完成", exact: true }).click();
  await expect(page.getByRole("button", { name: "标记完成", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "返回" }).click();
  await page.getByRole("button", { name: "账号菜单", exact: true }).click();
  await page.getByRole("button", { name: "退出登录", exact: true }).click();
  await page.getByRole("button", { name: "确认退出", exact: true }).click();
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  await page.goBack();
  await expect(page.getByRole("heading", { name: "登录安排儿" })).toBeVisible();
  await expect(page.getByText(title, { exact: true })).toHaveCount(0);
  await page.getByLabel("邮箱", { exact: true }).fill(email);
  await page.getByLabel("密码", { exact: true }).fill(password);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  // 后退后的安全 returnTo 可以恢复详情，不能要求一律回列表。
  await expect(
    page
      .getByRole("link", { name: new RegExp(title) })
      .or(page.getByRole("heading", { name: title, exact: true })),
  ).toBeVisible();

  const other = await browser.newContext({ baseURL });
  try {
    const registered = await other.request.post("/api/auth/register", {
      headers: { Origin: new URL(baseURL).origin, "X-App-Request": "1" },
      data: {
        email: process.env.LIVE_OTHER_EMAIL!,
        password,
        confirm_password: password,
        verification_code: process.env.LIVE_OTHER_VERIFICATION_CODE!,
      },
    });
    expect(registered.status()).toBe(201);
    const otherPage = await other.newPage();
    await otherPage.goto(detailPath);
    await expect(otherPage.getByText("该待办不存在或无法访问", { exact: true })).toBeVisible();
    const denied = await other.request.patch(`/api${detailPath}`, {
      headers: { Origin: new URL(baseURL).origin, "X-App-Request": "1" },
      data: { status: "completed" },
    });
    expect(denied.status()).toBe(404);
  } finally {
    await other.close();
  }
});
