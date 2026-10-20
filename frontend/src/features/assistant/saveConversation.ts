import type { ChatEntry } from "./types";

export function saveConversation(entries: ChatEntry[]) {
  const content = entries
    .map((entry) => {
      if (entry.role === "user") return `我：${entry.message}`;
      const items = entry.reply.items.map((item) => `- ${item.title}`).join("\n");
      return `AI：${entry.reply.message}${items ? `\n${items}` : ""}`;
    })
    .join("\n\n");
  const url = URL.createObjectURL(new Blob([content], { type: "text/plain;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = `AI对话-${new Date().toISOString().slice(0, 10)}.txt`;
  document.body.append(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
