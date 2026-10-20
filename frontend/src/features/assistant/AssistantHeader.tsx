import { Link } from "react-router-dom";

export function AssistantHeader({
  busy,
  startFresh,
  close,
}: {
  busy: boolean;
  startFresh: () => Promise<void>;
  close: () => void;
}) {
  return (
    <header className="page-header assistant-header">
      <h1>AI 对话</h1>
      <nav className="assistant-actions" aria-label="对话操作">
        <button
          type="button"
          className="assistant-action-button"
          onClick={() => void startFresh()}
          disabled={busy}
          aria-label="开始新对话"
          title="开始新对话"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M12 5v14M5 12h14" />
          </svg>
        </button>
        <Link
          className="assistant-action-button"
          to="/assistant/preferences"
          aria-label="打开偏好设置"
          title="偏好"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="M4 7h10M18 7h2M4 17h2M10 17h10M14 5v4M6 15v4" />
          </svg>
        </Link>
        <button
          type="button"
          className="assistant-action-button"
          onClick={close}
          aria-label="关闭 AI 对话"
          title="关闭 AI 对话"
        >
          <svg aria-hidden="true" viewBox="0 0 24 24">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </nav>
    </header>
  );
}
