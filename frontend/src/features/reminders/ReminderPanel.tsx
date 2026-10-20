import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { uncheckedFirst } from "../../shared/uncheckedFirst";
import { Toast } from "../../shared/Toast";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { PickerInput } from "../../shared/PickerInput";
import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";

type Reminder = {
  id: string;
  todo_id: string | null;
  event_id: string | null;
  remind_at: string;
  timezone: string;
  status: "scheduled" | "disabled";
  delivery: "app_only";
};

export function ReminderPanel({
  subject,
  id,
  defaultDate = "",
}: {
  subject: "todo" | "event";
  id: string;
  defaultDate?: string;
}) {
  const { call } = useSession();
  const sharing = useSharingEditor(subject, id);
  const [reminders, setReminders] = useState<Reminder[]>([]);
  const [date, setDate] = useState(defaultDate);
  const [time, setTime] = useState("09:00");
  const [error, setError] = useState("");
  const load = useCallback(async () => {
    try {
      const all = await call<Reminder[]>("/planning/reminders");
      setReminders(all.filter((item) => item[`${subject}_id`] === id));
    } catch (reason) {
      setError(messageOf(reason));
    }
  }, [call, id, subject]);
  useEffect(() => void load(), [load]);
  async function create(event: FormEvent) {
    event.preventDefault();
    if (!date || !time) return;
    setError("");
    try {
      await sharing.save(async () => {
        await call("/planning/reminders", {
          method: "POST",
          body: JSON.stringify({ [`${subject}_id`]: id, remind_date: date, remind_time: time }),
        });
        return { id };
      });
      await load();
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function remove(reminderId: string) {
    try {
      await call(`/planning/reminders/${reminderId}`, { method: "DELETE" });
      setReminders((current) => current.filter((item) => item.id !== reminderId));
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function toggle(item: Reminder) {
    const status = item.status === "scheduled" ? "disabled" : "scheduled";
    setReminders((current) =>
      current.map((value) => (value.id === item.id ? { ...value, status } : value)),
    );
    try {
      const next = await call<Reminder>(`/planning/reminders/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({ status }),
      });
      setReminders((current) => current.map((value) => (value.id === next.id ? next : value)));
    } catch (reason) {
      setReminders((current) => current.map((value) => (value.id === item.id ? item : value)));
      setError(messageOf(reason));
    }
  }
  return (
    <section className="reminder-panel" aria-labelledby={`reminder-${subject}-${id}`}>
      <h2 id={`reminder-${subject}-${id}`}>应用内提醒</h2>
      <p className="muted small">
        提醒只保存在本应用，不代表系统通知已经送达。可见范围沿用所属待办或日程。
      </p>
      {reminders.length > 0 && (
        <ul>
          {uncheckedFirst(reminders, (item) => item.status === "scheduled").map((item) => (
            <li key={item.id}>
              <time>
                {new Date(item.remind_at).toLocaleString("zh-CN", { timeZone: item.timezone })}
              </time>
              <label>
                <input
                  autoComplete="off"
                  type="checkbox"
                  checked={item.status === "scheduled"}
                  onChange={() => void toggle(item)}
                />
                开启提醒
              </label>
              <VisibilityControl kind="reminder" id={item.id} />
              <ConfirmButton
                className="text-button"
                title="删除提醒"
                message="确认删除这条提醒吗？删除后无法恢复。"
                onConfirm={() => remove(item.id)}
              >
                删除
              </ConfirmButton>
            </li>
          ))}
        </ul>
      )}
      <form className="reminder-form" onSubmit={create}>
        <label>
          提醒日期
          <PickerInput
            autoComplete="off"
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
          />
        </label>
        <label>
          提醒时间
          <PickerInput
            autoComplete="off"
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
          />
        </label>
        {sharing.canEdit && (
          <p className="muted small wide-field">
            修改这里的可见范围，也会改变所属待办或日程的可见范围。
          </p>
        )}
        <SharingEditor sharing={sharing} />
        <button disabled={!date || !time}>保存提醒</button>
      </form>
      {error && <Toast message={error} tone="error" />}
    </section>
  );
}
