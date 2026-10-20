import { test, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const user = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@example.com",
  timezone: "Asia/Shanghai",
};
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        status: 401,
        json: { error: { code: "SESSION_EXPIRED", message: "请登录" } },
      });
    if (path === "/api/auth/register/code")
      return route.fulfill({ json: { expires_in: 600, retry_after: 60 } });
    if (path === "/api/auth/register") return route.fulfill({ status: 201, json: user });
    return route.fulfill({ json: { items: [], next_cursor: null } });
  });
  await page.goto("/register");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
});

test("发送、前导零、注册契约与手机布局", async ({ page }) => {
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByText(/验证码邮件已发送/)).toBeVisible();
  await expect(page.getByRole("button", { name: /秒后重发/ })).toBeDisabled();
  await page.getByLabel("邮箱验证码").fill("012345");
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("确认密码").fill("abcdefghijkl");
  const evidence = "openspec/changes/add-email-verification/evidence";
  await mkdir(evidence, { recursive: true });
  // 截图前清空验证码，避免把认证凭据写入证据。
  await page.getByLabel("邮箱验证码").fill("");
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `${evidence}/register-${width}.png`, fullPage: true });
  }
  await page.getByLabel("邮箱验证码").fill("012345");
  const submitted = page.waitForRequest("**/api/auth/register");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  expect((await submitted).postDataJSON()).toMatchObject({
    email: "demo@example.com",
    verification_code: "012345",
  });
  await expect(page).toHaveURL(/\/$/);
});

test("失败不提示已发送，429按截止时间冷却", async ({ page }) => {
  await page.route("**/api/auth/register/code", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: "UNAVAILABLE", message: "邮件服务暂不可用" } },
    }),
  );
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByText("邮件服务暂不可用")).toBeVisible();
  await expect(page.getByText(/验证码邮件已发送/)).toHaveCount(0);
  await page.route("**/api/auth/register/code", (route) =>
    route.fulfill({
      status: 429,
      headers: { "Retry-After": "60" },
      json: { error: { code: "RATE_LIMITED", message: "请稍后重试" } },
    }),
  );
  await page.clock.install();
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByRole("button", { name: /秒后重发/ })).toBeDisabled();
  await page.clock.fastForward(61000);
  await expect(page.getByRole("button", { name: "发送验证码", exact: true })).toBeEnabled();
});

test("切换邮箱清空验证码且拒绝迟到响应，发送时不可注册", async ({ page }) => {
  let release!: () => void;
  await page.route("**/api/auth/register/code", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({ json: { expires_in: 600, retry_after: 60 } });
  });
  await page.getByLabel("邮箱验证码").fill("012345");
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByRole("button", { name: "创建账号", exact: true })).toBeDisabled();
  await page.getByLabel("邮箱", { exact: true }).fill("new@example.com");
  await expect(page.getByLabel("邮箱验证码")).toHaveValue("");
  const response = page.waitForResponse("**/api/auth/register/code");
  release();
  await response;
  await expect(page.getByText(/验证码邮件已发送/)).toHaveCount(0);
  await expect(page.getByRole("button", { name: "发送验证码", exact: true })).toBeEnabled();
});

test("验证码错误关联字段，注册失败允许重取但不自动重发", async ({ page }) => {
  await page.getByLabel("密码", { exact: true }).fill("abcdefghijkl");
  await page.getByLabel("确认密码").fill("abcdefghijkl");
  await page.getByLabel("邮箱验证码").fill("012345");
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({
      status: 422,
      json: {
        error: {
          code: "INVALID_VERIFICATION_CODE",
          message: "验证码无效，请重新获取",
          fields: { verification_code: "验证码无效，请重新获取" },
        },
      },
    }),
  );
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByLabel("邮箱验证码")).toHaveAttribute("aria-invalid", "true");
  await page.route("**/api/auth/register", (route) =>
    route.fulfill({
      status: 503,
      json: { error: { code: "REGISTRATION_FAILED", message: "注册失败" } },
    }),
  );
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByText(/注册未完成，请重新获取验证码/)).toBeVisible();
  await expect(page.getByLabel("邮箱验证码")).toHaveValue("");
  await expect(page.getByRole("button", { name: "发送验证码", exact: true })).toBeEnabled();
});

test("邮箱往返保留冷却，规范化不变保留输入", async ({ page }) => {
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByText(/验证码邮件已发送/)).toBeVisible();
  await page.getByLabel("邮箱验证码").fill("012345");
  await page.getByLabel("邮箱", { exact: true }).fill("DEMO@example.com");
  await expect(page.getByLabel("邮箱验证码")).toHaveValue("012345");
  await page.getByLabel("邮箱", { exact: true }).fill("other@example.com");
  await expect(page.getByLabel("邮箱验证码")).toHaveValue("");
  await page.getByLabel("邮箱", { exact: true }).fill("demo@example.com");
  await expect(page.getByRole("button", { name: /秒后重发/ })).toBeDisabled();
});

test("离开注册页面后的发送响应不污染新表单", async ({ page }) => {
  let release!: () => void;
  await page.route("**/api/auth/register/code", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({ json: { expires_in: 600, retry_after: 60 } });
  });
  await page.getByRole("button", { name: "发送验证码", exact: true }).click();
  await expect(page.getByRole("button", { name: "发送验证码" })).toBeDisabled();
  await page.getByRole("link", { name: "去登录", exact: true }).click();
  const response = page.waitForResponse("**/api/auth/register/code");
  release();
  await response;
  await page.getByRole("link", { name: "去注册", exact: true }).click();
  await expect(page.getByText(/验证码邮件已发送/)).toHaveCount(0);
  await expect(page.getByLabel("邮箱验证码")).toHaveValue("");
});

test("未登录页面重新获得焦点时保留输入框和焦点", async ({ page }) => {
  const input = page.getByLabel("邮箱验证码");
  await input.fill("012345");
  await input.focus();
  let resume: (() => void) | undefined;
  const response = page.waitForResponse(
    (result) => result.url().endsWith("/api/auth/me") && result.status() === 401,
  );
  await page.route("**/api/auth/me", async (route) => {
    await new Promise<void>((resolve) => {
      resume = resolve;
    });
    await route.fulfill({
      status: 401,
      json: { error: { code: "SESSION_EXPIRED", message: "请登录" } },
    });
  });
  try {
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect.poll(() => !!resume).toBe(true);
    await expect(input).toBeVisible();
    await expect(input).toBeFocused();
    await expect(input).toHaveValue("012345");
  } finally {
    resume?.();
  }
  await response;
  await expect(input).toBeFocused();
  await expect(input).toHaveValue("012345");
});
