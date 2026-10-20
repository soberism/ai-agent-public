import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { Modal } from "../../shared/Modal";
import { messageOf } from "../../shared/api";
import type { NotificationItem } from "./types";

type Invitation = { id: string; household_name: string; role: string };
export function FamilyAttention({ onCount }: { onCount: (count: number) => void }) {
  const { call } = useSession();
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [feedback, setFeedback] = useState<NotificationItem[]>([]);
  const [open, setOpen] = useState<"invitations" | "feedback" | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    try {
      const [incoming, notifications] = await Promise.all([
        call<{ items: Invitation[] }>("/households/invitations/incoming"),
        call<{ items: NotificationItem[] }>("/notifications"),
      ]);
      const results = notifications.items.filter(
        (item) => item.type === "invitation_result" && !item.read,
      );
      setInvitations(incoming.items);
      setFeedback(results);
      setError("");
      onCount(incoming.items.length + results.length);
    } catch (failure) {
      setError(messageOf(failure));
      onCount(1);
    }
  }, [call, onCount]);
  useEffect(() => {
    void load();
    const refresh = () => void load();
    window.addEventListener("focus", refresh);
    return () => window.removeEventListener("focus", refresh);
  }, [load]);
  async function act(path: string) {
    setBusy(true);
    setError("");
    try {
      await call(path, { method: "POST", body: "{}" });
      setOpen(null);
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {invitations.length > 0 && (
        <button className="family-attention-entry" onClick={() => setOpen("invitations")}>
          <strong>{invitations.length}</strong>
          <small>家庭邀请</small>
        </button>
      )}
      {feedback.length > 0 && (
        <button className="family-attention-entry" onClick={() => setOpen("feedback")}>
          <strong>{feedback.length}</strong>
          <small>邀请反馈</small>
        </button>
      )}
      {error && !open && (
        <button className="text-button" onClick={() => void load()}>
          家庭邀请加载失败，重试
        </button>
      )}
      {open && (
        <Modal
          title={open === "invitations" ? "收到的家庭邀请" : "家庭邀请反馈"}
          close={() => {
            if (!busy) setOpen(null);
          }}
        >
          <div className="stack family-attention-details">
            {error && (
              <p className="error" role="alert">
                {error}
              </p>
            )}
            {open === "invitations" ? (
              invitations.length ? (
                invitations.map((item) => (
                  <article className="stack" key={item.id}>
                    <strong>{item.household_name}</strong>
                    <p className="muted small">邀请你作为家庭成员 加入，个人内容不会自动共享。</p>
                    <div className="member-actions">
                      <button
                        disabled={busy}
                        onClick={() => void act(`/households/invitations/${item.id}/reject`)}
                      >
                        拒绝
                      </button>
                      <button
                        className="primary"
                        disabled={busy}
                        onClick={() => void act(`/households/invitations/${item.id}/accept`)}
                      >
                        接受邀请
                      </button>
                    </div>
                  </article>
                ))
              ) : (
                <p className="muted" role="status">
                  邀请已处理，暂无待处理邀请。
                </p>
              )
            ) : feedback.length ? (
              feedback.map((item) => (
                <article className="stack" key={item.id}>
                  <strong>{item.message}</strong>
                  <time className="muted small">
                    {new Date(item.created_at).toLocaleString("zh-CN")}
                  </time>
                  <button
                    className="text-button"
                    disabled={busy}
                    onClick={() => void act(`/notifications/${item.id}/read`)}
                  >
                    标为已读
                  </button>
                </article>
              ))
            ) : (
              <p className="muted" role="status">
                暂无未读邀请反馈。
              </p>
            )}
          </div>
        </Modal>
      )}
    </>
  );
}
