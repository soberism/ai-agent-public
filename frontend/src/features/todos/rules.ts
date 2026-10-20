import { codepoints } from "../../shared/text";
import type { DueFilter, Todo, TodoValues } from "./types";
export function todayInZone(now: Date): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Shanghai",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  return ["year", "month", "day"]
    .map((type) => parts.find((part) => part.type === type)!.value)
    .join("-");
}
export function addDays(date: string, days: number): string {
  const value = new Date(`${date}T12:00:00Z`);
  value.setUTCDate(value.getUTCDate() + days);
  return value.toISOString().slice(0, 10);
}
export function nextMonday(date: string): string {
  return addDays(date, 7 - ((new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7));
}
export function validateTodo(values: TodoValues): Record<string, string> {
  const errors: Record<string, string> = {};
  if (!values.title.trim()) errors.title = "请输入待办标题";
  else if (codepoints(values.title.trim()) > 15) errors.title = "标题最多 15 个字符";
  if (codepoints(values.description) > 2000) errors.description = "描述最多 2000 个字符";
  if (
    values.due_date &&
    (!/^\d{4}-\d{2}-\d{2}$/.test(values.due_date) ||
      values.due_date < "0002-01-01" ||
      values.due_date > "9999-12-30" ||
      Number.isNaN(Date.parse(`${values.due_date}T12:00:00Z`)) ||
      new Date(`${values.due_date}T12:00:00Z`).toISOString().slice(0, 10) !== values.due_date)
  )
    errors.due_date = "请选择有效的日期和时间";
  if (values.due_time && (!values.due_date || !/^([01]\d|2[0-3]):[0-5]\d$/.test(values.due_time)))
    errors.due_time = "请选择有效的日期和时间";
  return errors;
}
export function dateLabel(
  todo: Pick<Todo, "due_date" | "due_time">,
  full: boolean,
  today: string,
): string {
  if (!todo.due_date) return "不设截止日期";
  const [year, month, day] = todo.due_date.split("-");
  const label =
    !full && todo.due_date === today
      ? "今天"
      : !full && todo.due_date === addDays(today, 1)
        ? "明天"
        : `${year}年${Number(month)}月${Number(day)}日`;
  return label + (todo.due_time ? ` ${todo.due_time}` : "");
}
export function matchesDue(todo: Todo, due: DueFilter, today: string): boolean {
  if (due === "all") return true;
  if (due === "none") return !todo.due_date;
  if (due === "overdue") return todo.status === "ongoing" && todo.is_overdue;
  if (!todo.due_date) return false;
  if (due === "today") return todo.due_date === today;
  if (due === "tomorrow") return todo.due_date === addDays(today, 1);
  return todo.due_date >= today && todo.due_date <= addDays(today, 6);
}

export const filterLabels: Record<DueFilter, string> = {
  all: "全部",
  overdue: "已逾期",
  today: "今天",
  tomorrow: "明天",
  next7: "未来 7 天",
  none: "不设截止日期",
};
