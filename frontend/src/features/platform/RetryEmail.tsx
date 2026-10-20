import { Toast } from "../../shared/Toast";
import { useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";

export function RetryEmail({ id, done }: { id: string; done: () => void }) {
  const { call } = useSession();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      <button
        disabled={busy}
        onClick={async () => {
          setBusy(true);
          setError("");
          try {
            await call(`/mail/notifications/${id}/retry`, { method: "POST" });
            done();
          } catch (failure) {
            setError(messageOf(failure));
          } finally {
            setBusy(false);
          }
        }}
      >
        {busy ? "发送中…" : "重试发送"}
      </button>
      {error && <Toast message={error} tone="error" />}
    </>
  );
}
