import Input from "@rc-component/input";
import { ChecklistCard } from "./ChecklistCard";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import type { Checklist } from "./types";
import { BackButton } from "../../shared/BackButton";

export function ChecklistList() {
  const { call } = useSession();
  const navigate = useNavigate();
  const [items, setItems] = useState<Checklist[] | null>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [duplicating, setDuplicating] = useState<string | null>(null);
  const load = useCallback(async () => {
    try {
      setItems((await call<{ items: Checklist[] }>("/planning/checklists")).items);
      setError("");
    } catch (reason) {
      setError(messageOf(reason));
    }
  }, [call]);
  useEffect(() => void load(), [load]);
  async function create(event: FormEvent) {
    event.preventDefault();
    if (busy || !title.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await call<Checklist>("/planning/checklists", {
        method: "POST",
        body: JSON.stringify({ title }),
      });
      navigate(`/checklists/${result.id}`);
    } catch (reason) {
      setError(messageOf(reason));
      setBusy(false);
    }
  }
  async function duplicate(id: string) {
    if (duplicating !== null) return;
    setDuplicating(id);
    setError("");
    try {
      const copy = await call<Checklist>(`/planning/checklists/${id}/duplicate`, {
        method: "POST",
      });
      navigate(`/checklists/${copy.id}`);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setDuplicating(null);
    }
  }
  return (
    <main className="page checklist-page">
      <div className="checklist-sticky-header">
        <header className="page-header">
          <BackButton className="back button" fallback="/features" />
          <h1>清单</h1>
        </header>
        <form className="inline-create" onSubmit={create}>
          <label className="sr-only" htmlFor="checklist-title">
            清单名称
          </label>
          <Input
            autoComplete="off"
            id="checklist-title"
            maxLength={15}
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例如：旅行准备"
          />
          <button className="primary" disabled={busy || !title.trim()}>
            新建
          </button>
        </form>
      </div>
      {error && <Toast message={error} tone="error" />}
      {items === null ? (
        error ? (
          <button onClick={() => void load()}>重新加载</button>
        ) : (
          <p role="status">正在加载清单…</p>
        )
      ) : items.length === 0 ? (
        <section className="checklist-empty" aria-labelledby="checklist-empty-title">
          <svg className="checklist-empty-art" viewBox="0 0 160 140" fill="none" aria-hidden="true">
            <circle cx="80" cy="70" r="62" fill="var(--purple)" />
            <rect
              x="43"
              y="24"
              width="78"
              height="98"
              rx="12"
              fill="var(--surface)"
              stroke="var(--purple-ink)"
              strokeWidth="2"
            />
            <rect x="65" y="18" width="34" height="13" rx="6" fill="var(--purple-ink)" />
            <path
              d="m56 52 4 4 8-9M56 75l4 4 8-9"
              stroke="var(--purple-ink)"
              strokeWidth="3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <path
              d="M77 53h29M77 76h22M77 99h26"
              stroke="var(--line)"
              strokeWidth="4"
              strokeLinecap="round"
            />
            <rect
              x="56"
              y="94"
              width="10"
              height="10"
              rx="3"
              stroke="var(--purple-ink)"
              strokeWidth="2"
            />
          </svg>
          <h2 id="checklist-empty-title">还没有清单</h2>
          <p>
            把要准备的事记下来，逐项勾选。
            <br />
            下次需要时，还能复用整份清单。
          </p>
          <div className="checklist-empty-suggestions" aria-label="常用名称建议">
            {["旅行准备", "每周采购", "出门必带"].map((name) => (
              <button
                key={name}
                type="button"
                onClick={() => {
                  setTitle(name);
                  document.getElementById("checklist-title")?.focus();
                }}
              >
                {name}
                <span aria-hidden="true">＋</span>
              </button>
            ))}
          </div>
          <p className="checklist-empty-hint">选一个名称，或在上方输入你的想法</p>
        </section>
      ) : (
        <ul className="checklist-list">
          {items.map((item) => (
            <ChecklistCard
              key={item.id}
              item={item}
              duplicating={duplicating}
              duplicate={duplicate}
              remove={async (id) => {
                await call(`/planning/checklists/${id}`, { method: "DELETE" });
                setItems((current) => current?.filter((entry) => entry.id !== id) ?? null);
              }}
            />
          ))}
        </ul>
      )}
    </main>
  );
}
