import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const user = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "demo@example.com",
  timezone: "Asia/Shanghai",
};
const item = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "买牛奶",
  due_date: "2026-09-15",
  due_time: "18:00",
  status: "ongoing",
};

test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me") return route.fulfill({ json: user });
    if (path === "/api/assistant/threads")
      return route.fulfill({
        json: { thread_id: "33333333-3333-3333-3333-333333333333", entries: [] },
      });
    if (path === "/api/assistant/messages") {
      const body = route.request().postDataJSON();
      expect(body.thread_id).toBe("33333333-3333-3333-3333-333333333333");
      const message = body.message;
      if (message.includes("查看"))
        return route.fulfill({
          json: {
            kind: "result",
            message: "找到 1 条待办。",
            items: [item],
            action_token: null,
            action_label: null,
          },
        });
      return route.fulfill({
        json: {
          kind: "confirm",
          message: "确认创建待办“买牛奶”吗？",
          items: [],
          action_token: "test-action",
          action_label: "确认创建",
        },
      });
    }
    return route.fulfill({
      json: {
        kind: "success",
        message: "待办已创建。",
        items: [item],
        action_token: null,
        action_label: null,
      },
    });
  });
});

test("初始化线程期间不显示加载文案", async ({ page }) => {
  let release!: () => void;
  await page.route("**/api/assistant/threads", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({
      json: { thread_id: "33333333-3333-3333-3333-333333333333", entries: [] },
    });
  });
  await page.goto("/assistant");
  await expect(page.getByRole("heading", { name: "AI 对话" })).toBeVisible();
  const todosLink = page.getByRole("link", { name: "待办", exact: true });
  await expect(todosLink).toHaveCSS("text-decoration-line", "none");
  await expect(todosLink).toHaveCSS("min-height", "44px");
  await expect(page.getByText("加载中", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: "/tmp/assistant-without-loading.png" });
  release();
  await expect(page.getByLabel("对话内容")).toBeEnabled();
});

test("聚焦后的对话输入框保持可见", async ({ page }) => {
  await page.goto("/assistant");
  const input = page.getByLabel("对话内容");
  await expect(input).toBeEnabled();
  await input.focus();
  await expect(page.getByRole("navigation", { name: "全局导航" })).toBeHidden();
  const box = await input.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await input.evaluate((element: HTMLInputElement) => element.blur());
  await expect(page.getByRole("navigation", { name: "全局导航" })).toBeVisible();
});

test("聚焦时不因可见视口事件二次移动页面", async ({ page }) => {
  await page.goto("/assistant");
  const input = page.getByLabel("对话内容");
  await expect(input).toBeEnabled();
  await input.focus();
  const initial = await page.locator(".chat-input").boundingBox();
  await page.evaluate(() => {
    const viewport = window.visualViewport!;
    Object.defineProperty(viewport, "height", { configurable: true, value: 500 });
    viewport.dispatchEvent(new Event("resize"));
  });
  const composer = await page.locator(".chat-input").boundingBox();
  expect(composer!.y).toBe(initial!.y);
  await expect(page.getByRole("heading", { name: "AI 对话" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "全局导航" })).toBeHidden();
});

test("初始化恢复历史并滚动到最新消息", async ({ page }) => {
  const entries = Array.from({ length: 12 }, (_, index) => ({
    role: "user" as const,
    message: `历史消息${index}`,
  }));
  await page.route("**/api/assistant/threads", (route) =>
    route.fulfill({
      json: { thread_id: "33333333-3333-3333-3333-333333333333", entries },
    }),
  );
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/assistant");

  await expect(page.getByText("历史消息11", { exact: true })).toBeVisible();
  await expect
    .poll(() => page.locator(".assistant-content").evaluate((node) => node.scrollTop))
    .toBeGreaterThan(0);
});

test("历史确认消息不可再次操作", async ({ page }) => {
  await page.route("**/api/assistant/threads", (route) =>
    route.fulfill({
      json: {
        thread_id: "33333333-3333-3333-3333-333333333333",
        entries: [
          {
            role: "assistant",
            reply: {
              kind: "confirm",
              message: "确认创建待办“旧任务”吗？",
              items: [],
              action_token: "expired-action",
              action_label: "确认创建",
            },
          },
        ],
      },
    }),
  );
  await page.goto("/assistant");

  await expect(page.getByText("确认创建待办“旧任务”吗？")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认创建" })).toHaveCount(0);
});

test("开始新对话清空已恢复历史", async ({ page }) => {
  let releaseFresh!: () => void;
  await page.route("**/api/assistant/threads", async (route) => {
    const body = route.request().postDataJSON();
    if (body.fresh)
      await new Promise<void>((resolve) => {
        releaseFresh = resolve;
      });
    return route.fulfill({
      json: {
        thread_id: body.fresh ? "44444444-4444-4444-4444-444444444444" : "history-thread",
        entries: body.fresh ? [] : [{ role: "user", message: "上一段对话" }],
      },
    });
  });
  await page.goto("/assistant");
  await expect(page.getByText("上一段对话", { exact: true })).toBeVisible();

  const startFresh = page.getByRole("button", { name: "开始新对话" });
  await startFresh.click();
  await expect(startFresh).toBeDisabled();
  await expect(startFresh).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  releaseFresh();
  await expect(page.getByText("上一段对话", { exact: true })).toHaveCount(0);
  await expect(page.getByText("今天，有什么想交给我？")).toBeVisible();
});

test("等待模型回复时显示思考中", async ({ page }) => {
  let release!: () => void;
  await page.route("**/api/assistant/messages", async (route) => {
    await new Promise<void>((resolve) => {
      release = resolve;
    });
    await route.fulfill({
      json: {
        kind: "clarify",
        message: "请告诉我更具体的操作。",
        items: [],
        action_token: null,
        action_label: null,
      },
    });
  });
  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("1");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByRole("status").filter({ hasText: "思考中…" })).toBeVisible();
  await expect(page.getByLabel("对话内容")).toBeFocused();
  await expect(page.getByLabel("对话内容")).toBeEnabled();
  await page.screenshot({ path: "/tmp/assistant-thinking.png" });
  release();
  await expect(page.getByText("请告诉我更具体的操作。")).toBeVisible();
  await expect(page.getByLabel("对话内容")).toBeFocused();
  await expect(page.getByText("思考中…", { exact: true })).toHaveCount(0);
});

test("查询、确认创建与手机布局", async ({ page }) => {
  await page.goto("/assistant");
  await page.getByRole("button", { name: "查看我今天的待办" }).click();
  await expect(page.getByText("找到 1 条待办。")).toBeVisible();
  await expect(page.getByRole("link", { name: /买牛奶/ })).toBeVisible();

  await page.getByLabel("对话内容").fill("提醒我明天18:00买牛奶");
  await expect(page.getByRole("button", { name: "发送" })).toHaveCSS(
    "background-color",
    "rgb(40, 40, 50)",
  );
  await expect(page.getByRole("button", { name: "发送" })).toHaveCSS("height", "44px");
  const [inputBox, sendBox] = await Promise.all([
    page.getByLabel("对话内容").boundingBox(),
    page.getByRole("button", { name: "发送" }).boundingBox(),
  ]);
  expect(
    Math.abs(inputBox!.y + inputBox!.height / 2 - sendBox!.y - sendBox!.height / 2),
  ).toBeLessThan(1);
  await page.screenshot({ path: "/tmp/assistant-primary-send.png" });
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("确认创建待办“买牛奶”吗？")).toBeVisible();
  const confirmButton = page.getByRole("button", { name: "确认创建" });
  await expect(confirmButton).toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  await expect(confirmButton).toHaveCSS("border-top-width", "0px");
  await expect(confirmButton).toHaveCSS("color", "rgb(101, 83, 166)");
  await expect(confirmButton).toHaveCSS("min-height", "38px");
  await page.screenshot({ path: "/tmp/assistant-confirm-button.png" });
  await page.getByLabel("对话内容").fill("是的");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("待办已创建。")).toBeVisible();
  await expect(page.getByRole("link", { name: /买牛奶/ })).toHaveCount(2);

  const evidence = "openspec/changes/add-ai-todo-chat/evidence";
  await mkdir(evidence, { recursive: true });
  for (const width of [320, 390]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: `${evidence}/assistant-${width}.png`, fullPage: true });
  }
});

test("确认令牌失效后撤下旧按钮", async ({ page }) => {
  await page.route("**/api/assistant/actions/*/confirm", (route) =>
    route.fulfill({
      status: 404,
      json: { error: { code: "ACTION_NOT_FOUND", message: "确认操作已失效，请重新发起" } },
    }),
  );
  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("提醒我明天18:00买牛奶");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByRole("button", { name: "确认创建" }).click();
  await expect(page.getByText("确认操作已失效，请重新发起")).toBeVisible();
  await expect(page.getByRole("button", { name: "确认创建" })).toHaveCount(0);
  await page.setViewportSize({ width: 320, height: 568 });
  await page.screenshot({
    path: "openspec/changes/add-ai-todo-chat/evidence/assistant-expired-320.png",
    fullPage: true,
  });
});

test("长对话保留顶部导航并展示最新消息", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 568 });
  await page.goto("/assistant");

  for (let index = 0; index < 8; index += 1) {
    await page.getByLabel("对话内容").fill(`任务${index}`);
    await page.getByRole("button", { name: "发送" }).click();
  }

  await expect(page.getByRole("heading", { name: "AI 对话" })).toBeVisible();
  const latestMessage = page.getByText("任务7", { exact: true });
  const composer = page.locator(".chat-input");
  await expect(composer).toHaveCSS("position", "static");
  await expect(latestMessage).toBeVisible();
  await expect
    .poll(() => page.locator(".assistant-content").evaluate((node) => node.scrollTop))
    .toBeGreaterThan(0);
  const [latestMessageBox, composerBox] = await Promise.all([
    latestMessage.boundingBox(),
    composer.boundingBox(),
  ]);
  expect(latestMessageBox!.y + latestMessageBox!.height).toBeLessThanOrEqual(composerBox!.y);
  const headerBox = await page.locator(".assistant-header").boundingBox();
  const navBox = await page.getByRole("navigation", { name: "全局导航" }).boundingBox();
  expect(headerBox!.y).toBe(0);
  expect(navBox!.y - composerBox!.y - composerBox!.height).toBeLessThanOrEqual(16);
  await expect(page.locator(".assistant-content")).toHaveCSS("scrollbar-width", "none");
  await page.screenshot({
    path: "openspec/changes/add-ai-todo-chat/evidence/assistant-latest-320.png",
  });
  await page.locator(".assistant-content").evaluate((node) => (node.scrollTop = 0));
  const scrolledComposer = await composer.boundingBox();
  const pageBox = await page.locator(".assistant-page").boundingBox();
  expect(scrolledComposer!.y + scrolledComposer!.height).toBeLessThanOrEqual(
    pageBox!.y + pageBox!.height,
  );
  expect(scrolledComposer!.y + scrolledComposer!.height).toBeGreaterThan(
    pageBox!.y + pageBox!.height - 100,
  );
});

test("后端线程过期后清空消息并创建新线程", async ({ page }) => {
  let threadCount = 0;
  await page.route("**/api/assistant/threads", (route) => {
    threadCount += 1;
    return route.fulfill({
      json: { thread_id: `${threadCount}3333333-3333-3333-3333-333333333333`, entries: [] },
    });
  });
  await page.route("**/api/assistant/messages", (route) =>
    route.fulfill({
      status: 410,
      json: { error: { code: "THREAD_EXPIRED", message: "对话已过期，请重新开始" } },
    }),
  );
  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("是的");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("今天，有什么想交给我？")).toBeVisible();
  await expect(page.getByText("是的", { exact: true })).toHaveCount(0);
  await expect.poll(() => threadCount).toBe(2);
});

async function mockRecorder(page: import("@playwright/test").Page) {
  await page.addInitScript(() => {
    const track = { stop() {} };
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: async () => ({ getTracks: () => [track] }) },
    });
    class FakeMediaRecorder {
      static isTypeSupported(type: string) {
        return type === "audio/webm";
      }
      mimeType = "audio/webm";
      state = "inactive";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["voice"], { type: this.mimeType }) });
        this.onstop?.();
      }
    }
    Object.defineProperty(window, "MediaRecorder", { value: FakeMediaRecorder });
  });
}

test("录音格式在开始前为空时仍上传完整音频和明确格式", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "vibrate", {
      value: (duration: number) => {
        document.documentElement.dataset.vibration = String(duration);
        return true;
      },
    });
  });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "mediaDevices", {
      value: { getUserMedia: async () => ({ getTracks: () => [{ stop() {} }] }) },
    });
    class Recorder {
      static isTypeSupported(type: string) {
        return type === "audio/webm";
      }
      mimeType = "";
      state = "inactive";
      ondataavailable: ((event: { data: Blob }) => void) | null = null;
      onstop: (() => void) | null = null;
      start() {
        this.state = "recording";
      }
      stop() {
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["header"]) });
        this.ondataavailable?.({ data: new Blob(["audio"]) });
        this.onstop?.();
      }
    }
    Object.defineProperty(window, "MediaRecorder", { value: Recorder });
  });
  const uploads: Record<string, string>[] = [];
  await page.route("**/api/assistant/transcriptions", (route) => {
    uploads.push(route.request().postDataJSON());
    return route.fulfill({ json: { transcript: "测试录音" } });
  });
  await page.goto("/assistant");
  const button = page.getByRole("button", { name: "按住说话" });
  const input = page.getByLabel("对话内容");
  await input.focus();
  await button.hover();
  await page.mouse.down();
  await expect(page.getByRole("button", { name: "松开结束录音" })).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-vibration", "300");
  await page.mouse.up();
  await expect.poll(() => uploads.length).toBe(1);
  await expect(input).not.toBeFocused();
  await expect(input).toHaveValue("测试录音");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(input).not.toBeFocused();
  expect(uploads[0].mime_type).toBe("audio/webm");
  expect(Buffer.from(uploads[0].audio_base64, "base64").toString()).toBe("headeraudio");
});

test("iPhone Safari 按住可见按钮录音", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "userAgent", {
      value:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    });
  });
  await mockRecorder(page);
  await page.goto("/assistant");
  const button = page.getByRole("button", { name: "按住说话" });
  await expect(page.locator(".voice-haptic-switch")).toHaveCount(0);
  const box = await button.boundingBox();
  if (!box) throw new Error("语音按钮未渲染");
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(page.getByRole("button", { name: "松开结束录音" })).toBeVisible();
  await page.mouse.up();
  await expect(page.getByRole("button", { name: "按住说话" })).toBeVisible();
});

test("iPhone Safari 语音备忘直接按住可见录音按钮", async ({ page }, testInfo) => {
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "userAgent", {
      value:
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    });
  });
  await mockRecorder(page);
  await page.route("**/api/assistant/voice-memos", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/assistant/voice-memos/audio", (route) =>
    route.fulfill({
      status: 201,
      json: {
        id: "memo-test",
        transcript: "",
        status: "draft",
        target_type: null,
        target_id: null,
        created_at: "2026-09-21T00:00:00Z",
      },
    }),
  );
  await page.goto("/voice-memos");
  const button = page.getByRole("button", { name: "按住说话" });
  await expect(button).toBeVisible();
  await expect(page.locator(".voice-haptic-switch")).toHaveCount(0);
  const buttonBox = await button.boundingBox();
  expect(buttonBox).toBeTruthy();
  await page.screenshot({ path: testInfo.outputPath("voice-memo-button-idle.png") });
  await page.mouse.move(buttonBox!.x + buttonBox!.width / 2, buttonBox!.y + buttonBox!.height / 2);
  await page.mouse.down();
  await expect(page.getByRole("button", { name: "松开结束录音" })).toBeVisible();
  await page.mouse.up();
});

test("语音转写校对后才发送", async ({ page }) => {
  await mockRecorder(page);
  let sent = "";
  await page.route("**/api/assistant/transcriptions", (route) =>
    route.fulfill({ json: { transcript: "明天买牛奶" } }),
  );
  await page.route("**/api/assistant/messages", (route) => {
    sent = route.request().postDataJSON().message;
    return route.fulfill({
      json: { kind: "message", message: "收到", items: [], action_token: null, action_label: null },
    });
  });
  await page.goto("/assistant");
  await page.getByRole("button", { name: "语音输入" }).click();
  await page.getByRole("button", { name: "停止录音" }).click();
  const draft = page.getByLabel("请检查转写内容");
  await expect(draft).toHaveValue("明天买牛奶");
  await draft.fill("明晚买牛奶");
  await page.getByRole("button", { name: "发送校对内容" }).click();
  await expect.poll(() => sent).toBe("明晚买牛奶");
});

test("转写服务不可用时不生成草稿", async ({ page }) => {
  await mockRecorder(page);
  await page.route("**/api/assistant/transcriptions", (route) =>
    route.fulfill({
      status: 503,
      json: {
        error: {
          code: "VOICE_TRANSCRIPTION_UNAVAILABLE",
          message: "语音转写服务尚未配置，请改用文字输入",
        },
      },
    }),
  );
  await page.goto("/assistant");
  await page.getByRole("button", { name: "语音输入" }).click();
  await page.getByRole("button", { name: "停止录音" }).click();
  await expect(page.getByRole("alert")).toContainText("语音转写服务尚未配置");
  await expect(page.getByLabel("请检查转写内容")).toHaveCount(0);
});

test("输入框右侧发送与语音切换", async ({ page }) => {
  await page.goto("/assistant");
  const input = page.getByLabel("对话内容");
  await expect(page.getByRole("button", { name: "按住说话" })).toBeVisible();
  await expect(page.getByRole("button", { name: "发送", exact: true })).toHaveCount(0);
  await input.fill("测试消息");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "按住说话" })).toHaveCount(0);
  await page.screenshot({ path: "/tmp/assistant-composer-send.png" });
  await input.fill("  ");
  await expect(page.getByRole("button", { name: "按住说话" })).toBeVisible();
  const inputBox = await input.boundingBox();
  const voiceBox = await page.getByRole("button", { name: "按住说话" }).boundingBox();
  expect(voiceBox!.x).toBeGreaterThan(inputBox!.x + inputBox!.width);
  await page.screenshot({ path: "/tmp/assistant-composer-voice.png" });
});
