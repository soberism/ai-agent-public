import { useEffect, useRef, useState } from "react";
import { ApiError, messageOf, request } from "../../shared/api";
import { upsertRunEntry } from "./agentRunEntries";
import type {
  AgentRun,
  AgentSuggestion,
  AssistantReply,
  AssistantThread,
  ChatEntry,
} from "./types";

const terminalStatuses = new Set(["completed", "failed", "cancelled", "waiting"]);

function safeHistory(entries: ChatEntry[]) {
  return entries.map((entry) =>
    entry.role === "assistant"
      ? { ...entry, reply: { ...entry.reply, action_token: null, action_label: null } }
      : entry,
  );
}

function isAgentRun(value: unknown): value is AgentRun {
  if (!value || typeof value !== "object") return false;
  const run = value as Partial<AgentRun>;
  return (
    typeof run.id === "string" &&
    typeof run.status === "string" &&
    Array.isArray(run.sources) &&
    Array.isArray(run.actions)
  );
}

export function useAssistantChat() {
  const [entries, setEntries] = useState<ChatEntry[]>([]);
  const [threadId, setThreadId] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [run, setRun] = useState<AgentRun | null>(null);
  const [pendingRuns, setPendingRuns] = useState<AgentRun[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const startedRef = useRef(false);
  const pollRef = useRef(0);
  const threadRef = useRef("");

  function stopPolling() {
    pollRef.current += 1;
  }

  async function refreshPending(id: string) {
    try {
      const plans = await request<AgentRun[]>(`/agent/runs/pending/${id}`);
      if (threadRef.current === id) {
        const pending = plans.filter((plan) => isAgentRun(plan) && plan.status === "waiting");
        setPendingRuns(pending);
        setEntries((current) => pending.reduce(upsertRunEntry, current));
      }
    } catch (reason) {
      if (!(reason instanceof ApiError && [404, 405, 501].includes(reason.status))) throw reason;
    }
  }

  async function openThread(fresh = false) {
    const thread = await request<AssistantThread>("/assistant/threads", {
      method: "POST",
      body: JSON.stringify(fresh ? { fresh: true } : {}),
    });
    setThreadId(thread.thread_id);
    threadRef.current = thread.thread_id;
    setExpiresAt(thread.expires_at || "");
    setEntries(fresh ? [] : safeHistory(thread.entries));
    if (fresh) setPendingRuns([]);
    try {
      await refreshPending(thread.thread_id);
    } catch (reason) {
      setError(messageOf(reason));
    }
    try {
      const active = await request<AgentRun>(`/agent/runs/active/${thread.thread_id}`);
      if (isAgentRun(active) && !settle(active)) await poll(active.id);
    } catch (reason) {
      if (!(reason instanceof ApiError && reason.status === 404)) throw reason;
    }
  }

  const openThreadRef = useRef(openThread);
  openThreadRef.current = openThread;

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    openThreadRef
      .current()
      .catch((reason) => setError(messageOf(reason)))
      .finally(() => setBusy(false));
    return stopPolling;
  }, []);

  function settle(next: AgentRun) {
    setRun(next);
    setEntries((current) => upsertRunEntry(current, next));
    setPendingRuns((current) =>
      next.status === "waiting"
        ? [
            next,
            ...current.filter((item) => item.id !== next.id && item.id !== next.parent_plan_id),
          ]
        : current.filter((item) => item.id !== next.id),
    );
    if (next.status === "waiting")
      void refreshPending(next.thread_id).catch((reason) => setError(messageOf(reason)));
    if (!terminalStatuses.has(next.status)) return false;
    setBusy(false);
    return true;
  }

  async function poll(runId: string) {
    const pollId = ++pollRef.current;
    let networkFailures = 0;
    while (pollId === pollRef.current) {
      await new Promise((resolve) => window.setTimeout(resolve, 700));
      try {
        const next = await request<AgentRun>(`/agent/runs/${runId}`);
        if (!isAgentRun(next)) throw new Error("Agent Run 响应格式无效");
        networkFailures = 0;
        if (settle(next)) return;
      } catch (reason) {
        if (reason instanceof ApiError && reason.code === "NETWORK_ERROR" && networkFailures < 3) {
          networkFailures += 1;
          await new Promise((resolve) =>
            window.setTimeout(resolve, 700 * 2 ** (networkFailures - 1)),
          );
          continue;
        }
        throw reason;
      }
    }
  }

  async function legacySend(text: string) {
    const reply = await request<AssistantReply>("/assistant/messages", {
      method: "POST",
      body: JSON.stringify({ thread_id: threadId, message: text }),
    });
    setEntries((current) => [...current, { role: "assistant", reply }]);
  }

  async function startFresh() {
    if (busy) return;
    stopPolling();
    setBusy(true);
    setError("");
    setRun(null);
    try {
      await openThread(true);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function send(text: string, suggestion?: AgentSuggestion | null) {
    if (!text || busy || !threadId) return;
    let accepted = false;
    setEntries((current) => [...current, { role: "user", message: text }]);
    setRun(null);
    setBusy(true);
    setError("");
    try {
      const created = await request<AgentRun>("/agent/runs", {
        method: "POST",
        body: JSON.stringify({
          thread_id: threadId,
          prompt: text,
          ...(suggestion && {
            source_run_id: suggestion.source_run_id,
            suggestion_id: suggestion.id,
          }),
        }),
      });
      if (!isAgentRun(created)) throw new ApiError(404, "RUN_UNAVAILABLE", "自主任务暂不可用");
      accepted = true;
      if (!settle(created)) await poll(created.id);
    } catch (reason) {
      if (!suggestion && reason instanceof ApiError && [404, 405, 501].includes(reason.status)) {
        try {
          await legacySend(text);
        } catch (legacyReason) {
          if (legacyReason instanceof ApiError && legacyReason.code === "THREAD_EXPIRED") {
            setEntries([]);
            try {
              await openThread();
            } catch (threadReason) {
              setError(messageOf(threadReason));
            }
          } else {
            setError(messageOf(legacyReason));
          }
        } finally {
          setBusy(false);
        }
      } else {
        if (suggestion && !accepted)
          setEntries((current) => {
            const last = current.at(-1);
            return last?.role === "user" && last.message === text ? current.slice(0, -1) : current;
          });
        setBusy(false);
        setError(messageOf(reason));
      }
    }
  }

  async function confirm(token: string) {
    if (busy) return;
    setBusy(true);
    setError("");
    setEntries((current) =>
      current.map((entry) =>
        entry.role === "assistant" && entry.reply.action_token === token
          ? { ...entry, reply: { ...entry.reply, action_token: null, action_label: null } }
          : entry,
      ),
    );
    try {
      const reply = await request<AssistantReply>(`/assistant/actions/${token}/confirm`, {
        method: "POST",
        body: "{}",
      });
      setEntries((current) => [...current, { role: "assistant", reply }]);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }

  async function resume(target: AgentRun, actionIds: string[]) {
    if (busy || target.plan_version === null) return;
    setBusy(true);
    setError("");
    try {
      const next = await request<AgentRun>(`/agent/runs/${target.id}/resume`, {
        method: "POST",
        body: JSON.stringify({ plan_version: target.plan_version, selected_action_ids: actionIds }),
      });
      if (!isAgentRun(next)) throw new Error("Agent Run 响应格式无效");
      if (!settle(next)) await poll(next.id);
    } catch (reason) {
      setBusy(false);
      setError(messageOf(reason));
    }
  }

  async function cancel(target: AgentRun) {
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      const next = await request<AgentRun>(`/agent/runs/${target.id}/cancel`, {
        method: "POST",
        body: "{}",
      });
      if (!isAgentRun(next)) throw new Error("Agent Run 响应格式无效");
      settle(next);
    } catch (reason) {
      setBusy(false);
      setError(messageOf(reason));
    }
  }

  return {
    busy,
    cancel,
    confirm,
    entries,
    error,
    expiresAt,
    pendingRuns,
    run,
    resume,
    send,
    startFresh,
    threadId,
  };
}
