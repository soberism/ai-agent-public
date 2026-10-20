import Input, { TextArea } from "@rc-component/input";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { MemoryList } from "./MemoryList";
import type { AssistantMemory, AssistantPreferences as Preferences } from "./types";

import { PageHeader } from "../../shared/PageHeader";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";

export function AssistantPreferences() {
  const { call } = useSession();
  const [preferences, setPreferences] = useState<Preferences | null>(null);
  const [instructions, setInstructions] = useState("");
  const [memories, setMemories] = useState<AssistantMemory[]>([]);
  const [newMemory, setNewMemory] = useState("");
  const [busyId, setBusyId] = useState("");
  const [loadError, setLoadError] = useState("");
  const { setNotice, toastProps } = useToast();

  const load = useCallback(async () => {
    setLoadError("");
    try {
      const [nextPreferences, nextMemories] = await Promise.all([
        call<Preferences>("/assistant/preferences"),
        call<AssistantMemory[]>("/assistant/memories"),
      ]);
      setPreferences(nextPreferences);
      setInstructions(nextPreferences.custom_instructions);
      setMemories(nextMemories);
    } catch (error) {
      setLoadError(messageOf(error));
    }
  }, [call]);
  useEffect(() => void load(), [load]);

  async function patchPreferences(
    body: Partial<Pick<Preferences, "custom_instructions" | "memory_enabled">>,
  ) {
    setBusyId("preferences");
    setNotice("");
    try {
      const next = await call<Preferences>("/assistant/preferences", {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setPreferences(next);
      setInstructions(next.custom_instructions);
      setNotice("AI 偏好已保存");
    } catch (error) {
      setNotice(messageOf(error), "error");
    } finally {
      setBusyId("");
    }
  }

  async function addMemory(event: React.FormEvent) {
    event.preventDefault();
    setBusyId("new");
    setNotice("");
    try {
      const created = await call<AssistantMemory>("/assistant/memories", {
        method: "POST",
        body: JSON.stringify({ content: newMemory.trim() }),
      });
      setMemories((current) => [created, ...current]);
      setNewMemory("");
    } catch (error) {
      setNotice(messageOf(error), "error");
    } finally {
      setBusyId("");
    }
  }

  async function updateMemory(id: string, body: { content?: string; enabled?: boolean }) {
    setBusyId(id);
    setNotice("");
    try {
      const updated = await call<AssistantMemory>(`/assistant/memories/${id}`, {
        method: "PATCH",
        body: JSON.stringify(body),
      });
      setMemories((current) => current.map((item) => (item.id === id ? updated : item)));
    } catch (error) {
      setNotice(messageOf(error), "error");
      throw error;
    } finally {
      setBusyId("");
    }
  }

  async function deleteMemory(id: string) {
    setBusyId(id);
    setNotice("");
    try {
      await call(`/assistant/memories/${id}`, { method: "DELETE", body: JSON.stringify({}) });
      setMemories((current) => current.filter((item) => item.id !== id));
    } catch (error) {
      setNotice(messageOf(error), "error");
    } finally {
      setBusyId("");
    }
  }

  if (!preferences && !loadError) return <Loading />;
  return (
    <main className="page platform-page assistant-preferences">
      <PageHeader title="偏好与记忆" back="/assistant" />
      {loadError && (
        <section className="state">
          <Toast message={loadError} tone="error" />
          <button onClick={() => void load()}>重新加载</button>
        </section>
      )}
      <Toast {...toastProps} />
      {preferences && (
        <>
          <section className="settings-card stack">
            <h2>自定义指令</h2>
            <label>
              称呼、表达偏好和稳定习惯
              <TextArea
                autoComplete="off"
                value={instructions}
                maxLength={2000}
                onChange={(e) => setInstructions(e.target.value)}
              />
            </label>
            <p className="muted small">不会覆盖权限、写操作确认或真实业务规则。</p>
            <button
              className="primary"
              disabled={busyId === "preferences"}
              onClick={() => void patchPreferences({ custom_instructions: instructions })}
            >
              保存指令
            </button>
          </section>
          <section className="settings-card stack">
            <div className="row">
              <div>
                <h2>长期记忆</h2>
                <p className="muted small">关闭后保留现有内容，但不提供给 AI。</p>
              </div>
              <label className="inline-toggle">
                <input
                  autoComplete="off"
                  type="checkbox"
                  checked={preferences.memory_enabled}
                  disabled={busyId === "preferences"}
                  onChange={(e) => void patchPreferences({ memory_enabled: e.target.checked })}
                />
                启用
              </label>
            </div>
            <form className="inline-create" onSubmit={(event) => void addMemory(event)}>
              <label className="sr-only" htmlFor="new-memory">
                新增记忆
              </label>
              <Input
                autoComplete="off"
                id="new-memory"
                value={newMemory}
                maxLength={500}
                onChange={(e) => setNewMemory(e.target.value)}
                placeholder="例如：我周末习惯早起跑步"
              />
              <button disabled={busyId === "new" || !newMemory.trim()}>添加</button>
            </form>
            <MemoryList
              memories={memories}
              busyId={busyId}
              onUpdate={updateMemory}
              onDelete={deleteMemory}
            />
          </section>
        </>
      )}
    </main>
  );
}
