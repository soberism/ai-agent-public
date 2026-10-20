import { VisibilityControl } from "../sharing/VisibilityControl";
import { Link } from "react-router-dom";
import { dateLabel, todayInZone } from "./rules";
import { TodoStatusControl } from "./TodoStatusControl";
import type { Todo } from "./types";

export function TodoListItem({
  todo,
  busy,
  serverTime,
  toggle,
  remove,
}: {
  todo: Todo;
  busy: boolean;
  serverTime: string;
  toggle: (todo: Todo) => void;
  remove: () => void;
}) {
  return (
    <li className="todo-row">
      <TodoStatusControl todo={todo} busy={busy} toggle={toggle} />
      <Link className="todo-content" to={`/todos/${todo.id}/edit`}>
        <strong>{todo.title}</strong>
        {todo.description && <span className="todo-description">{todo.description}</span>}
        <span className="muted">
          {dateLabel(todo, true, todayInZone(new Date(serverTime)))}
          {todo.is_overdue && todo.status === "ongoing" && (
            <span className="overdue"> · 已逾期</span>
          )}
        </span>
        <span className="muted">{todo.status === "completed" ? "已完成" : "进行中"} · 应用内</span>
      </Link>
      <VisibilityControl kind="todo" id={todo.id} />
      <button
        className="todo-delete"
        type="button"
        aria-label={`删除待办“${todo.title}”`}
        onClick={remove}
      >
        删除
      </button>
    </li>
  );
}
