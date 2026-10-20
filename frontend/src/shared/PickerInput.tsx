import { lunarTileContent } from "./LunarDate";
import { useEffect, useId, useRef, useState } from "react";
import type { InputHTMLAttributes } from "react";
import MonthCalendar from "react-calendar";
import "react-calendar/dist/Calendar.css";
import { Modal } from "./Modal";
import { TimePicker } from "./TimePicker";

export function PickerInput({
  type,
  value,
  defaultValue,
  id,
  className,
  onChange,
  onInvalid,
  ...props
}: InputHTMLAttributes<HTMLInputElement>) {
  const generatedId = useId();
  const native = useRef<HTMLInputElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const [step, setStep] = useState<"date" | "time" | null>(null);
  const [chosen, setChosen] = useState(String(defaultValue ?? ""));
  const [draftDate, setDraftDate] = useState("");
  const selected = String(value ?? chosen);
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
  const date = (draftDate || selected).split("T")[0];
  const time = type === "datetime-local" ? (selected.split("T")[1] ?? "") : selected;
  function commit(next: string) {
    const input = native.current;
    if (!input) return;
    Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set?.call(input, next);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
    setChosen(input.value);
    setStep(null);
  }
  function open() {
    setDraftDate("");
    setStep(type === "time" ? "time" : "date");
  }
  return (
    <div className={`picker-field ${className ?? ""}`}>
      <button
        id={id ?? generatedId}
        ref={trigger}
        type="button"
        className="picker-trigger"
        disabled={props.disabled || props.readOnly}
        aria-label={props["aria-label"]}
        aria-describedby={props["aria-describedby"]}
        aria-haspopup="dialog"
        aria-expanded={step !== null}
        onClick={open}
      >
        <span>
          {selected.replaceAll("-", "/").replace("T", " ") ||
            props.placeholder ||
            (type === "time" ? "选择时间" : "选择日期")}
        </span>
        <span className="event-status-chevron" aria-hidden="true" />
      </button>
      <input
        {...props}
        type={type}
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
          open();
          onInvalid?.(event);
        }}
      />
      {step === "date" && (
        <Modal title="选择日期" close={() => setStep(null)}>
          <div className="month-calendar">
            <MonthCalendar
              locale="zh-CN"
              calendarType="iso8601"
              tileContent={lunarTileContent}
              value={
                date && !Number.isNaN(Date.parse(date)) ? new Date(`${date}T12:00:00`) : new Date()
              }
              minDate={
                props.min ? new Date(`${String(props.min).split("T")[0]}T00:00:00`) : undefined
              }
              maxDate={
                props.max ? new Date(`${String(props.max).split("T")[0]}T23:59:59`) : undefined
              }
              onChange={(next) => {
                if (!(next instanceof Date)) return;
                const formatted = `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, "0")}-${String(next.getDate()).padStart(2, "0")}`;
                if (type === "datetime-local") {
                  setDraftDate(formatted);
                  setStep("time");
                } else commit(formatted);
              }}
            />
          </div>
        </Modal>
      )}
      {step === "time" && (
        <TimePicker
          value={time}
          select={(next) => commit(type === "datetime-local" ? `${date}T${next}` : next)}
          close={() => setStep(null)}
        />
      )}
    </div>
  );
}
