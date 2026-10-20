import { Link } from "react-router-dom";
import { dateLabel, todayInZone } from "../todos/rules";
import type { PlatformHome } from "./types";

export function RecentUpdates({ home }: { home: PlatformHome }) {
  const today = todayInZone(new Date(home.server_time));
  const items = [
    ...home.recent.map((todo) => ({
      key: `todo:${todo.id}`,
      title: todo.title,
      type: "待办",
      to: `/todos/${todo.id}`,
      updatedAt: todo.updated_at,
      time: dateLabel(todo, false, today),
    })),
    ...(home.recent_events ?? []).map((event) => ({
      key: `event:${event.id}`,
      title: event.title,
      type: "日程",
      to: `/calendar/${event.id}/edit`,
      updatedAt: event.updated_at,
      time: dateLabel({ due_date: event.start_date, due_time: event.start_time }, false, today),
    })),
  ]
    .sort((a, b) => Date.parse(b.updatedAt) - Date.parse(a.updatedAt) || a.key.localeCompare(b.key))
    .slice(0, 5);

  if (!items.length) return <p className="muted">暂无事项</p>;
  return (
    <ul className="summary-list">
      {items.map((item) => (
        <li key={item.key}>
          <Link to={item.to}>
            <strong>{item.title}</strong>
            <span>
              {item.type} · {item.time}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
