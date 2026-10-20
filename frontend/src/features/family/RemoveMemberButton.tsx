import { useRef, useState } from "react";
import { useSession } from "../../app/session";
import { Modal } from "../../shared/Modal";
import { Toast } from "../../shared/Toast";
import { messageOf } from "../../shared/api";

export function RemoveMemberButton({
  householdId,
  memberId,
  save,
}: {
  householdId: string;
  memberId: string;
  save: (memberId: string, body: Record<string, unknown>) => Promise<boolean>;
}) {
  const { call } = useSession();
  const [impact, setImpact] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  async function preview() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      const value = await call<{ message: string }>(
        `/households/${householdId}/members/${memberId}/removal-impact`,
      );
      setImpact(value.message);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  async function confirm() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    try {
      if (await save(memberId, { status: "removed" })) setImpact(null);
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <button className="danger" disabled={busy} onClick={() => void preview()}>
        移出家庭
      </button>
      <Toast message={error} tone="error" />
      {impact !== null && (
        <Modal
          title="移出家庭"
          close={() => {
            if (!pending.current) setImpact(null);
          }}
          className="confirmation-dialog"
        >
          <p className="confirmation-message">{impact}</p>
          <div className="modal-actions">
            <button disabled={busy} onClick={() => setImpact(null)}>
              取消
            </button>
            <button className="danger" disabled={busy} onClick={() => void confirm()}>
              {busy ? "处理中…" : "确认移出"}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
