import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export function Toast({
  message,
  tone = "success",
  onClose,
}: {
  message: string;
  tone?: "success" | "error";
  onClose?: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(true);
  const close = useCallback(() => {
    setVisible(false);
    onClose?.();
  }, [onClose]);
  useEffect(() => {
    setVisible(true);
    if (!message) return;
    const timer = window.setTimeout(close, 3000);
    return () => window.clearTimeout(timer);
  }, [message, close]);
  useEffect(() => {
    const element = ref.current;
    if (message && visible) element?.showPopover?.();
    return () => element?.hidePopover?.();
  }, [message, visible]);
  return message && visible
    ? createPortal(
        <div
          ref={ref}
          popover="manual"
          className={`toast ${tone}`}
          role={tone === "error" ? "alert" : "status"}
        >
          <span>{message}</span>
          <button type="button" className="text-button" aria-label="关闭提示" onClick={close}>
            ×
          </button>
        </div>,
        document.body,
      )
    : null;
}
