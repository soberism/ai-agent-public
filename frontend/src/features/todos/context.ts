import { createContext } from "react";
import type { DueFilter, TodoPage, TodoStatus } from "./types";
export type ListState = {
  status: TodoStatus;
  due: DueFilter;
  page: TodoPage | null;
  scroll: number;
};
export type TodoContext = {
  list: ListState;
  setList: React.Dispatch<React.SetStateAction<ListState>>;
  notice: string;
  noticeTone: "success" | "error";
  notify: (value: string, tone?: "success" | "error") => void;
};
export const Context = createContext<TodoContext>(null!);
