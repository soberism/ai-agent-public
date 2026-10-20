import { useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { ApiError, messageOf } from "../../shared/api";
import type { Todo } from "./types";
export function useTodo(id: string | undefined) {
  const { call } = useSession();
  const [todo, setTodo] = useState<Todo | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    setTodo(null);
    setError("");
    if (!id) return;
    void call<Todo>(`/todos/${id}`)
      .then((value) => {
        if (active) setTodo(value);
      })
      .catch((failure) => {
        if (active && !(failure instanceof ApiError && failure.status === -1))
          setError(
            failure instanceof ApiError && failure.status === 404
              ? "该待办不存在或无法访问"
              : messageOf(failure),
          );
      });
    return () => {
      active = false;
    };
  }, [id, retry, call]);
  return { todo, setTodo, error, retry: () => setRetry((value) => value + 1) };
}
