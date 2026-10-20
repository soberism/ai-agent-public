import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import type { NotificationItem } from "./types";

export function NotificationsPage() {
  const { call } = useSession();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    try {
      setItems((await call<{ items: NotificationItem[] }>("/notifications")).items);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call]);
  useEffect(() => void load(), [load]);

  async function read(item: NotificationItem) {
    if (item.read) return;
    try {
      await call(`/notifications/${item.id}/read`, { method: "POST", body: "{}" });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }

  async function decide(item: NotificationItem, action: "accept" | "reject") {
    if (!item.invitation_id) return;
    setBusy(item.id);
    try {
      await call(`/households/invitations/${item.invitation_id}/${action}`, {
        method: "POST",
        body: "{}",
      });
      await call(`/notifications/${item.id}/read`, { method: "POST", body: "{}" });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="page feature-page">
      <PageHeader title="站内通知" back="/settings" />
      {error && <Toast message={error} tone="error" />}
      {!loaded ? (
        <Loading compact />
      ) : !items.length ? (
        <section className="feature-card empty">
          <h2>暂无通知</h2>
          <p className="muted">家庭邀请、指派和重要变更会显示在这里。</p>
        </section>
      ) : (
        <section className="feature-card">
          <ul className="notification-list">
            {items.map((item) => (
              <li className={item.read ? "read" : ""} key={item.id}>
                <div>
                  <strong>{item.title}</strong>
                  <time>{new Date(item.created_at).toLocaleString("zh-CN")}</time>
                </div>
                <p>{item.message}</p>
                {item.type === "invitation" && item.invitation_id && !item.read ? (
                  <div className="member-actions">
                    <button disabled={busy === item.id} onClick={() => void decide(item, "reject")}>
                      拒绝
                    </button>
                    <button
                      className="confirm-button"
                      disabled={busy === item.id}
                      onClick={() => void decide(item, "accept")}
                    >
                      接受邀请
                    </button>
                  </div>
                ) : (
                  <button
                    className="text-button"
                    disabled={item.read}
                    onClick={() => void read(item)}
                  >
                    {item.read ? "已读" : "标为已读"}
                  </button>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}
