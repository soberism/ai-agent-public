import Input from "@rc-component/input";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { PickerInput } from "../../shared/PickerInput";
import { Select } from "../../shared/Select";
export type EmailSettings = {
  notifications_enabled: boolean;
  recipient_emails: string[];
  reminder_enabled: boolean;
  reminder_minutes: number | "";
  weekly_enabled: boolean;
  weekly_day: number;
  weekly_time: string;
  quiet_start: string;
  quiet_end: string;
};

export function EmailScheduleForm({
  value,
  change,
  save,
  dispatch,
  dispatching,
}: {
  value: EmailSettings;
  change: (value: EmailSettings) => void;
  save: (event: React.FormEvent<HTMLFormElement>) => void;
  dispatch: () => void;
  dispatching: boolean;
}) {
  const set = (key: keyof EmailSettings, next: string | boolean | number) =>
    change({ ...value, [key]: next });
  return (
    <form className="feature-card stack email-schedule-form" onSubmit={save}>
      <h2>邮件提醒与摘要</h2>
      <section className="email-setting-section">
        <label className="check-row">
          <input
            autoComplete="off"
            type="checkbox"
            checked={value.notifications_enabled}
            onChange={(event) => set("notifications_enabled", event.target.checked)}
          />
          邮件通知
        </label>
        <fieldset className="recipient-fields">
          <legend>收件邮箱</legend>
          {value.recipient_emails.map((email, index) => (
            <div className="recipient-row" key={index}>
              <Input
                autoComplete="off"
                type="email"
                readOnly={index === 0}
                required
                aria-label={`收件邮箱 ${index + 1}`}
                value={email}
                onChange={(event) =>
                  change({
                    ...value,
                    recipient_emails: value.recipient_emails.map((item, i) =>
                      i === index ? event.target.value : item,
                    ),
                  })
                }
              />
              {index > 0 && (
                <ConfirmButton
                  className="recipient-delete"
                  title="删除收件邮箱"
                  ariaLabel={`删除收件邮箱 ${index + 1}`}
                  message="确认删除这个收件邮箱吗？保存设置后生效。"
                  onConfirm={() =>
                    change({
                      ...value,
                      recipient_emails: value.recipient_emails.filter((_, i) => i !== index),
                    })
                  }
                >
                  删除
                </ConfirmButton>
              )}
            </div>
          ))}
          <button
            type="button"
            disabled={value.recipient_emails.length >= 3}
            onClick={() => change({ ...value, recipient_emails: [...value.recipient_emails, ""] })}
          >
            ＋ 添加
          </button>
        </fieldset>
      </section>
      <section className="email-setting-section">
        <label className="check-row">
          <input
            autoComplete="off"
            type="checkbox"
            checked={value.reminder_enabled}
            onChange={(event) => set("reminder_enabled", event.target.checked)}
          />
          事项提醒
        </label>
        <label>
          提前多少分钟提醒
          <input
            autoComplete="off"
            type="number"
            min={0}
            max={10080}
            step={1}
            required
            value={value.reminder_minutes}
            onChange={(event) =>
              set("reminder_minutes", event.target.value === "" ? "" : Number(event.target.value))
            }
          />
        </label>
      </section>
      <section className="email-setting-section">
        <label className="check-row">
          <input
            autoComplete="off"
            type="checkbox"
            checked={value.weekly_enabled}
            onChange={(event) => set("weekly_enabled", event.target.checked)}
          />
          每周摘要
        </label>
        <label>
          每周发送时间
          <PickerInput
            autoComplete="off"
            type="time"
            value={value.weekly_time}
            onChange={(event) => set("weekly_time", event.target.value)}
          />
        </label>
        <label>
          每周发送日期
          <Select
            value={value.weekly_day}
            onChange={(event) => set("weekly_day", Number(event.target.value))}
          >
            {["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((day, index) => (
              <option key={day} value={index}>
                {day}
              </option>
            ))}
          </Select>
        </label>
      </section>
      <section className="email-setting-section">
        <h3>免打扰时段</h3>
        <div className="event-time-grid">
          <label>
            免打扰开始
            <PickerInput
              autoComplete="off"
              type="time"
              value={value.quiet_start}
              onChange={(event) => set("quiet_start", event.target.value)}
            />
          </label>
          <label>
            免打扰结束
            <PickerInput
              autoComplete="off"
              type="time"
              value={value.quiet_end}
              onChange={(event) => set("quiet_end", event.target.value)}
            />
          </label>
        </div>
      </section>
      <button className="primary">保存设置</button>
      <button
        type="button"
        onClick={dispatch}
        disabled={dispatching || !value.notifications_enabled || !value.weekly_enabled}
      >
        {dispatching ? "发送中…" : "立即发送每周摘要"}
      </button>
    </form>
  );
}
