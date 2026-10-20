import { expect, test } from "@playwright/test";
import type { AgentRun, ChatEntry } from "../src/features/assistant/types";

test.use({ reducedMotion: "reduce" });

const threadId = "33333333-3333-3333-3333-333333333333";
const prompt = "创建待办：下周天下午去郊游";
const message = "该请求已有待确认的操作计划，请在上方卡片执行或取消。";
const reply = (text: string) => ({
  kind: "message" as const,
  message: text,
  items: [],
  action_token: null,
  action_label: null,
});
const plan: AgentRun = {
  id: "44444444-4444-4444-4444-444444444444",
  thread_id: threadId,
  prompt,
  status: "waiting",
  progress: null,
  final_answer: null,
  sources: [],
  plan_version: 1,
  error: null,
  actions: [
    {
      id: "55555555-5555-5555-5555-555555555555",
      title: "创建待办",
      description: "内容：标题：去郊游；截止日期：2026-10-25；截止时间：14:00",
      status: "proposed",
      result: null,
      error: null,
    },
  ],
};

for (const [width, extended] of [
  [320, false],
  [390, false],
  [1200, false],
  [320, true],
] as const) {
  test(`确认卡片字段分行，重复请求有回复并保留原计划 ${width}px${extended ? " 长内容与多项" : ""}`, async ({
    page,
  }, testInfo) => {
    await page.setViewportSize({ width, height: 844 });
    const note = "带上野餐垫、饮水、防晒用品和备用衣物，出发前再次确认天气与集合地点。";
    const shownPlan = extended
      ? {
          ...plan,
          actions: [
            { ...plan.actions[0], description: `${plan.actions[0].description}；说明：${note}` },
            {
              ...plan.actions[0],
              id: "second-action",
              title: "添加清单项",
              description: "准备全家人的午餐和饮水，包括孩子的过敏食物注意事项。",
            },
          ],
        }
      : plan;
    const entries: ChatEntry[] = [
      { role: "user", message: prompt },
      { id: plan.id, role: "assistant", reply: reply("请确认要执行的操作") },
      { role: "user", message: "你好" },
      { id: "greeting", role: "assistant", reply: reply("你好！有什么可以帮你的吗？") },
    ];
    let repeats = 0;
    let confirmed = false;
    await page.route("**/api/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/auth/me")
        return route.fulfill({ json: { id: "demo", email: "demo@example.com" } });
      if (path === "/api/assistant/threads")
        return route.fulfill({ json: { thread_id: threadId, entries } });
      if (path === `/api/agent/runs/pending/${threadId}`)
        return route.fulfill({ json: confirmed ? [] : [shownPlan] });
      if (path === `/api/agent/runs/active/${threadId}`) return route.fulfill({ status: 204 });
      if (path === "/api/agent/runs") {
        expect(route.request().postDataJSON().prompt).toBe(prompt);
        const id = `repeat-${++repeats}`;
        entries.push(
          { role: "user", message: prompt },
          { id, role: "assistant", reply: reply(message) },
        );
        return route.fulfill({
          json: {
            ...plan,
            id,
            status: "completed",
            actions: [],
            plan_version: null,
            final_answer: message,
          },
        });
      }
      if (path === `/api/agent/runs/${plan.id}/resume`) {
        expect(route.request().postDataJSON().selected_action_ids).toEqual(
          shownPlan.actions.map((action) => action.id),
        );
        confirmed = true;
        return route.fulfill({
          json: { ...shownPlan, status: "completed", final_answer: "已创建待办「去郊游」。" },
        });
      }
      return route.fulfill({ status: 404, json: { error: { message: "未找到" } } });
    });
    await page.goto("/assistant");
    const card = page.getByRole("region", { name: "待确认操作" });
    await expect(card).toBeVisible();
    const content = card.locator(".agent-action-content").first();
    await expect(content).toHaveCSS("display", "grid");
    await expect(card.getByText("去郊游", { exact: true })).toBeVisible();
    await expect(card.getByText("2026-10-25", { exact: true })).toBeVisible();
    await expect(card.getByText("14:00", { exact: true })).toBeVisible();
    const checkboxes = await card.getByRole("checkbox").all();
    for (const checkbox of checkboxes) await checkbox.uncheck();
    await expect(card.getByRole("button", { name: "执行所选操作" })).toBeDisabled();
    for (const checkbox of checkboxes) await checkbox.check();
    await expect(card.getByRole("button", { name: "执行所选操作" })).toBeEnabled();
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    if (extended) await expect(card).toContainText(note);
    await card.screenshot({ path: testInfo.outputPath(`confirmation-${width}.png`) });
    for (let i = 1; i <= 2; i++) {
      await page.getByLabel("对话内容").fill(prompt);
      await page.getByRole("button", { name: "发送" }).click();
      await expect(page.getByText(message, { exact: true })).toHaveCount(i);
      await expect(card).toHaveCount(1);
      await expect(page.locator(".chat-log > .chat-assistant").last()).toHaveText(message);
    }
    await page.reload();
    await expect(card).toHaveCount(1);
    await expect(page.getByText(message, { exact: true })).toHaveCount(2);
    await expect(page.locator(".chat-user")).toHaveCount(4);
    await card.getByRole("button", { name: "执行所选操作" }).click();
    await expect(page.getByText("已创建待办「去郊游」。", { exact: true })).toBeVisible();
    expect(confirmed).toBe(true);
    await expect(card).toHaveCount(0);
  });
}
