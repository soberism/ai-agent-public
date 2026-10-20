export type TodoStatus = "ongoing" | "completed";
export type DueFilter = "all" | "overdue" | "today" | "tomorrow" | "next7" | "none";
export type TodoValues = {
  title: string;
  description: string;
  due_date: string;
  due_time: string;
};
export type TodoPayload = {
  title: string;
  description: string | null;
  due_date: string | null;
  due_time: string | null;
};
export type Todo = TodoPayload & {
  id: string;
  timezone: string;
  due_at: string | null;
  status: TodoStatus;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
  is_overdue: boolean;
  source: "app";
  assignee_id: string;
};
export type TodoPage = {
  items: Todo[];
  next_cursor: string | null;
  server_time: string;
};
export const emptyValues: TodoValues = {
  title: "",
  description: "",
  due_date: "",
  due_time: "",
};
