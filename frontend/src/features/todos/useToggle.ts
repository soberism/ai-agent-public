import { useContext, useState } from "react";
import { useSession } from "../../app/session";
import { ApiError, messageOf } from "../../shared/api";
import { Context } from "./context";
import type { Todo } from "./types";
export function useToggle() {
  const session = useSession();
  const { setList, notify } = useContext(Context);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState("");
  async function toggle(todo: Todo): Promise<Todo | undefined> {
    if (busy) return;
    setBusy(todo.id);
    setError("");
    const target = todo.status === "ongoing" ? "completed" : "ongoing";
    try {
      let result: Todo;
      try {
        result = await session.call<Todo>(`/todos/${todo.id}`, {
          method: "PATCH",
          body: JSON.stringify({ status: target }),
        });
      } catch (failure) {
        if (!(failure instanceof ApiError) || (failure.status !== 0 && failure.status < 500))
          throw failure;
        result = await session.call<Todo>(`/todos/${todo.id}`);
        if (result.status !== target) throw new Error("操作尚未完成，请重试", { cause: failure });
      }
      setBusy(null);
      setList((previous) =>
        previous.page
          ? {
              ...previous,
              page: {
                ...previous.page,
                items: previous.page.items.map((item) => (item.id === result.id ? result : item)),
              },
            }
          : previous,
      );
      notify(target === "completed" ? "已标记完成" : "已恢复为未完成");
      await new Promise((resolve) => window.setTimeout(resolve, 350));
      setList((previous) =>
        previous.page && previous.status !== result.status
          ? {
              ...previous,
              page: {
                ...previous.page,
                items: previous.page.items.filter((item) => item.id !== result.id),
              },
            }
          : previous,
      );
      return result;
    } catch (failure) {
      if (!(failure instanceof ApiError && (failure.status === -1 || failure.status === 401)))
        setError(`操作失败，请重试。${messageOf(failure)}`);
    } finally {
      setBusy(null);
    }
  }
  return { toggle, busy, error };
}
