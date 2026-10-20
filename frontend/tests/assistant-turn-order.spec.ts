import { expect, test } from "@playwright/test";
import { upsertRunEntry } from "../src/features/assistant/agentRunEntries";
import type { ChatEntry } from "../src/features/assistant/types";

test.use({ reducedMotion: "reduce" });

const threadId = "33333333-3333-3333-3333-333333333333";
const runId = "44444444-4444-4444-4444-444444444444";
const greetingId = "66666666-6666-6666-6666-666666666666";
const prompt = "明天上午去接孩子";
const reply = (message: string, kind = "message") => ({
  kind,
  message,
  items: [],
  action_token: null,
  action_label: null,
});
const plan = {
  id: runId,
  thread_id: threadId,
  prompt,
  status: "waiting" as const,
  progress: null,
  final_answer: "我已整理好操作计划，请确认要执行的项目。",
  sources: [],
  plan_version: 1,
  error: null,
  actions: [
    {
      id: "55555555-5555-5555-5555-555555555555",
      title: "创建日程",
      description: "标题：接孩子；开始时间：09:00；结束时间：10:00",
      status: "proposed" as const,
      result: null,
      error: null,
    },
  ],
};

for (const [width, legacy] of [
  [320, false],
  [390, false],
  [390, true],
] as const) {
  test(`确认卡片留在原轮次，问候、刷新和执行不重复 ${width}px ${legacy ? "旧历史" : "新历史"}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const prompts: string[] = [];
    let greetingComplete = false;
    let confirmed = false;
    const greeting = () => ({
      ...plan,
      id: greetingId,
      prompt: "你好",
      actions: [],
      plan_version: null,
      status: greetingComplete ? "completed" : "running",
      progress: "正在分析问题",
      final_answer: greetingComplete ? "你好！有什么可以帮你的吗？" : null,
    });
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({
          json: {
            id: "11111111-1111-1111-1111-111111111111",
            email: "demo@example.com",
          },
        });
      if (path === "/api/assistant/threads")
        return route.fulfill({
          json: {
            thread_id: threadId,
            entries: greetingComplete
              ? [
                  { role: "user", message: prompt },
                  ...(!legacy
                    ? [{ id: runId, role: "assistant", reply: reply(plan.final_answer, "confirm") }]
                    : []),
                  { role: "user", message: "你好" },
                  { id: greetingId, role: "assistant", reply: reply("你好！有什么可以帮你的吗？") },
                ]
              : [],
          },
        });
      if (path === `/api/agent/runs/pending/${threadId}`)
        return route.fulfill({ json: prompts.length && !confirmed ? [plan] : [] });
      if (path === `/api/agent/runs/active/${threadId}`)
        return greetingComplete ? route.fulfill({ json: plan }) : route.fulfill({ status: 204 });
      if (path === "/api/agent/runs") {
        prompts.push(route.request().postDataJSON().prompt);
        return route.fulfill({ json: prompts.length === 1 ? plan : greeting() });
      }
      if (path === `/api/agent/runs/${greetingId}`) return route.fulfill({ json: greeting() });
      if (path === `/api/agent/runs/${runId}/resume`) {
        expect(route.request().postDataJSON()).toEqual({
          plan_version: 1,
          selected_action_ids: [plan.actions[0].id],
        });
        confirmed = true;
        return route.fulfill({
          json: {
            ...plan,
            status: "completed",
            final_answer: "已创建日程「接孩子」。",
            actions: [{ ...plan.actions[0], status: "completed" }],
          },
        });
      }
      return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
    });
    await page.goto("/assistant");
    await page.getByLabel("对话内容").fill(prompt);
    await page.getByRole("button", { name: "发送" }).click();
    const card = page.getByRole("region", { name: "待确认操作" });
    await expect(card).toHaveCount(1);
    await page.getByLabel("对话内容").fill("你好");
    await page.getByRole("button", { name: "发送" }).click();
    await expect(page.getByText("正在分析问题", { exact: true })).toBeVisible();
    const ordered = () =>
      page.locator(".chat-log").evaluate((log) => {
        const card = log.querySelector('[aria-label="待确认操作"]');
        const users = log.querySelectorAll(".chat-user");
        return (
          !!card && !!(card.compareDocumentPosition(users[1]) & Node.DOCUMENT_POSITION_FOLLOWING)
        );
      });
    expect(await ordered()).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`pending-${width}.png`) });
    greetingComplete = true;
    await expect(page.getByText("你好！有什么可以帮你的吗？", { exact: true })).toBeVisible();
    await expect(card).toHaveCount(1);
    expect(prompts).toEqual([prompt, "你好"]);
    await page.reload();
    await expect(card).toHaveCount(1);
    expect(await ordered()).toBe(true);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await expect(page.getByRole("button", { name: "执行所选操作" })).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath(`restored-${width}.png`) });
    await page.getByRole("button", { name: "执行所选操作" }).click();
    await expect(page.getByText("已创建日程「接孩子」。", { exact: true })).toHaveCount(1);
    await expect(card).toHaveCount(0);
    expect(confirmed).toBe(true);
  });
}

test("修订计划只替换父计划，其他计划保持原位", () => {
  let entries: ChatEntry[] = [{ role: "user", message: prompt }];
  entries = upsertRunEntry(entries, plan);
  const other = { ...plan, id: "other", prompt: "另一件事" };
  entries = upsertRunEntry([...entries, { role: "user", message: other.prompt }], other);
  const revised = { ...plan, id: "revised", prompt: "改成后天", parent_plan_id: runId };
  entries = upsertRunEntry([...entries, { role: "user", message: revised.prompt }], revised);
  expect(entries[1]).toMatchObject({
    id: runId,
    reply: { kind: "message", message: "已根据你的补充重新整理操作计划。" },
  });
  expect(entries[3]).toMatchObject({ id: other.id, reply: { kind: "confirm" } });
  expect(entries[5]).toMatchObject({ id: revised.id, reply: { kind: "confirm" } });
});
