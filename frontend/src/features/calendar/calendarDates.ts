import { addDays } from "../todos/rules";

export function localDate(value: Date) {
  const year = value.getFullYear();
  return `${year}-${String(value.getMonth() + 1).padStart(2, "0")}-${String(value.getDate()).padStart(2, "0")}`;
}

export function dateWindow(date: string, range: "day" | "week" | "month"): [string, string] {
  if (range === "day") return [date, date];
  if (range === "week") {
    const offset = (new Date(`${date}T12:00:00Z`).getUTCDay() + 6) % 7;
    const start = addDays(date, -offset);
    return [start, addDays(start, 6)];
  }
  const start = `${date.slice(0, 7)}-01`;
  const next = new Date(`${start}T12:00:00Z`);
  next.setUTCMonth(next.getUTCMonth() + 1);
  return [start, addDays(next.toISOString().slice(0, 10), -1)];
}
