import Input from "@rc-component/input";
import { useState } from "react";
import { Modal } from "./Modal";

const validTime = (value: string) => /^([01]\d|2[0-3]):[0-5]\d$/.test(value);
const commonMinutes = ["00", "15", "30", "45"];

export function TimePicker({
  value,
  select,
  close,
}: {
  value: string;
  select: (value: string) => void;
  close: () => void;
}) {
  const [time, setTime] = useState(validTime(value) ? value : "09:00");
  const [hour, minute] = time.split(":");
  const update = (part: number, next: string) => {
    const parts = time.includes(":") ? time.split(":") : ["09", "00"];
    parts[part] = next;
    setTime(parts.join(":"));
  };
  return (
    <Modal title="选择时间" close={close} className="time-picker-dialog">
      <div className="time-preview">
        <Input
          aria-label="直接输入时间"
          inputMode="numeric"
          maxLength={5}
          placeholder="09:00"
          value={time}
          aria-invalid={!validTime(time)}
          onChange={(event) => {
            const next = event.target.value.replace(/[^\d:]/g, "");
            setTime(/^\d{4}$/.test(next) ? `${next.slice(0, 2)}:${next.slice(2)}` : next);
          }}
        />
        <span>24 小时制 · 可直接输入</span>
      </div>
      <h3 className="time-group-title">小时</h3>
      <div className="time-grid" role="group" aria-label="小时">
        {Array.from({ length: 24 }, (_, index) => {
          const number = String(index).padStart(2, "0");
          return (
            <button
              type="button"
              key={number}
              aria-label={`${number}时`}
              aria-pressed={hour === number}
              onClick={() => update(0, number)}
            >
              {number}
            </button>
          );
        })}
      </div>
      <h3 className="time-group-title time-minute-title">分钟</h3>
      <div className="time-minute-grid" role="group" aria-label="分钟">
        {commonMinutes.map((number) => (
          <button
            type="button"
            key={number}
            aria-label={`${number}分`}
            aria-pressed={minute === number}
            onClick={() => update(1, number)}
          >
            {number}
          </button>
        ))}
      </div>
      <label className="precise-minute">
        精确分钟（00–59）
        <Input
          type="number"
          inputMode="numeric"
          min={0}
          max={59}
          step={1}
          value={minute && /^\d+$/.test(minute) ? Number(minute) : ""}
          onChange={(event) =>
            update(1, event.target.value === "" ? "" : event.target.value.padStart(2, "0"))
          }
        />
      </label>
      <button
        type="button"
        className="primary full"
        disabled={!validTime(time)}
        onClick={() => {
          if (!validTime(time)) return;
          select(time);
          close();
        }}
      >
        确认时间
      </button>
    </Modal>
  );
}
