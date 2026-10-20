import Input, { TextArea } from "@rc-component/input";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { uncheckedFirst } from "../../shared/uncheckedFirst";
import { Toast } from "../../shared/Toast";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";

type Candidate = { id: string; type: "todo"; title: string; selected: boolean };

import { BackButton } from "../../shared/BackButton";

export function DailyDump() {
  const { call } = useSession();
  const sharing = useSharingEditor("daily_dump");
  const [text, setText] = useState("");
  const [id, setId] = useState("");
  const [items, setItems] = useState<Candidate[]>([]);
  const [created, setCreated] = useState<{ id: string; title: string; url: string }[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function organize() {
    setBusy(true);
    setError("");
    try {
      const result = await sharing.save(() =>
        call<{ id: string; candidates: Candidate[] }>("/workflows/daily-dumps", {
          method: "POST",
          body: JSON.stringify({ text }),
        }),
      );
      setId(result.id);
      setItems(result.candidates);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }
  async function commit() {
    setBusy(true);
    setError("");
    try {
      const result = await call<{ created: { id: string; title: string; url: string }[] }>(
        `/workflows/daily-dumps/${id}/commit`,
        { method: "POST", body: JSON.stringify({ candidates: items }) },
      );
      setCreated(result.created);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="page feature-page">
      <header className="page-header">
        <BackButton className="back button" fallback="/review" />
        <h1>随手记转待办</h1>
      </header>
      <p className="boundary-note">
        把想到的事逐行写下。应用会先生成候选项，只有确认后才写入待办。
      </p>
      {id && <VisibilityControl kind="daily_dump" id={id} />}
      {error && <Toast message={error} tone="error" />}
      {!items.length && !created.length && (
        <section className="feature-card stack">
          <label>
            随手记
            <TextArea
              disabled={sharing.recovering}
              autoComplete="off"
              rows={8}
              value={text}
              onChange={(event) => setText(event.target.value)}
              placeholder={"预约牙医\n周五买猫粮\n整理保险材料"}
            />
          </label>
          <SharingEditor sharing={sharing} disabled={busy} />
          <button
            className="primary"
            disabled={!text.trim() || busy}
            onClick={() => void organize()}
          >
            {busy ? "生成中…" : "生成待办候选"}
          </button>
        </section>
      )}
      {!!items.length && !created.length && (
        <section className="feature-card stack">
          <h2>逐项确认</h2>
          {uncheckedFirst(items, (item) => item.selected).map((item, index) => (
            <label className="check-row" key={item.id}>
              <input
                disabled={sharing.recovering}
                autoComplete="off"
                type="checkbox"
                checked={item.selected}
                onChange={(event) =>
                  setItems((current) =>
                    current.map((value) =>
                      value.id === item.id ? { ...value, selected: event.target.checked } : value,
                    ),
                  )
                }
              />
              <Input
                disabled={sharing.recovering}
                autoComplete="off"
                aria-label={`候选项 ${index + 1}`}
                maxLength={15}
                value={item.title}
                onChange={(event) =>
                  setItems((current) =>
                    current.map((value) =>
                      value.id === item.id ? { ...value, title: event.target.value } : value,
                    ),
                  )
                }
              />
            </label>
          ))}
          <button
            className="primary"
            disabled={busy || !items.some((item) => item.selected && item.title.trim())}
            onClick={() => void commit()}
          >
            确认写入
          </button>
        </section>
      )}
      {!!created.length && (
        <section className="feature-card stack daily-dump-result">
          <h2>整理完成</h2>
          <ul className="daily-dump-results">
            {created.map((item) => (
              <li key={item.id}>
                <Link to={item.url}>
                  <span>{item.title}</span>
                  <span aria-hidden="true">›</span>
                </Link>
              </li>
            ))}
          </ul>
          <button
            className="primary"
            onClick={() => {
              setText("");
              setId("");
              setItems([]);
              setCreated([]);
              setError("");
            }}
          >
            继续整理
          </button>
        </section>
      )}
    </main>
  );
}
