import type { Todo } from "./types";

export function TodoStatusControl({
  todo,
  busy,
  toggle,
}: {
  todo: Todo;
  busy: boolean;
  toggle: (todo: Todo) => void;
}) {
  const action = todo.status === "completed" ? "恢复未完成" : "标记完成";
  return (
    <button
      className={`status-control ${todo.status === "completed" ? "checked" : ""} ${busy ? "loading" : ""}`}
      aria-label={`${action}：${todo.title}`}
      aria-pressed={todo.status === "completed"}
      disabled={busy}
      onClick={() => toggle(todo)}
    />
  );
}
