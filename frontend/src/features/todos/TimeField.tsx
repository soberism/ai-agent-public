import { PickerInput } from "../../shared/PickerInput";

export function TimeField({
  value,
  disabled,
  error,
  hasDate,
  update,
}: {
  value: string;
  disabled: boolean;
  error?: string;
  hasDate: boolean;
  update: (value: string) => void;
}) {
  return (
    <div>
      <label htmlFor="due-time">截止时间</label>
      <div className="date-field">
        <PickerInput
          autoComplete="off"
          id="due-time"
          type="time"
          placeholder="选择时间"
          value={value}
          disabled={disabled || !hasDate}
          aria-describedby="time-help"
          aria-invalid={!!error}
          onChange={(event) => update(event.target.value)}
        />
        <button type="button" disabled={disabled || !value} onClick={() => update("")}>
          清空
        </button>
      </div>
      <span id="time-help" className="muted">
        {hasDate ? "按北京时间保存；留空则仅设置日期" : "先选择截止日期，再设置时间"}
      </span>
    </div>
  );
}
