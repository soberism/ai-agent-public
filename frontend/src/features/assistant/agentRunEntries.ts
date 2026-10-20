import type { AgentRun, AssistantReply, ChatEntry } from "./types";

function asReply(run: AgentRun): AssistantReply {
  const pending = ["waiting", "queued", "running"].includes(run.status);
  return {
    kind: pending ? "confirm" : run.status === "completed" ? "result" : "message",
    message: pending
      ? "我已整理好操作计划，请确认要执行的项目。"
      : run.final_answer || run.error || "本次任务已取消。",
    items: Array.from(
      new Map(
        run.actions
          .filter((action) => action.status === "completed")
          .flatMap((action) => action.result?.items || [])
          .map((item) => [`${item.kind}-${item.id}`, item]),
      ).values(),
    ),
    action_token: null,
    action_label: null,
    suggestions: run.suggestions || [],
  };
}

export function upsertRunEntry(entries: ChatEntry[], run: AgentRun): ChatEntry[] {
  if (["queued", "running"].includes(run.status) && !run.actions.length) return entries;
  if (run.status === "waiting" && run.parent_plan_id) {
    entries = entries.map((entry) =>
      entry.role === "assistant" && entry.id === run.parent_plan_id
        ? {
            ...entry,
            reply: { ...entry.reply, kind: "message", message: "已根据你的补充重新整理操作计划。" },
          }
        : entry,
    );
  }
  const entry: ChatEntry = { id: run.id, role: "assistant", reply: asReply(run) };
  const existing = entries.findIndex((item) => item.role === "assistant" && item.id === run.id);
  if (existing >= 0) return entries.map((item, index) => (index === existing ? entry : item));
  // Older pending plans have no saved reply; anchor them to their original prompt.
  const userIndex = entries.findLastIndex(
    (item) => item.role === "user" && item.message === run.prompt,
  );
  const index = userIndex < 0 ? entries.length : userIndex + 1;
  return [...entries.slice(0, index), entry, ...entries.slice(index)];
}
