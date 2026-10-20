import { TextArea } from "@rc-component/input";
import { Toast } from "../../shared/Toast";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { VoiceDraft } from "./VoiceDraft";

type VoiceSession = {
  id: string;
  status: string;
  turns: { role: string; content: string }[];
  summary?: string;
};

import { BackButton } from "../../shared/BackButton";

export function VoiceLive() {
  const { call } = useSession();
  const [conversation, setConversation] = useState<VoiceSession | null>(null);
  const [turn, setTurn] = useState("");
  const [error, setError] = useState("");
  async function start() {
    try {
      setConversation(await call<VoiceSession>("/workflows/voice-sessions", { method: "POST" }));
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function send(value = turn) {
    if (!conversation || !value.trim()) return;
    try {
      const next = await call<VoiceSession>(`/workflows/voice-sessions/${conversation.id}/turns`, {
        method: "POST",
        body: JSON.stringify({ transcript: value }),
      });
      setConversation(next);
      setTurn("");
      const reply = next.turns.at(-1)?.content;
      if (reply && "speechSynthesis" in window)
        window.speechSynthesis.speak(new SpeechSynthesisUtterance(reply));
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function end() {
    if (!conversation) return;
    try {
      setConversation(
        await call<VoiceSession>(`/workflows/voice-sessions/${conversation.id}/end`, {
          method: "POST",
        }),
      );
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  return (
    <main className="page feature-page">
      <header className="page-header">
        <BackButton className="back button" fallback="/voice-memos" />
        <h1>实时语音对话</h1>
      </header>
      <p className="boundary-note">
        连续提交每轮转写，结束后生成本次通话摘要；涉及写操作仍需在 AI 助手中确认。
      </p>
      {error && <Toast message={error} tone="error" />}
      {!conversation && (
        <section className="voice-call state">
          <div className="voice-orb" aria-hidden="true">
            ✦
          </div>
          <h2>准备好了吗？</h2>
          <button className="primary" onClick={() => void start()}>
            开始通话
          </button>
        </section>
      )}
      {conversation && conversation.status === "active" && (
        <section className="feature-card stack">
          <h2>通话进行中</h2>
          {conversation.turns.map((item, index) => (
            <p className={`voice-turn ${item.role}`} key={index}>
              {item.content}
            </p>
          ))}
          <VoiceDraft disabled={false} onSend={(value) => void send(value)} />
          <label>
            也可输入本轮内容
            <TextArea
              autoComplete="off"
              value={turn}
              onChange={(event) => setTurn(event.target.value)}
              placeholder="输入后发送"
            />
          </label>
          <div className="row">
            <button className="primary" disabled={!turn.trim()} onClick={() => void send()}>
              发送本轮
            </button>
            <button onClick={() => void end()}>结束并总结</button>
          </div>
        </section>
      )}
      {conversation?.status === "ended" && (
        <section className="state success">
          <h2>通话摘要</h2>
          <p>{conversation.summary}</p>
          <Link className="button primary" to="/assistant">
            交给 AI 助手处理
          </Link>
        </section>
      )}
    </main>
  );
}
