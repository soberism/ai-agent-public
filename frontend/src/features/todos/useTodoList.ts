import { useCallback, useContext, useEffect, useRef, useState } from "react";
import { useSession } from "../../app/session";
import { ApiError } from "../../shared/api";
import { Context } from "./context";
import type { DueFilter, Todo, TodoPage, TodoStatus } from "./types";
import { useToggle } from "./useToggle";

const pageCache = new Map<string, TodoPage>();
const cacheKey = (accountId: string, status: TodoStatus, due: DueFilter) =>
  `${accountId}:${status}:${due}`;

export function useTodoList() {
  const session = useSession();
  const { call } = session;
  const accountId = session.user!.id;
  const { list, setList, notify } = useContext(Context);
  const initialScroll = useRef(list.scroll);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [filterOpen, setFilterOpen] = useState(false);
  const [deleteBusy, setDeleteBusy] = useState<string | null>(null);
  const sequence = useRef(0);
  const { toggle, busy, error: toggleError } = useToggle();
  const fetchPage = useCallback(
    async (cursor?: string) => {
      const token = ++sequence.current;
      const key = cacheKey(accountId, list.status, list.due);
      setLoading(true);
      setError("");
      try {
        const query = new URLSearchParams({
          status: list.status,
          due: list.due,
        });
        if (cursor) query.set("cursor", cursor);
        const result = await call<TodoPage>(`/todos?${query}`);
        if (token !== sequence.current) return;
        setList((previous) => {
          const page =
            cursor && previous.page
              ? {
                  ...result,
                  items: [
                    ...previous.page.items,
                    ...result.items.filter(
                      (todo) => !previous.page!.items.some((old) => old.id === todo.id),
                    ),
                  ],
                }
              : result;
          pageCache.set(key, page);
          return { ...previous, page };
        });
      } catch (failure) {
        if (
          token === sequence.current &&
          !(failure instanceof ApiError && (failure.status === -1 || failure.status === 401))
        )
          setError("待办加载失败，请重试");
      } finally {
        if (token === sequence.current) setLoading(false);
      }
    },
    [accountId, list.status, list.due, call, setList],
  );
  useEffect(() => {
    const requests = sequence;
    void fetchPage();
    return () => {
      requests.current++;
    };
  }, [fetchPage]);
  useEffect(() => {
    window.scrollTo(0, initialScroll.current);
    const save = () => setList((previous) => ({ ...previous, scroll: window.scrollY }));
    window.addEventListener("scroll", save);
    return () => window.removeEventListener("scroll", save);
  }, [setList]);
  useEffect(() => {
    const refresh = () => void fetchPage();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refresh();
    }, 60000);
    window.addEventListener("focus", refresh);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", refresh);
    };
  }, [fetchPage]);
  function change(status: TodoStatus, due = list.due) {
    sequence.current++;
    const nextDue = status === "completed" && due === "overdue" ? "all" : due;
    setList((previous) => ({
      ...previous,
      status,
      due: nextDue,
      page: pageCache.get(cacheKey(accountId, status, nextDue)) ?? null,
      scroll: 0,
    }));
    setError("");
  }
  async function deleteTodo(todo: Todo) {
    if (deleteBusy) return false;
    setDeleteBusy(todo.id);
    let deleted = false;
    try {
      await call<void>(`/todos/${todo.id}`, { method: "DELETE" });
      deleted = true;
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === 0 || failure.status >= 500)) {
        try {
          await call<Todo>(`/todos/${todo.id}`);
        } catch (check) {
          deleted = check instanceof ApiError && check.status === 404;
        }
      }
      if (!deleted && !(failure instanceof ApiError && failure.status === 401))
        notify("删除失败，请重试", "error");
    } finally {
      setDeleteBusy(null);
    }
    if (!deleted) return false;
    setList((previous) =>
      previous.page
        ? {
            ...previous,
            page: {
              ...previous.page,
              items: previous.page.items.filter((item) => item.id !== todo.id),
            },
          }
        : previous,
    );
    notify("待办已删除");
    return true;
  }
  return {
    session,
    list,
    loading,
    error,
    filterOpen,
    setFilterOpen,
    toggle,
    busy,
    toggleError,
    deleteTodo,
    deleteBusy,
    fetchPage,
    change,
  };
}
