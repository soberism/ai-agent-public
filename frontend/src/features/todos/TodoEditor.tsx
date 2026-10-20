import { Toast } from "../../shared/Toast";
import { useParams } from "react-router-dom";
import { EditorForm } from "./EditorForm";
import { useTodo } from "./useTodo";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
export function TodoEditor() {
  const { id } = useParams();
  const loaded = useTodo(id);
  if (id && loaded.error)
    return (
      <>
        <PageHeader title="待办详情" back="/todos" />
        <div className="state">
          <Toast message={loaded.error} tone="error" />
          <button onClick={loaded.retry}>重新加载</button>
        </div>
      </>
    );
  if (id && !loaded.todo) return <Loading />;
  return <EditorForm key={id || "new"} todo={loaded.todo} />;
}
