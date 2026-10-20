import { uncheckedFirst } from "../../shared/uncheckedFirst";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import { ReviewCard } from "./ReviewCard";
import { ConfirmButton } from "../../shared/ConfirmButton";
import type { ReviewItem } from "./types";

export function DocumentReviewPage() {
  const { call } = useSession();
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [selected, setSelected] = useState<string[]>([]);
  const load = useCallback(async () => {
    try {
      setItems(
        (await call<{ items: ReviewItem[] }>("/documents/review-items?status=pending")).items,
      );
      setSelected([]);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call]);
  useEffect(() => void load(), [load]);

  async function update(item: ReviewItem, action: "save" | "accept" | "ignore", title: string) {
    setBusy(item.id);
    setError("");
    try {
      const path = `/documents/review-items/${item.id}`;
      if (title !== item.title)
        await call(path, { method: "PATCH", body: JSON.stringify({ title }) });
      if (action !== "save") await call(`${path}/${action}`, { method: "POST", body: "{}" });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setBusy("");
    }
  }
  async function acceptAll() {
    const ids = selected.length ? selected : items.map((item) => item.id);
    setBusy("all");
    setError("");
    try {
      await call("/workflows/document-review/batch", {
        method: "POST",
        body: JSON.stringify({ item_ids: ids, action: "accept" }),
      });
      await load();
    } finally {
      setBusy("");
    }
  }

  return (
    <main className="page feature-page">
      <PageHeader title="待审核" />
      <section className="feature-intro">
        <h2>确认后才写入</h2>
        <p>逐项核对标题、来源证据和识别置信度。忽略不会删除原材料。</p>
      </section>
      {error && <Toast message={error} tone="error" />}
      {!loaded ? (
        <Loading compact />
      ) : !items.length ? (
        <section className="feature-card empty">
          <h2>没有待审核内容</h2>
          <p className="muted">新材料识别完成后会出现在这里。</p>
          <Link className="button" to="/documents">
            上传材料
          </Link>
        </section>
      ) : (
        <>
          <div className="review-batch">
            <span>已选择 {selected.length || items.length} 项</span>
            <ConfirmButton
              title="接受审核内容"
              message={`接受 ${selected.length || items.length} 项并写入计划？`}
              onConfirm={acceptAll}
              className="confirm-button"
              confirmClassName="primary"
              confirmLabel="接受并写入"
              disabled={Boolean(busy)}
            >
              接受全部
            </ConfirmButton>
          </div>
          <div className="review-stack">
            {uncheckedFirst(items, (item) => selected.includes(item.id)).map((item) => (
              <ReviewCard
                key={item.id}
                item={item}
                busy={busy === item.id || busy === "all"}
                update={update}
                selected={selected.includes(item.id)}
                toggle={() =>
                  setSelected((current) =>
                    current.includes(item.id)
                      ? current.filter((id) => id !== item.id)
                      : [...current, item.id],
                  )
                }
              />
            ))}
          </div>
        </>
      )}
    </main>
  );
}
