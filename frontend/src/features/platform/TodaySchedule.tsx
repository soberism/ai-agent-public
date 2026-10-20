import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { todayInZone } from "../todos/rules";
import type { CalendarEvent } from "../calendar/types";

export function TodaySchedule({
  onUpcomingChange,
}: {
  onUpcomingChange: (count: number | null) => void;
}) {
  const { call } = useSession();
  const today = todayInZone(new Date());
  const [events, setEvents] = useState<CalendarEvent[] | null>(null);
  const [error, setError] = useState("");
  const [now, setNow] = useState(Date.now);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 30000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    onUpcomingChange(
      events === null || error
        ? null
        : events.filter((event) => {
            const start = Date.parse(event.starts_at);
            return start > now && start <= now + 3600000;
          }).length,
    );
  }, [events, error, now, onUpcomingChange]);
  const load = useCallback(async () => {
    setError("");
    try {
      const result = await call<{ items: CalendarEvent[] }>(
        `/calendar/events?date_from=${today}&date_to=${today}`,
      );
      setEvents(
        result.items
          .filter((event) => event.status === "scheduled")
          .sort((a, b) => a.starts_at.localeCompare(b.starts_at)),
      );
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [call, today]);
  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="home-card home-summary" aria-labelledby="schedule-title">
      <div className="section-heading">
        <h2 id="schedule-title">
          今天的日程
          {events !== null && !error && <span className="summary-total">{events.length} 项</span>}
        </h2>
        <Link to={`/calendar?date=${today}`}>查看全部</Link>
      </div>
      {error ? (
        <div>
          <Toast message={`日程加载失败：${error}`} tone="error" />
          <button className="text-button" onClick={() => void load()}>
            重新加载
          </button>
        </div>
      ) : events === null ? (
        <p className="muted" role="status">
          日程加载中…
        </p>
      ) : events.length === 0 ? (
        <p className="muted">今天暂无日程</p>
      ) : (
        <>
          <ul className="summary-list">
            {events.map((event) => (
              <li key={event.id}>
                <Link to={`/calendar/${event.id}/edit`}>
                  <strong>{event.title}</strong>
                  <span>
                    {event.start_date === today ? "" : `${event.start_date} `}
                    {event.start_time}–{event.end_date === today ? "" : `${event.end_date} `}
                    {event.end_time}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
