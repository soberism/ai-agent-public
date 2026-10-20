import type { InputRef } from "@rc-component/input";
import Input from "@rc-component/input";
import { Toast } from "../../shared/Toast";
import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useAssistantChat } from "./useAssistantChat";
import { VoiceDraft } from "./VoiceDraft";
import { AssistantTimeline } from "./AssistantTimeline";
import { AssistantHeader } from "./AssistantHeader";
import { AssistantEmpty } from "./AssistantEmpty";
import { AssistantSuggestionDraft } from "./AssistantSuggestionDraft";
import type { AgentSuggestion } from "./types";
import { SessionExpiryNotice } from "./SessionExpiryNotice";
import { useAssistantClose } from "./useAssistantClose";

export function Assistant() {
  const { closing, close, onAnimationEnd, pageRef } = useAssistantClose();
  const [message, setMessage] = useState("");
  const [selectedSuggestion, setSelectedSuggestion] = useState<AgentSuggestion | null>(null);
  const previousDraft = useRef("");
  const [voiceTranscribing, setVoiceTranscribing] = useState(false);
  const [voiceRecording, setVoiceRecording] = useState(false);
  const {
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
  } = useAssistantChat();
  const inputRef = useRef<InputRef>(null);
  const contentRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const content = contentRef.current;
    if (content) content.scrollTop = entries.length ? content.scrollHeight : 0;
  }, [entries, busy, error]);

  function sendMessage(value: string) {
    const text = value.trim();
    if (!text || busy || !threadId) return;
    setMessage("");
    void send(text, selectedSuggestion);
    setSelectedSuggestion(null);
    previousDraft.current = "";
    inputRef.current?.focus();
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    sendMessage(message);
  }

  function chooseSuggestion(suggestion: AgentSuggestion) {
    if (!suggestion.draft || busy) return;
    if (!selectedSuggestion) previousDraft.current = message;
    setSelectedSuggestion(suggestion);
    setMessage(suggestion.draft);
    inputRef.current?.focus();
  }

  async function startNewThread() {
    setSelectedSuggestion(null);
    setMessage("");
    previousDraft.current = "";
    await startFresh();
  }

  return (
    <main
      ref={pageRef}
      className={`page assistant-page${closing ? " assistant-page-closing" : ""}`}
      onAnimationEnd={onAnimationEnd}
    >
      <div className="assistant-shell">
        <AssistantHeader busy={busy} startFresh={startNewThread} close={close} />
        <SessionExpiryNotice expiresAt={expiresAt} entries={entries} />
        <div className="assistant-content" ref={contentRef}>
          {!entries.length && <AssistantEmpty disabled={busy || !threadId} onSend={sendMessage} />}
          <section className="chat-log" aria-live="polite" aria-label="对话消息">
            <AssistantTimeline
              entries={entries}
              busy={busy}
              run={run}
              pendingRuns={pendingRuns}
              onCancel={cancel}
              onResume={resume}
              onConfirm={confirm}
              onChoose={chooseSuggestion}
            />
            {error && <Toast message={error} tone="error" />}
          </section>
        </div>
        <form className="chat-input" onSubmit={submit}>
          <AssistantSuggestionDraft
            suggestion={selectedSuggestion}
            onCancel={() => {
              setSelectedSuggestion(null);
              setMessage(previousDraft.current);
              previousDraft.current = "";
            }}
          />
          <label className="sr-only" htmlFor="assistant-message">
            对话内容
          </label>
          <Input
            autoComplete="off"
            ref={inputRef}
            id="assistant-message"
            value={message}
            onChange={(event) => {
              setMessage(event.target.value);
              if (
                selectedSuggestion &&
                !event.target.value.startsWith(selectedSuggestion.draft || "")
              ) {
                setSelectedSuggestion(null);
                previousDraft.current = "";
              }
            }}
            maxLength={1000}
            placeholder={
              voiceRecording ? "语音输入中" : voiceTranscribing ? "语音转换中" : "有什么想交给我？"
            }
            disabled={!threadId || voiceRecording || voiceTranscribing}
          />
          {message.trim() ? (
            <button
              className="button primary"
              disabled={busy || !threadId || voiceTranscribing || voiceRecording}
            >
              发送
            </button>
          ) : (
            <VoiceDraft
              disabled={busy || !threadId}
              onTranscribed={(text) =>
                setMessage((current) => [current.trim(), text.trim()].filter(Boolean).join(" "))
              }
              onTranscribingChange={setVoiceTranscribing}
              onRecordingChange={(recording) => {
                if (recording) inputRef.current?.blur();
                setVoiceRecording(recording);
              }}
            />
          )}
        </form>
      </div>
    </main>
  );
}
