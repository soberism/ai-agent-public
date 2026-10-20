import { Modal } from "../../shared/Modal";
import type { Todo } from "./types";

export function TodoDeleteDialog({
  todo,
  busy,
  close,
  remove,
}: {
  todo: Todo;
  busy: boolean;
  close: () => void;
  remove: (todo: Todo) => Promise<unknown>;
}) {
  return (
    <Modal title="删除待办" close={close}>
      <p>确认删除“{todo.title}”吗？删除后无法恢复。</p>
      <div className="modal-actions">
        <button disabled={busy} onClick={close}>
          取消
        </button>
        <button
          className="danger"
          disabled={busy}
          onClick={async () => {
            await remove(todo);
            close();
          }}
        >
          确认删除
        </button>
      </div>
    </Modal>
  );
}
