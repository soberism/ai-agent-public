import { useSharingEditor } from "../sharing/useSharingEditor";
import { useCallback, useContext, useRef, useState } from "react";
import { useBeforeUnload, useBlocker, useNavigate } from "react-router-dom";
import { useSession } from "../../app/session";
import { ApiError, messageOf } from "../../shared/api";
import { Context } from "./context";
import { matchesDue, todayInZone, validateTodo } from "./rules";
import type { Todo, TodoPayload, TodoValues } from "./types";
import { emptyValues } from "./types";

function createIdempotencyKey() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const value = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${value.slice(0, 8)}-${value.slice(8, 12)}-${value.slice(12, 16)}-${value.slice(16, 20)}-${value.slice(20)}`;
}

export function useTodoEditor({ todo }: { todo: Todo | null }) {
  const session = useSession();
  const sharing = useSharingEditor("todo", todo?.id);
  const { list, setList, notify } = useContext(Context);
  const navigate = useNavigate();
  const initial = useRef<TodoValues>(
    todo
      ? {
          title: todo.title,
          description: todo.description || "",
          due_date: todo.due_date || "",
          due_time: todo.due_time || "",
        }
      : { ...emptyValues },
  );
  const [values, setValues] = useState({ ...initial.current });
  const [pending, setPending] = useState(false);
  const [error, setError] = useState("");
  const [feedbackRevision, setFeedbackRevision] = useState(0);
  const [fields, setFields] = useState<Record<string, string>>({});
  const [calendar, setCalendar] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef<{ key: string; payload: TodoPayload } | undefined>(undefined);
  const bypass = useRef(false);
  const dirty =
    JSON.stringify(values) !== JSON.stringify(initial.current) ||
    sharing.changed ||
    sharing.recovering;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      !bypass.current &&
      session.state === "authenticated" &&
      (dirty || uncertain) &&
      currentLocation.pathname !== nextLocation.pathname,
  );
  useBeforeUnload(
    useCallback(
      (event) => {
        if ((dirty || uncertain) && !bypass.current) {
          event.preventDefault();
          event.returnValue = "";
        }
      },
      [dirty, uncertain],
    ),
  );
  function update(name: keyof TodoValues, value: string) {
    setValues((old) => ({
      ...old,
      [name]: value,
      ...(name === "due_date" && !value ? { due_time: "" } : {}),
    }));
    setFields({});
    setError("");
  }
  function updateCachedTodo(current: Todo) {
    setList((previous) =>
      previous.page
        ? {
            ...previous,
            page: {
              ...previous.page,
              items:
                current.status === previous.status &&
                matchesDue(current, previous.due, todayInZone(new Date()))
                  ? previous.page.items.map((item) => (item.id === current.id ? current : item))
                  : previous.page.items.filter((item) => item.id !== current.id),
            },
          }
        : previous,
    );
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    if (pending) return;
    setFeedbackRevision((value) => value + 1);
    const validation = validateTodo(values);
    setFields(validation);
    if (Object.keys(validation).length) return;
    const payload: TodoPayload = {
      title: values.title.trim(),
      description: values.description || null,
      due_date: values.due_date || null,
      due_time: values.due_time || null,
    };
    setPending(true);
    setError("");
    try {
      if (!todo && !attempt.current) attempt.current = { key: createIdempotencyKey(), payload };
      const result = await sharing.save(() =>
        session.call<Todo>(todo ? `/todos/${todo.id}` : "/todos", {
          method: todo ? "PATCH" : "POST",
          headers: !todo ? { "Idempotency-Key": attempt.current!.key } : undefined,
          body: JSON.stringify(todo ? payload : attempt.current!.payload),
        }),
      );
      bypass.current = true;
      setUncertain(false);
      if (!todo) {
        setList({ status: "ongoing", due: "all", page: null, scroll: 0 });
        notify("待办已添加");
        navigate("/todos");
      } else {
        updateCachedTodo(result);
        notify(
          result.status !== list.status || !matchesDue(result, list.due, todayInZone(new Date()))
            ? "已保存，该待办不符合当前筛选条件"
            : "修改已保存",
        );
        navigate("/todos");
      }
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === -1 || failure.status === 401)) return;
      if (
        failure instanceof ApiError &&
        (failure.status === 0 || failure.status >= 500 || failure.status === 409)
      ) {
        setUncertain(true);
        setError(
          todo
            ? "保存结果尚未确认，请核对当前待办后再继续。"
            : failure.status === 409
              ? "请求标识与内容冲突，请保留当前内容并核对，不要重复新建。"
              : "保存结果尚未确认。请保持原内容，使用同一请求核对并重试。",
        );
      } else {
        if (failure instanceof ApiError) setFields(failure.fields);
        attempt.current = undefined;
        setUncertain(false);
        setError(`保存失败，请重试。${messageOf(failure)}`);
      }
    } finally {
      setPending(false);
    }
  }
  async function checkEdit() {
    if (!todo || pending) return;
    setPending(true);
    try {
      const current = await session.call<Todo>(`/todos/${todo.id}`);
      const matches =
        current.title === values.title.trim() &&
        (current.description || "") === values.description &&
        (current.due_date || "") === values.due_date &&
        (current.due_time || "") === values.due_time;
      if (matches && !sharing.changed && !sharing.recovering) {
        bypass.current = true;
        updateCachedTodo(current);
        notify("修改已保存");
        navigate("/todos");
      } else {
        setUncertain(false);
        setError("已核对，当前保存内容与草稿不同。请确认后重新保存。");
      }
    } catch (failure) {
      setError(`暂时无法核对。${messageOf(failure)}`);
    } finally {
      setPending(false);
    }
  }
  const validation = validateTodo(values);
  const locked = pending || uncertain || sharing.recovering;
  return {
    sharing,
    session,
    navigate,
    initial,
    values,
    setValues,
    pending,
    error,
    feedbackRevision,
    fields,
    calendar,
    setCalendar,
    uncertain,
    setUncertain,
    attempt,
    blocker,
    update,
    save,
    checkEdit,
    validation,
    locked,
  };
}
