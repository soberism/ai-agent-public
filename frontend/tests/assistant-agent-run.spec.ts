import { expect, test } from "@playwright/test";

const threadId = "33333333-3333-3333-3333-333333333333";
const runId = "44444444-4444-4444-4444-444444444444";

const run = {
  id: runId,
  thread_id: threadId,
  status: "waiting",
  progress: "已读取待办，正在准备操作",
  final_answer: null,
  sources: [{ title: "家庭待办", excerpt: "买牛奶", url: null }],
  actions: [
    {
      id: "55555555-5555-5555-5555-555555555555",
      title: "完成待办：买牛奶",
      description: "将状态更新为已完成",
      status: "proposed",
      result: null,
      error: null,
    },
  ],
  plan_version: 1,
  error: null,
};

test("展示来源并由用户确认 Agent 操作计划", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === "/api/agent/runs") return route.fulfill({ json: run });
    if (path.endsWith("/resume")) {
      expect(route.request().postDataJSON()).toEqual({
        plan_version: 1,
        selected_action_ids: ["55555555-5555-5555-5555-555555555555"],
      });
      return route.fulfill({
        json: {
          ...run,
          status: "completed",
          final_answer: "已完成待办“买牛奶”。查看 **待办**：/todos",
          actions: [
            {
              ...run.actions[0],
              status: "completed",
              result: {
                kind: "success",
                message: "待办已完成。",
                items: [
                  {
                    id: "66666666-6666-6666-6666-666666666666",
                    title: "买牛奶",
                    due_date: null,
                    due_time: null,
                    status: "completed",
                    kind: "todo",
                    url: "/todos/66666666-6666-6666-6666-666666666666",
                  },
                ],
                action_token: null,
                action_label: null,
              },
            },
          ],
        },
      });
    }
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("完成买牛奶");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByRole("region", { name: "回答来源" })).toContainText("家庭待办");
  await expect(page.getByRole("region", { name: "待确认操作" })).toContainText("完成待办：买牛奶");
  await expect(page.getByRole("region", { name: "待确认操作" }).getByRole("checkbox")).toHaveCount(
    1,
  );
  await page.getByRole("button", { name: "确认", exact: true }).click();
  await expect(page.getByRole("link", { name: "打开待办" })).toHaveAttribute("href", "/todos");
  await expect(page.getByRole("region", { name: "操作结果" })).toHaveCount(0);
  const reply = page.locator(".chat-assistant").last();
  await expect(reply).toContainText("已完成待办");
  await expect(reply.getByRole("link", { name: "买牛奶" })).toHaveAttribute(
    "href",
    "/todos/66666666-6666-6666-6666-666666666666",
  );
  await expect(reply.getByRole("checkbox")).toHaveCount(0);
});

test("刷新页面后恢复等待确认的 Agent Run", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === `/api/agent/runs/active/${threadId}`) return route.fulfill({ json: run });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");

  await expect(page.getByRole("region", { name: "回答来源" })).toContainText("家庭待办");
  await expect(page.getByRole("region", { name: "待确认操作" })).toContainText("完成待办");
});

test("回答后的快捷操作预填输入并绑定原对象", async ({ page }) => {
  const suggestion = {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    source_run_id: runId,
    label: "调整时间",
    type: "follow_up",
    intent: "edit_event",
    target_kind: "event",
    target_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    target_title: "接孩子",
    draft: "把日程「接孩子」改到：",
    url: null,
  };
  const requests: Record<string, unknown>[] = [];
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === "/api/agent/runs") {
      requests.push(route.request().postDataJSON());
      return route.fulfill({
        json: {
          ...run,
          status: "completed",
          final_answer: "已创建日程。",
          suggestions: requests.length === 1 ? [suggestion] : [],
        },
      });
    }
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("创建接孩子日程");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByLabel("对话内容").fill("我原来写的草稿");
  await page.getByRole("button", { name: "调整时间" }).click();
  await expect(page.getByLabel("对话内容")).toHaveValue(suggestion.draft);
  await page.getByRole("button", { name: "取消快捷操作" }).click();
  await expect(page.getByLabel("对话内容")).toHaveValue("我原来写的草稿");
  await page.getByRole("button", { name: "调整时间" }).click();
  await expect(page.getByLabel("对话内容")).toHaveValue(suggestion.draft);
  await page.getByLabel("对话内容").fill(suggestion.draft + "明天 14:00");
  await page.getByRole("button", { name: "发送" }).click();

  await expect.poll(() => requests.length).toBe(2);
  expect(requests[1]).toMatchObject({
    prompt: suggestion.draft + "明天 14:00",
    source_run_id: runId,
    suggestion_id: suggestion.id,
  });
});

test("历史快捷操作失效时不回退到旧助手写入", async ({ page }) => {
  const suggestion = {
    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
    source_run_id: runId,
    label: "添加清单项",
    type: "follow_up",
    intent: "add_checklist_item",
    target_kind: "checklist",
    target_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    target_title: "旅行准备",
    draft: "在清单「旅行准备」添加：",
    url: null,
  };
  let legacyCalls = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({
        json: {
          thread_id: threadId,
          entries: [
            {
              role: "assistant",
              reply: {
                kind: "result",
                message: "已找到清单",
                items: [],
                action_token: null,
                action_label: null,
                suggestions: [suggestion],
              },
            },
          ],
        },
      });
    if (path === "/api/agent/runs")
      return route.fulfill({
        status: 404,
        json: { error: { code: "SUGGESTION_NOT_FOUND", message: "快捷操作已失效" } },
      });
    if (path === "/api/assistant/messages") legacyCalls += 1;
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByRole("button", { name: "添加清单项" }).click();
  await page.getByLabel("对话内容").fill(suggestion.draft + "护照");
  await page.getByRole("button", { name: "发送" }).click();
  await expect(page.getByText("快捷操作已失效")).toBeVisible();
  await expect(page.locator(".chat-user")).toHaveCount(0);
  expect(legacyCalls).toBe(0);
});

test("待确认计划列表失败时仍恢复活跃任务", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === `/api/agent/runs/pending/${threadId}`)
      return route.fulfill({ status: 503, json: { error: { message: "暂时不可用" } } });
    if (path === `/api/agent/runs/active/${threadId}`) return route.fulfill({ json: run });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await expect(page.getByRole("region", { name: "待确认操作" })).toContainText("完成待办");
});

test("聊天里的好的作为新消息发送，不确认历史计划", async ({ page }) => {
  const prompts: string[] = [];
  let confirmations = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === "/api/agent/runs") {
      prompts.push(route.request().postDataJSON().prompt);
      return route.fulfill({ json: run });
    }
    if (path.includes("/confirm") || path.endsWith("/resume")) confirmations += 1;
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("创建待办");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByLabel("对话内容").fill("好的");
  await page.getByRole("button", { name: "发送" }).click();

  await expect.poll(() => prompts).toEqual(["创建待办", "好的"]);
  expect(confirmations).toBe(0);
});

test("刷新后能看到两个独立的待确认计划", async ({ page }) => {
  const older = {
    ...run,
    id: "66666666-6666-6666-6666-666666666666",
    plan_version: 2,
    actions: [{ ...run.actions[0], id: "77777777-7777-7777-7777-777777777777" }],
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === `/api/agent/runs/pending/${threadId}`)
      return route.fulfill({ json: [run, older] });
    if (path === `/api/agent/runs/active/${threadId}`) return route.fulfill({ json: run });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await expect(page.getByRole("region", { name: "待确认操作" })).toHaveCount(2);
});

test("取消 Agent Run 后不显示未执行的操作结果", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === "/api/agent/runs") return route.fulfill({ json: run });
    if (path === `/api/agent/runs/${runId}/cancel`)
      return route.fulfill({
        json: {
          ...run,
          status: "cancelled",
          final_answer: "已取消本次任务。",
        },
      });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("创建待办");
  await page.getByRole("button", { name: "发送" }).click();
  await page.getByRole("button", { name: "取消", exact: true }).click();

  await expect(page.getByText("已取消本次任务。")).toBeVisible();
  await expect(page.getByRole("region", { name: "操作结果" })).toHaveCount(0);
});

test("没有活跃任务时对话页可直接输入", async ({ page }) => {
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === `/api/agent/runs/active/${threadId}`)
      return route.fulfill({ status: 204, body: "" });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");

  await expect(page.getByLabel("对话内容")).toBeEnabled();
  await expect(page.getByText("响应无法确认，请重试核对")).toHaveCount(0);
});

test("轮询短暂断网后保留 Run 并继续完成", async ({ page }) => {
  let polls = 0;
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({ json: { thread_id: threadId, entries: [] } });
    if (path === `/api/agent/runs/active/${threadId}`)
      return route.fulfill({ status: 404, json: { error: { message: "无活跃任务" } } });
    if (path === "/api/agent/runs")
      return route.fulfill({ json: { ...run, status: "queued", actions: [], sources: [] } });
    if (path === `/api/agent/runs/${runId}`) {
      polls += 1;
      if (polls === 1) return route.abort("failed");
      return route.fulfill({
        json: {
          ...run,
          status: "completed",
          progress: null,
          final_answer: "网络恢复后已完成。",
          actions: [],
        },
      });
    }
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });

  await page.goto("/assistant");
  await page.getByLabel("对话内容").fill("检查任务");
  await page.getByRole("button", { name: "发送" }).click();

  await expect(page.getByText("网络恢复后已完成。")).toBeVisible();
  expect(polls).toBe(2);
});

test("历史消息隐藏设应用内提醒并保留标记完成", async ({ page }) => {
  const base = {
    source_run_id: runId,
    type: "follow_up",
    target_kind: "todo",
    target_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
    target_title: "接孩子",
    url: null,
  };
  await page.route("**/api/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/auth/me")
      return route.fulfill({
        json: { id: "11111111-1111-1111-1111-111111111111", email: "demo@example.com" },
      });
    if (path === "/api/assistant/threads")
      return route.fulfill({
        json: {
          thread_id: threadId,
          entries: [
            {
              id: runId,
              role: "assistant",
              reply: {
                kind: "result",
                message:
                  "进行中待办1项。\n「接孩子」：不设截止日期\n日程1项。\n「去乐天玛特」：2026-10-17 16:00—2026-10-17 17:00",
                items: [],
                suggestions: [
                  {
                    ...base,
                    id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
                    label: "设应用内提醒",
                    intent: "create_reminder",
                    draft: "设置提醒：",
                  },
                  {
                    ...base,
                    id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
                    label: "标记完成",
                    intent: "edit_todo",
                    draft: "把待办「接孩子」标记完成",
                  },
                ],
              },
            },
          ],
        },
      });
    return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
  });
  await page.goto("/assistant");
  await expect(page.getByRole("button", { name: "标记完成" })).toBeVisible();
  await expect(page.getByRole("button", { name: "设应用内提醒" })).toHaveCount(0);
  await expect(page.locator(".chat-assistant")).toContainText("去乐天玛特");
  await page.reload();
  await expect(page.getByRole("button", { name: "标记完成" })).toBeVisible();
  await expect(page.getByRole("button", { name: "设应用内提醒" })).toHaveCount(0);
  await page.screenshot({ path: "/tmp/ai-agent-query-reply.png", fullPage: true });
});
