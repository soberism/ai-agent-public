import type { InputRef } from "@rc-component/input";
import Input from "@rc-component/input";
import { ChecklistEditor } from "./ChecklistEditor";
import { uncheckedFirst } from "../../shared/uncheckedFirst";
import { Toast } from "../../shared/Toast";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { useCallback, useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import type { Checklist } from "./types";

import { BackButton } from "../../shared/BackButton";

export function ChecklistDetail() {
  const { id = "" } = useParams();
  const { call } = useSession();
  const navigate = useNavigate();
  const [list, setList] = useState<Checklist | null>(null);
  const inputRef = useRef<InputRef>(null);
  const [title, setTitle] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      setList(await call<Checklist>(`/planning/checklists/${id}`));
    } catch (reason) {
      setError(messageOf(reason));
    }
  }, [call, id]);
  useEffect(() => void load(), [load]);
  async function add(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) return;
    try {
      setList(
        await call<Checklist>(`/planning/checklists/${id}/items`, {
          method: "POST",
          body: JSON.stringify({ title }),
        }),
      );
      setTitle("");
      inputRef.current?.focus({ preventScroll: true });
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function toggle(itemId: string, completed: boolean) {
    try {
      setList(
        await call<Checklist>(`/planning/checklists/${id}/items/${itemId}`, {
          method: "PATCH",
          body: JSON.stringify({ completed }),
        }),
      );
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function remove() {
    try {
      await call(`/planning/checklists/${id}`, { method: "DELETE" });
      navigate("/checklists");
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function action(path: string, body?: object) {
    try {
      setList(
        await call<Checklist>(`/planning/checklists/${id}/${path}`, {
          method: "POST",
          body: body ? JSON.stringify(body) : undefined,
        }),
      );
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  return (
    <main className="page checklist-page">
      <header className="page-header">
        <BackButton className="back button" fallback="/checklists" />
        <h1>{list?.title ?? "清单"}</h1>
      </header>
      {error && <Toast message={error} tone="error" />}
      {list && (
        <>
          <p className="muted">
            {list.completed_count}/{list.total_count} 已完成
          </p>
          <p className="muted small">来源：应用内</p>
          <ChecklistEditor key={list.id} list={list} saved={setList} />
          <div className="checklist-actions">
            <button onClick={() => void action("pin")}>
              {list.pinned ? "取消置顶" : "置顶清单"}
            </button>
            <button onClick={() => void action("bulk", { completed: true })}>全部完成</button>
            <button onClick={() => void action("bulk", { completed: false })}>全部恢复</button>
            <ConfirmButton
              className="danger"
              title="删除清单"
              message={`确认删除“${list.title}”吗？删除后无法恢复。`}
              onConfirm={remove}
            >
              删除清单
            </ConfirmButton>
          </div>
          <form className="inline-create checklist-add" onSubmit={add}>
            <label className="sr-only" htmlFor="item-title">
              清单项
            </label>
            <Input
              autoComplete="off"
              ref={inputRef}
              id="item-title"
              maxLength={15}
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="添加一个项目"
            />
            <button className="primary" disabled={!title.trim()}>
              添加
            </button>
          </form>
          <ul className="check-items">
            {uncheckedFirst(list.items, (item) => item.completed).map((item) => (
              <li key={item.id}>
                <label>
                  <input
                    autoComplete="off"
                    type="checkbox"
                    checked={item.completed}
                    onChange={(e) => void toggle(item.id, e.target.checked)}
                  />
                  <span>{item.title}</span>
                </label>
                <ConfirmButton
                  title="删除清单项"
                  message={`确认删除“${item.title}”吗？删除后无法恢复。`}
                  ariaLabel={`删除清单项 ${item.title}`}
                  className="text-button danger"
                  onConfirm={async () => {
                    setList(
                      await call<Checklist>(`/planning/checklists/${id}/items/${item.id}`, {
                        method: "DELETE",
                      }),
                    );
                  }}
                >
                  删除
                </ConfirmButton>
              </li>
            ))}
          </ul>
        </>
      )}
    </main>
  );
}
