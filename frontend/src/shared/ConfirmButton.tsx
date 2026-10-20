import { Toast } from "./Toast";
import { useRef, useState, type ReactNode } from "react";
import { Modal } from "./Modal";
import { messageOf } from "./api";

export function ConfirmButton({
  title,
  message,
  onConfirm,
  children,
  className = "danger",
  disabled = false,
  confirmLabel = "确认删除",
  ariaLabel,
  confirmClassName = "danger",
}: {
  title: string;
  message: ReactNode;
  onConfirm: () => unknown | Promise<unknown>;
  children: ReactNode;
  className?: string;
  disabled?: boolean;
  confirmLabel?: string;
  ariaLabel?: string;
  confirmClassName?: string;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const pending = useRef(false);
  const close = () => {
    if (!pending.current) setOpen(false);
  };
  async function confirm() {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError("");
    try {
      await onConfirm();
      setOpen(false);
    } catch (reason) {
      setError(messageOf(reason));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <>
      <button
        type="button"
        className={className}
        disabled={disabled}
        aria-label={ariaLabel}
        onClick={() => {
          setError("");
          setOpen(true);
        }}
      >
        {children}
      </button>
      {open && (
        <Modal title={title} close={close} className="confirmation-dialog">
          <p className="confirmation-message">{message}</p>
          {error && <Toast message={error} tone="error" />}
          <div className="modal-actions">
            <button type="button" disabled={busy} onClick={close}>
              取消
            </button>
            <button
              type="button"
              className={confirmClassName}
              disabled={busy}
              onClick={() => void confirm()}
            >
              {busy ? "处理中…" : confirmLabel}
            </button>
          </div>
        </Modal>
      )}
    </>
  );
}
