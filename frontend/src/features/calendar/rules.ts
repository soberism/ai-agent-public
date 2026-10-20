import { codepoints } from "../../shared/text";
import { addDays } from "../todos/rules";
import type { EventValues } from "./types";

export function validateEvent(values: EventValues) {
  const errors: Record<string, string> = {};
  if (!values.title.trim()) errors.title = "请输入日程标题";
  else if (codepoints(values.title.trim()) > 15) errors.title = "标题最多 15 个字符";
  if (codepoints(values.description) > 2000) errors.description = "描述最多 2000 个字符";
  if (codepoints(values.location) > 200) errors.location = "地点最多 200 个字符";
  if (!values.start_date || !values.start_time) errors.start = "请选择开始日期和时间";
  if (!values.end_date || !values.end_time) errors.end = "请选择结束日期和时间";
  if (
    !errors.start &&
    !errors.end &&
    `${values.end_date}T${values.end_time}` <= `${values.start_date}T${values.start_time}`
  )
    errors.end = "结束时间必须晚于开始时间";
  if (values.recurrence !== "none" && !values.recurrence_until)
    errors.recurrence_until = "请选择重复结束日期";
  else if (
    values.recurrence_until &&
    (values.recurrence_until < values.start_date ||
      values.recurrence_until > addDays(values.start_date, 365))
  )
    errors.recurrence_until = "重复结束日期需在开始后的 366 天内";
  return errors;
}
