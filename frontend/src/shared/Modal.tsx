import { createPortal } from "react-dom";
import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
export function Modal({
  title,
  children,
  close,
  className,
}: {
  title: string;
  children: ReactNode;
  close: () => void;
  className?: string;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    const dialog = ref.current;
    dialog?.showModal();
    dialog?.focus();
    return () => {
      dialog?.close();
      if (previous instanceof HTMLInputElement || previous instanceof HTMLTextAreaElement)
        previous.blur();
      else previous?.focus();
    };
  }, []);
  return createPortal(
    <dialog
      ref={ref}
      className={className}
      tabIndex={-1}
      aria-label={title}
      onCancel={(event) => {
        event.preventDefault();
        close();
      }}
    >
      <header className="row">
        <h2>{title}</h2>
        <button type="button" className="icon-button" aria-label={`关闭${title}`} onClick={close}>
          ×
        </button>
      </header>
      {children}
    </dialog>,
    document.body,
  );
}
