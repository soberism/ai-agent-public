import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";

type Incoming = { id: string; household_name: string; role: string; expires_at: string | null };
export function IncomingInvitations({ onAccepted }: { onAccepted: () => Promise<void> }) {
  const { call } = useSession();
  const [items, setItems] = useState<Incoming[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const load = useCallback(async () => {
    try {
      setItems((await call<{ items: Incoming[] }>("/households/invitations/incoming")).items);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [call]);
  useEffect(() => void load(), [load]);
  async function decide(id: string, action: "accept" | "reject") {
    setBusy(id);
    try {
      await call(`/households/invitations/${id}/${action}`, { method: "POST", body: "{}" });
      await load();
      if (action === "accept") await onAccepted();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy("");
    }
  }
  if (!items.length && !error) return null;
  return (
    <section className="feature-card stack">
      <h2>收到的家庭邀请</h2>
      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}
      {error && <button onClick={() => void load()}>重新加载邀请</button>}
      {items.map((item) => (
        <article key={item.id} className="stack">
          <strong>{item.household_name}</strong>
          <p className="muted">邀请你作为家庭成员加入</p>
          {item.expires_at && (
            <small className="muted">
              有效期至 {new Date(item.expires_at).toLocaleString("zh-CN")}
            </small>
          )}
          <div className="member-actions">
            <button disabled={!!busy} onClick={() => void decide(item.id, "reject")}>
              拒绝
            </button>
            <button
              className="primary"
              disabled={!!busy}
              onClick={() => void decide(item.id, "accept")}
            >
              接受邀请
            </button>
          </div>
        </article>
      ))}
    </section>
  );
}
