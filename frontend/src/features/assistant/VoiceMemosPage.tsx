import { VoiceMemoCard } from "./VoiceMemoCard";
import { encode } from "./audio";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { PageHeader } from "../../shared/PageHeader";
import { VoiceDraft } from "./VoiceDraft";

export type Memo = {
  id: string;
  transcript: string;
  audio_url?: string | null;
  status: string;
  target_type: "todo" | "event" | null;
  target_id: string | null;
  created_at: string;
};

export function VoiceMemosPage() {
  const { call } = useSession();
  const [items, setItems] = useState<Memo[]>([]);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const [transcribing, setTranscribing] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setItems(await call<Memo[]>("/assistant/voice-memos"));
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [call]);

  useEffect(() => void load(), [load]);
  useEffect(() => {
    if (location.hash.startsWith("#voice-memo-"))
      document.getElementById(location.hash.slice(1))?.scrollIntoView({ block: "start" });
  }, [items]);

  async function convert(item: Memo, targetType: "todo" | "event") {
    await call(`/assistant/voice-memos/${item.id}/convert`, {
      method: "POST",
      body: JSON.stringify({
        target_type: targetType,
        title: Array.from(item.transcript).slice(0, 15).join(""),
      }),
    });
    await load();
  }

  async function saveAudio(audio: Blob, mimeType: string, uploadId: string = crypto.randomUUID()) {
    setSaving(true);
    setError("");
    try {
      if (!audio.size || audio.size > 8 * 1024 * 1024)
        throw new Error("录音不能为空且不得超过 8MB");
      const audioBase64 = await encode(audio);
      const memo = await call<Memo>("/assistant/voice-memos/audio", {
        method: "POST",
        body: JSON.stringify({
          audio_base64: audioBase64,
          mime_type: mimeType,
          upload_id: uploadId,
        }),
      });
      setItems((current) => [memo, ...current]);
    } catch (failure) {
      setError(messageOf(failure));
      throw failure;
    } finally {
      setSaving(false);
    }
  }

  async function transcribe(item: Memo) {
    setTranscribing(item.id);
    setError("");
    try {
      const memo = await call<Memo>(`/assistant/voice-memos/${item.id}/transcribe`, {
        method: "POST",
      });
      setItems((current) => current.map((value) => (value.id === memo.id ? memo : value)));
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setTranscribing(null);
    }
  }

  async function remove(item: Memo) {
    await call(`/assistant/voice-memos/${item.id}`, { method: "DELETE" });
    setItems((current) => current.filter((value) => value.id !== item.id));
  }

  return (
    <main className="page voice-memos-page">
      <PageHeader title="语音备忘" />
      {error && <Toast message={error} tone="error" />}
      <section className="stack-list memo-list" aria-labelledby="memo-list-title">
        <div className="section-heading">
          <h2 id="memo-list-title">我的备忘</h2>
          <small className="muted">{items.length} 条</small>
        </div>
        {items.map((item) => (
          <VoiceMemoCard
            key={item.id}
            item={item}
            transcribing={transcribing}
            transcribe={transcribe}
            convert={convert}
            remove={remove}
          />
        ))}
        {!items.length && !error && (
          <div className="memo-empty">
            <h3>还没有备忘</h3>
            <p>
              待办、灵感或临时安排，都可以先说下来。
              <br />
              按住下方按钮，录下第一条。
            </p>
          </div>
        )}
      </section>
      <section className="memo-recorder" aria-labelledby="memo-record-title">
        <h2 id="memo-record-title">把想到的事，说下来</h2>
        <p>按住录音，松开后直接保存语音。</p>
        <VoiceDraft showLabel disabled={saving} onRecorded={saveAudio} />
      </section>
    </main>
  );
}
