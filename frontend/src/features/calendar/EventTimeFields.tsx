import { useState, type Dispatch, type SetStateAction } from "react";
import { PickerInput } from "../../shared/PickerInput";
import type { EventValues } from "./types";

const durations = [30, 60, 120, 240, 480, 720];

function endAfter(values: EventValues, minutes: number): EventValues {
  const start = new Date(`${values.start_date}T${values.start_time}:00Z`);
  if (Number.isNaN(start.getTime())) return { ...values, end_date: "", end_time: "" };
  start.setUTCMinutes(start.getUTCMinutes() + minutes);
  const end = start.toISOString();
  return { ...values, end_date: end.slice(0, 10), end_time: end.slice(11, 16) };
}

export function EventTimeFields({
  values,
  setValues,
}: {
  values: EventValues;
  setValues: Dispatch<SetStateAction<EventValues>>;
}) {
  const initialDuration =
    (Date.parse(`${values.end_date}T${values.end_time}:00Z`) -
      Date.parse(`${values.start_date}T${values.start_time}:00Z`)) /
    60000;
  const [duration, setDuration] = useState(
    durations.includes(initialDuration) ? initialDuration : 60,
  );
  const [custom, setCustom] = useState(!durations.includes(initialDuration));
  function updateStart(key: "start_date" | "start_time", value: string) {
    setValues((current) => {
      const next = { ...current, [key]: value };
      return custom ? next : endAfter(next, duration);
    });
  }
  return (
    <div className="stack event-time-fields">
      <div className="event-time-grid">
        <label>
          日期
          <PickerInput
            type="date"
            aria-label="日期"
            value={values.start_date}
            onChange={(event) => updateStart("start_date", event.target.value)}
          />
        </label>
        <label>
          开始时间
          <PickerInput
            type="time"
            aria-label="开始时间"
            value={values.start_time}
            onChange={(event) => updateStart("start_time", event.target.value)}
          />
        </label>
      </div>
      <fieldset className="event-duration">
        <legend>时长</legend>
        <div className="chips">
          {durations.map((minutes) => (
            <button
              key={minutes}
              type="button"
              className={!custom && duration === minutes ? "chip selected" : "chip"}
              aria-pressed={!custom && duration === minutes}
              onClick={() => {
                setCustom(false);
                setDuration(minutes);
                setValues((current) => endAfter(current, minutes));
              }}
            >
              {minutes < 60 ? `${minutes} 分钟` : `${minutes / 60} 小时`}
            </button>
          ))}
        </div>
      </fieldset>
      <div className="event-end-summary">
        <span className="muted">
          {values.end_date && values.end_time
            ? `结束于 ${values.end_date === values.start_date ? "" : `${values.end_date} `}${values.end_time}`
            : "请选择日期和开始时间"}
        </span>
        <button
          type="button"
          className="text-button"
          aria-expanded={custom}
          onClick={() => {
            if (custom) setValues((current) => endAfter(current, duration));
            setCustom(!custom);
          }}
        >
          {custom ? "按时长设置" : "自定义结束时间"}
        </button>
      </div>
      {custom && (
        <div className="event-time-grid">
          <label>
            结束日期
            <PickerInput
              type="date"
              aria-label="结束日期"
              value={values.end_date}
              onChange={(event) =>
                setValues((current) => ({ ...current, end_date: event.target.value }))
              }
            />
          </label>
          <label>
            结束时间
            <PickerInput
              type="time"
              aria-label="结束时间"
              value={values.end_time}
              onChange={(event) =>
                setValues((current) => ({ ...current, end_time: event.target.value }))
              }
            />
          </label>
        </div>
      )}
    </div>
  );
}
