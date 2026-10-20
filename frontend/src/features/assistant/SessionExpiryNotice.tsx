import { useEffect, useState } from "react";
import { saveConversation } from "./saveConversation";
import type { ChatEntry } from "./types";

const HOUR = 60 * 60 * 1000;

export function SessionExpiryNotice({
  expiresAt,
  entries,
}: {
  expiresAt: string;
  entries: ChatEntry[];
}) {
  const [remaining, setRemaining] = useState(Infinity);

  useEffect(() => {
    const expiry = Date.parse(expiresAt);
    if (!Number.isFinite(expiry)) {
      setRemaining(Infinity);
      return;
    }
    let timer: number;
    function update() {
      const left = expiry - Date.now();
      setRemaining(left);
      if (left > 0)
        timer = window.setTimeout(update, Math.max(1, left > HOUR ? left - HOUR : left));
    }
    update();
    return () => window.clearTimeout(timer);
  }, [expiresAt]);

  if (remaining > HOUR) return null;
  return (
    <p className="assistant-expiry-notice" role="status">
      {remaining > 0 ? "当前对话将在 1 小时内过期。" : "当前对话已过期，请开始新对话。"}
      {entries.length > 0 && (
        <button type="button" onClick={() => saveConversation(entries)}>
          下载对话
        </button>
      )}
    </p>
  );
}
