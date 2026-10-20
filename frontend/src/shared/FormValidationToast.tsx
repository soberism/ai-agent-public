import { useEffect, useRef, type FormEvent, type ReactNode } from "react";
import { Toast } from "./Toast";
import { useToast } from "./useToast";

export function FormValidationToast({ children }: { children: ReactNode }) {
  const { setNotice, toastProps } = useToast();
  const reporting = useRef(false);
  const resetTimer = useRef<number | undefined>(undefined);
  useEffect(() => () => window.clearTimeout(resetTimer.current), []);
  const invalid = (event: FormEvent<HTMLDivElement>) => {
    if (event.defaultPrevented) return;
    const field = event.target;
    if (
      !(field instanceof HTMLInputElement) &&
      !(field instanceof HTMLTextAreaElement) &&
      !(field instanceof HTMLSelectElement)
    )
      return;
    event.preventDefault();
    if (reporting.current) return;
    reporting.current = true;
    resetTimer.current = window.setTimeout(() => {
      reporting.current = false;
    }, 0);
    const labelNode = field.labels?.[0]?.cloneNode(true);
    if (labelNode instanceof HTMLElement) {
      labelNode
        .querySelectorAll("input, textarea, select, button")
        .forEach((node) => node.remove());
    }
    const label = labelNode?.textContent?.trim() || field.getAttribute("aria-label") || "此字段";
    setNotice(
      field.validity.valueMissing ? `请填写${label}` : `${label}：${field.validationMessage}`,
      "error",
    );
    field.focus();
  };
  return (
    <div style={{ display: "contents" }} onInvalid={invalid}>
      <Toast {...toastProps} />
      {children}
    </div>
  );
}
