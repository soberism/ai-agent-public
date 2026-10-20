import { VisibilityControl } from "../sharing/VisibilityControl";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { useSession } from "../../app/session";
import { Link } from "react-router-dom";
import type { CalendarEvent } from "./types";

export function CalendarEvents({
  events,
  onDeleted,
}: {
  events: CalendarEvent[];
  onDeleted: (id: string) => void;
}) {
  const { call } = useSession();
  return (
    <ul className="event-list">
      {events.map((event) => (
        <li key={event.id}>
          <Link to={`/calendar/${event.id}/edit`}>
            <time>
              {event.start_time}–
              {event.end_date === event.start_date
                ? event.end_time
                : `${event.end_date} ${event.end_time}`}
            </time>
            <strong>{event.title}</strong>
            {event.status === "cancelled" && <span className="event-card-status">已取消</span>}
            {event.end_date !== event.start_date && (
              <span>
                日期：{event.start_date} 至 {event.end_date}
              </span>
            )}
            {event.location && <span>地点：{event.location}</span>}
            {event.description && (
              <span className="event-card-description">备注：{event.description}</span>
            )}
          </Link>
          <VisibilityControl kind="event" id={event.id} />
          <ConfirmButton
            className="text-button event-delete"
            ariaLabel={`删除日程：${event.title}`}
            title="删除日程"
            message={`确认删除“${event.title}”吗？删除后无法恢复。`}
            onConfirm={async () => {
              await call(`/calendar/events/${event.id}`, { method: "DELETE" });
              onDeleted(event.id);
            }}
          >
            删除
          </ConfirmButton>
        </li>
      ))}
    </ul>
  );
}
