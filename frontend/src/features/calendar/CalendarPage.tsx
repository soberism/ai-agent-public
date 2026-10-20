import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import MonthCalendar from "react-calendar";
import type { Value } from "react-calendar/dist/shared/types.js";
import "react-calendar/dist/Calendar.css";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { addDays, todayInZone } from "../todos/rules";
import type { CalendarEvent } from "./types";
import { CalendarEvents } from "./CalendarEvents";
import { lunarTileContent } from "../../shared/LunarDate";
import { dateWindow, localDate } from "./calendarDates";

const calendarCache = new Map<string, CalendarEvent[]>();

function calendarCacheKey(userId: string, from: string, to: string) {
  return `${userId}:${from}:${to}`;
}

export function CalendarPage() {
  const session = useSession();
  const { call } = session;
  const [search] = useSearchParams();
  const initialDate = search.get("date") ?? todayInZone(new Date());
  const [initialFrom, initialTo] = dateWindow(initialDate, "month");
  const [date, setDate] = useState(initialDate);
  const [events, setEvents] = useState<CalendarEvent[] | null>(
    () => calendarCache.get(calendarCacheKey(session.user!.id, initialFrom, initialTo)) ?? null,
  );
  const [range, setRange] = useState<"day" | "week" | "all">("day");
  const [calendarOpen, setCalendarOpen] = useState(true);
  const [error, setError] = useState("");
  const [dateFrom, dateTo] = dateWindow(date, range === "all" ? "month" : range);
  const [monthFrom, monthTo] = dateWindow(date, "month");
  const queryFrom = dateFrom < monthFrom ? dateFrom : monthFrom;
  const queryTo = dateTo > monthTo ? dateTo : monthTo;
  const load = useCallback(async () => {
    const key = calendarCacheKey(session.user!.id, queryFrom, queryTo);
    const cached = calendarCache.get(key);
    setError("");
    setEvents(cached ?? null);
    try {
      const result = await call<{ items: CalendarEvent[] }>(
        `/calendar/events?date_from=${queryFrom}&date_to=${queryTo}`,
      );
      calendarCache.set(key, result.items);
      setEvents(result.items);
    } catch (reason) {
      setError(messageOf(reason));
    }
  }, [call, queryFrom, queryTo, session.user]);
  useEffect(() => void load(), [load]);
  const onDeleted = (id: string) => {
    setEvents((current) => current?.filter((event) => event.id !== id) ?? null);
    for (const [key, items] of calendarCache) {
      if (key.startsWith(`${session.user!.id}:`))
        calendarCache.set(
          key,
          items.filter((event) => event.id !== id),
        );
    }
  };
  const visibleEvents =
    events?.filter((event) => event.start_date <= dateTo && event.end_date >= dateFrom) ?? [];
  const selected = new Date(`${date}T12:00:00`);
  const selectDate = (value: Value) => {
    if (!(value instanceof Date)) return;
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    setDate(`${year}-${month}-${day}`);
    setRange("day");
  };
  return (
    <main className="page calendar-page">
      <header className="platform-header">
        <h1>日程</h1>
        <button
          type="button"
          className="text-button calendar-collapse-toggle"
          aria-expanded={calendarOpen}
          aria-controls="calendar-month-grid"
          onClick={() => setCalendarOpen((open) => !open)}
        >
          {calendarOpen ? "收起日历" : "展开日历"}
          <svg width="14" height="14" viewBox="0 0 24 24" aria-hidden="true">
            <path d={calendarOpen ? "m6 15 6-6 6 6" : "m6 9 6 6 6-6"} />
          </svg>
        </button>
      </header>
      <section aria-label="选择日期" className="month-calendar" hidden={!calendarOpen}>
        <div id="calendar-month-grid" hidden={!calendarOpen}>
          <MonthCalendar
            value={selected}
            onChange={selectDate}
            onActiveStartDateChange={({ activeStartDate, action }) => {
              if (range === "all" && activeStartDate && action !== "onChange")
                setDate(localDate(activeStartDate));
            }}
            locale="zh-CN"
            calendarType="iso8601"
            next2Label={null}
            prev2Label={null}
            minDetail="month"
            tileClassName={({ date: tileDate }) =>
              events?.some((event) => event.start_date === localDate(tileDate))
                ? "calendar-has-events"
                : undefined
            }
            tileContent={lunarTileContent}
          />
        </div>
      </section>
      <div className="tabs" role="group" aria-label="日历视图">
        {(["day", "week", "all"] as const).map((value) => (
          <button
            key={value}
            className={range === value ? "active" : ""}
            aria-pressed={range === value}
            onClick={() => setRange(value)}
          >
            {{ day: "日", week: "周", all: "全部" }[value]}
          </button>
        ))}
      </div>
      <h2 className="selected-date">
        {range === "all"
          ? `${date.slice(0, 7)} 全部日程`
          : `${dateFrom === dateTo ? dateFrom : `${dateFrom} 至 ${dateTo}`} 的日程`}
      </h2>
      {error && events !== null && (
        <Toast message={[error, "，当前显示上次数据"].join("")} tone="error" />
      )}
      {error && events === null ? (
        <div className="state compact">
          <Toast message={error} tone="error" />
          <button onClick={() => void load()}>重新加载</button>
        </div>
      ) : events === null ? (
        <p role="status" className="muted">
          正在加载日程…
        </p>
      ) : visibleEvents.length === 0 ? (
        <div className="state empty">
          <h2>当前范围还没有日程</h2>
          <p className="muted">安排一个明确的时间段，给重要的事留出位置。</p>
          <Link className="button" to={`/calendar/new?date=${date}`}>
            新建日程
          </Link>
        </div>
      ) : range === "week" ? (
        <div className="week-calendar" aria-label="周日历">
          {Array.from({ length: 7 }, (_, index) => addDays(dateFrom, index)).map((day, index) => {
            const dayEvents = visibleEvents.filter(
              (event) => (event.start_date < dateFrom ? dateFrom : event.start_date) === day,
            );
            return (
              <section
                key={day}
                className={dayEvents.length ? undefined : "week-day-empty"}
                aria-label={`${day}的日程`}
              >
                <h3>
                  {day.slice(5)} · 星期{"一二三四五六日"[index]}
                </h3>
                {dayEvents.length ? (
                  <CalendarEvents events={dayEvents} onDeleted={onDeleted} />
                ) : (
                  <p className="muted">暂无日程</p>
                )}
              </section>
            );
          })}
        </div>
      ) : (
        <CalendarEvents events={visibleEvents} onDeleted={onDeleted} />
      )}
      <div className="bottom-action">
        <Link className="button primary" to={`/calendar/new?date=${date}`}>
          ＋ 新建日程
        </Link>
      </div>
    </main>
  );
}
