import { SharingEditor } from "../sharing/SharingEditor";
import { Toast } from "../../shared/Toast";
import { Calendar } from "./Calendar";
import { EditorDialogs } from "./EditorDialogs";
import { EditorFields } from "./EditorFields";
import type { Todo } from "./types";
import { useTodoEditor } from "./useTodoEditor";
import { BackButton } from "../../shared/BackButton";

export function EditorForm({ todo }: { todo: Todo | null }) {
  const form = useTodoEditor({ todo });
  const { values, pending, error, calendar, setCalendar, uncertain, update, save, checkEdit } =
    form;
  return (
    <>
      <header className="page-header">
        <BackButton fallback="/todos" />
        <h1>{todo ? "待办详情" : "新建待办"}</h1>
      </header>
      <form className="stack editor" noValidate onSubmit={save}>
        <EditorFields form={form} />
        <Toast
          key={form.feedbackRevision}
          message={error || Object.values(form.fields).find(Boolean) || ""}
          tone="error"
        />
        <SharingEditor sharing={form.sharing} disabled={pending} />
        <div className="bottom-action">
          {uncertain && todo ? (
            <button
              type="button"
              className="primary full"
              disabled={pending}
              onClick={() => void checkEdit()}
            >
              核对当前待办
            </button>
          ) : (
            <button className="primary full" disabled={pending}>
              {uncertain ? "核对并重试" : todo ? "保存修改" : "添加待办"}
            </button>
          )}
        </div>
      </form>
      {calendar && (
        <Calendar
          value={values.due_date}
          select={(value) => update("due_date", value)}
          close={() => setCalendar(false)}
        />
      )}
      <EditorDialogs form={form} />
    </>
  );
}
