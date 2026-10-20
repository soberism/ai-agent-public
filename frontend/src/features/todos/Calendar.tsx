import { lunarTileContent } from "../../shared/LunarDate";
import MonthCalendar from "react-calendar";
import "react-calendar/dist/Calendar.css";
import { Modal } from "../../shared/Modal";
import { todayInZone, validateTodo } from "./rules";
import { emptyValues } from "./types";
export function Calendar({
  value,
  select,
  close,
}: {
  value: string;
  select: (value: string) => void;
  close: () => void;
}) {
  const invalid = validateTodo({ ...emptyValues, title: "日期", due_date: value }).due_date;
  const initial = !invalid && value ? value : todayInZone(new Date());
  return (
    <Modal title="选择截止日期" close={close}>
      <div className="month-calendar">
        <MonthCalendar
          locale="zh-CN"
          calendarType="iso8601"
          tileContent={lunarTileContent}
          value={new Date(initial + "T12:00:00")}
          minDate={new Date("0002-01-01T00:00:00")}
          maxDate={new Date("9999-12-30T23:59:59")}
          onChange={(date) => {
            if (!(date instanceof Date)) return;
            select(
              String(date.getFullYear()).padStart(4, "0") +
                "-" +
                String(date.getMonth() + 1).padStart(2, "0") +
                "-" +
                String(date.getDate()).padStart(2, "0"),
            );
            close();
          }}
        />
      </div>
    </Modal>
  );
}
