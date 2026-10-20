import { Link } from "react-router-dom";
import { dateLabel, todayInZone } from "../todos/rules";
import type { Todo } from "../todos/types";

export function TodoSummary({ items, serverTime }: { items: Todo[]; serverTime: string }) {
  if (!items.length) return <p className="muted">暂无事项</p>;
  return (
    <ul className="summary-list">
      {items.map((todo) => (
        <li key={todo.id}>
          <Link to={`/todos/${todo.id}`}>
            <strong>{todo.title}</strong>
            <span>{dateLabel(todo, false, todayInZone(new Date(serverTime)))}</span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
