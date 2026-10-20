import Input from "@rc-component/input";
import { useState } from "react";
import { useSession } from "../../app/session";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { messageOf } from "../../shared/api";
import { Toast } from "../../shared/Toast";
import type { Checklist } from "./types";

export function ChecklistEditor({
  list,
  saved,
}: {
  list: Checklist;
  saved: (list: Checklist) => void;
}) {
  const { call } = useSession();
  const sharing = useSharingEditor("checklist", list.id);
  const [title, setTitle] = useState(list.title);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <details className="feature-card checklist-editor">
      <summary>编辑清单</summary>
      <form
        className="stack"
        onSubmit={async (event) => {
          event.preventDefault();
          if (busy) return;
          setBusy(true);
          setError("");
          try {
            saved(
              await sharing.save(() =>
                call<Checklist>(`/planning/checklists/${list.id}`, {
                  method: "PATCH",
                  body: JSON.stringify({ title }),
                }),
              ),
            );
          } catch (failure) {
            setError(messageOf(failure));
          } finally {
            setBusy(false);
          }
        }}
      >
        <label>
          清单名称
          <Input
            value={title}
            maxLength={15}
            required
            disabled={busy || sharing.recovering}
            onChange={(event) => setTitle(event.target.value)}
          />
        </label>
        <SharingEditor sharing={sharing} disabled={busy} />
        {error && <Toast message={error} tone="error" />}
        <button className="primary" disabled={busy}>
          保存
        </button>
      </form>
    </details>
  );
}
