import { expect, test } from "@playwright/test";
import { dateLabel, todayInZone } from "../src/features/todos/rules";

test("日期标签固定使用上海日期", () => {
  const today = todayInZone(new Date("2026-09-16T18:00:00Z"));
  expect(today).toBe("2026-09-17");
  expect(dateLabel({ due_date: "2026-09-16", due_time: "09:00" }, false, today)).toBe(
    "2026年9月16日 09:00",
  );
  expect(dateLabel({ due_date: "2026-09-17", due_time: "09:00" }, false, today)).toBe("今天 09:00");
});
