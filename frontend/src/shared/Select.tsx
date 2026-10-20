import { Children, isValidElement, useEffect, useId, useRef, useState } from "react";
import type { ReactNode, SelectHTMLAttributes } from "react";
import { Modal } from "./Modal";

type Option = { value: string; label: ReactNode; disabled: boolean };
function optionsOf(children: ReactNode, disabled = false): Option[] {
  const options: Option[] = [];
  Children.forEach(children, (child) => {
    if (
      !isValidElement<{ value?: string | number; children?: ReactNode; disabled?: boolean }>(child)
    )
      return;
    if (child.type === "option") {
      options.push({
        value: String(child.props.value ?? child.props.children ?? ""),
        label: child.props.children,
        disabled: disabled || !!child.props.disabled,
      });
    } else options.push(...optionsOf(child.props.children, disabled || !!child.props.disabled));
  });
  return options;
}

export function Select({
  children,
  value,
  defaultValue,
  id,
  className,
  onChange,
  onInvalid,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  const generatedId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const native = useRef<HTMLSelectElement>(null);
  const [open, setOpen] = useState(false);
  const options = optionsOf(children);
  const [chosen, setChosen] = useState(String(defaultValue ?? options[0]?.value ?? ""));
  const selected = String(
    value ??
      (options.some((option) => option.value === chosen) ? chosen : (options[0]?.value ?? "")),
  );
  useEffect(() => {
    const form = native.current?.form;
    let frame = 0;
    const reset = () => {
      frame = requestAnimationFrame(() => setChosen(native.current?.value ?? ""));
    };
    form?.addEventListener("reset", reset);
    return () => {
      form?.removeEventListener("reset", reset);
      cancelAnimationFrame(frame);
    };
  }, []);
  return (
    <div className={`picker-field ${className ?? ""}`}>
      <button
        id={id ?? generatedId}
        ref={trigger}
        type="button"
        className="picker-trigger"
        disabled={props.disabled}
        aria-label={props["aria-label"]}
        aria-describedby={props["aria-describedby"]}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => {
          setOpen(true);
        }}
      >
        <span>{options.find((option) => option.value === selected)?.label ?? "请选择"}</span>
        <span className="event-status-chevron" aria-hidden="true" />
      </button>
      <select
        {...props}
        ref={native}
        id={`${id ?? generatedId}-native`}
        className="picker-native"
        tabIndex={-1}
        aria-hidden="true"
        value={value}
        defaultValue={defaultValue}
        onChange={(event) => {
          setChosen(event.target.value);
          onChange?.(event);
        }}
        onInvalid={(event) => {
          event.preventDefault();
          trigger.current?.focus();
          setOpen(true);
          onInvalid?.(event);
        }}
      >
        {children}
      </select>
      {open && (
        <Modal
          className="select-dialog"
          title={props["aria-label"] ?? "选择选项"}
          close={() => setOpen(false)}
        >
          <div className="picker-options">
            {options.map((option, index) => (
              <button
                type="button"
                key={`${option.value}-${index}`}
                disabled={option.disabled}
                aria-pressed={selected === option.value}
                onClick={() => {
                  if (!native.current) return;
                  native.current.value = option.value;
                  native.current.dispatchEvent(new Event("change", { bubbles: true }));
                  setOpen(false);
                }}
              >
                <span>{option.label}</span>
                <span aria-hidden="true">{selected === option.value ? "✓" : ""}</span>
              </button>
            ))}
          </div>
        </Modal>
      )}
    </div>
  );
}
