import { Toast } from "../../shared/Toast";
import { Select } from "../../shared/Select";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import type { Todo, TodoPage } from "../todos/types";
import type { HouseholdDetail } from "./types";

type Assignment = {
  todo_id: string;
  assignee_id: string;
  status: string;
  note: string;
  title: string;
};

export function FamilyAssignments({ household }: { household: HouseholdDetail }) {
  const { call, user } = useSession();
  const [todos, setTodos] = useState<Todo[]>([]);
  const [items, setItems] = useState<Assignment[]>([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [page, assignments] = await Promise.all([
        call<TodoPage>("/todos?status=ongoing&limit=50"),
        call<Assignment[]>("/collaboration/assignments"),
      ]);
      setTodos(page.items);
      setItems(assignments);
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, [call]);
  useEffect(() => void load(), [load]);

  async function assign(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await call(`/collaboration/todos/${data.get("todo")}/assign`, {
        method: "POST",
        body: JSON.stringify({ household_id: household.id, assignee_id: data.get("member") }),
      });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }

  async function feedback(id: string, status: "completed" | "rejected") {
    const note = status === "rejected" ? window.prompt("请填写拒绝原因") : "";
    if (status === "rejected" && note === null) return;
    try {
      await call(`/collaboration/todos/${id}/feedback`, {
        method: "POST",
        body: JSON.stringify({ status, note }),
      });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }

  const members = household.members.filter((member) => member.account_id);
  return (
    <section className="feature-card">
      <h3>家庭任务协作</h3>
      {error && <Toast message={error} tone="error" />}
      <form className="family-action-form" onSubmit={assign}>
        <Select name="todo" required aria-label="选择待办">
          <option value="">选择待办</option>
          {todos.map((todo) => (
            <option key={todo.id} value={todo.id}>
              {todo.title}
            </option>
          ))}
        </Select>
        <Select name="member" required aria-label="选择成员">
          <option value="">指派给</option>
          {members.map((member) => (
            <option key={member.id} value={member.account_id!}>
              {member.display_name}
            </option>
          ))}
        </Select>
        <button className="primary">指派</button>
      </form>
      <ul className="plain-list">
        {items.map((item) => (
          <li key={item.todo_id}>
            <span>
              {item.title} · {item.status}
              {item.note ? ` · ${item.note}` : ""}
            </span>
            {item.assignee_id === user?.id && item.status === "assigned" && (
              <span className="row">
                <button onClick={() => void feedback(item.todo_id, "completed")}>完成</button>
                <button onClick={() => void feedback(item.todo_id, "rejected")}>拒绝</button>
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
