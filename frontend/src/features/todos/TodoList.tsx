import { TodoLoadMore } from "./TodoLoadMore";
import { Toast } from "../../shared/Toast";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Modal } from "../../shared/Modal";
import { Loading } from "../../shared/Loading";
import { Notice } from "./Notice";
import { filterLabels } from "./rules";
import { TodoDeleteDialog } from "./TodoDeleteDialog";
import { TodoListItem } from "./TodoListItem";
import type { DueFilter, Todo } from "./types";
import { useTodoList } from "./useTodoList";
export function TodoList() {
  const {
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
  } = useTodoList();
  const [deleteTarget, setDeleteTarget] = useState<Todo | null>(null);
  return (
    <>
      <div className="todo-sticky-header">
        <header className="page-header todo-header">
          <h1>待办</h1>
          <div className="header-actions">
            <Link className="app-nav-link" to="/assistant">
              <svg aria-hidden="true" viewBox="0 0 24 24" width="18" height="18">
                <path d="M12 3l1.3 4.2L17.5 8.5l-4.2 1.3L12 14l-1.3-4.2-4.2-1.3 4.2-1.3L12 3Z" />
                <path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7.7-2.3Z" />
              </svg>
              AI 对话
            </Link>
          </div>
        </header>
        <Notice />
        <div className="tabs" role="group" aria-label="待办状态">
          <button
            aria-pressed={list.status === "ongoing"}
            className={list.status === "ongoing" ? "active" : ""}
            onClick={() => change("ongoing")}
          >
            进行中
          </button>
          <button
            aria-pressed={list.status === "completed"}
            className={list.status === "completed" ? "active" : ""}
            onClick={() => change("completed")}
          >
            已完成
          </button>
        </div>
        <div className="list-toolbar">
          <span className="filter-summary">{filterLabels[list.due]}</span>
          <button className="text-button" onClick={() => setFilterOpen(true)}>
            筛选
          </button>
        </div>
      </div>
      {toggleError && <Toast message={toggleError} tone="error" />}
      {error && list.page && (
        <Toast message={[error, "，当前显示上次数据"].join("")} tone="error" />
      )}
      {error && !list.page ? (
        <div className="state compact">
          <Toast message={error} tone="error" />
          <button onClick={() => void fetchPage()}>重新加载</button>
        </div>
      ) : !list.page ? (
        <Loading compact />
      ) : list.page.items.length === 0 ? (
        <div className="state empty">
          <div aria-hidden="true" className="empty-symbol">
            ✓
          </div>
          <h2>
            {list.due !== "all"
              ? "没有符合条件的待办"
              : list.status === "ongoing"
                ? "暂时没有待办"
                : "还没有已完成的待办"}
          </h2>
          <p className="muted">
            {list.due !== "all" ? "换个条件，看看其他安排。" : "把重要的小事记下来，慢慢完成。"}
          </p>
          {list.due !== "all" ? (
            <button onClick={() => change(list.status, "all")}>清除筛选</button>
          ) : (
            list.status === "ongoing" && (
              <Link className="button" to="/todos/new">
                添加第一条待办
              </Link>
            )
          )}
        </div>
      ) : (
        <>
          <ul className="todo-list">
            {list.page.items.map((todo) => (
              <TodoListItem
                key={todo.id}
                todo={todo}
                busy={busy === todo.id}
                serverTime={list.page!.server_time}
                toggle={(item) => void toggle(item)}
                remove={() => setDeleteTarget(todo)}
              />
            ))}
          </ul>
          {list.page.next_cursor && (
            <TodoLoadMore
              cursor={list.page.next_cursor}
              loading={loading}
              error={error}
              load={fetchPage}
            />
          )}
        </>
      )}
      <div className="bottom-action">
        <Link className="button primary" to="/todos/new">
          <span aria-hidden="true">＋ </span>新建待办
        </Link>
      </div>
      {filterOpen && (
        <Modal title="筛选待办" close={() => setFilterOpen(false)}>
          <p className="muted">截止日期</p>
          <div className="filter-options">
            {(Object.keys(filterLabels) as DueFilter[])
              .filter((due) => !(list.status === "completed" && due === "overdue"))
              .map((due) => (
                <button
                  key={due}
                  className={`chip ${list.due === due ? "selected" : ""}`}
                  aria-pressed={list.due === due}
                  onClick={() => {
                    change(list.status, due);
                    setFilterOpen(false);
                  }}
                >
                  {filterLabels[due]}
                </button>
              ))}
          </div>
          <div className="modal-actions">
            <button onClick={() => change(list.status, "all")}>重置</button>
          </div>
        </Modal>
      )}
      {deleteTarget && (
        <TodoDeleteDialog
          todo={deleteTarget}
          busy={deleteBusy === deleteTarget.id}
          close={() => setDeleteTarget(null)}
          remove={deleteTodo}
        />
      )}
    </>
  );
}
