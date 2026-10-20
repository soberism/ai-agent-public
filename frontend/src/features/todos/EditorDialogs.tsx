import { Modal } from "../../shared/Modal";
import { useTodoEditor } from "./useTodoEditor";
export function EditorDialogs({ form }: { form: ReturnType<typeof useTodoEditor> }) {
  const { blocker, uncertain } = form;
  if (blocker.state !== "blocked") return null;
  return (
    <Modal title="放弃本次修改？" close={() => blocker.reset()}>
      <p>
        尚未保存的内容将被清除。
        {uncertain && "上一次请求可能已经保存，可先继续编辑并核对结果。"}
      </p>
      <div className="modal-actions">
        <button className="danger" onClick={() => blocker.proceed()}>
          放弃修改
        </button>
        <button className="primary" onClick={() => blocker.reset()}>
          继续编辑
        </button>
      </div>
    </Modal>
  );
}
