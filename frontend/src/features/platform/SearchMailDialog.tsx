import { Toast } from "../../shared/Toast";
import { useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Modal } from "../../shared/Modal";

type Mail = { subject: string; body: string; sender: string | null; created_at: string };

export function SearchMailDialog({
  id,
  kind,
  close,
}: {
  id: string;
  kind: string;
  close: () => void;
}) {
  const { call } = useSession();
  const [mail, setMail] = useState<Mail | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    call<Mail>(`/hub/search/${kind}/${id}`, { signal: controller.signal })
      .then((value) => {
        if (!controller.signal.aborted) setMail(value);
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(messageOf(failure));
      });
    return () => controller.abort();
  }, [call, id, kind, retry]);
  const title =
    kind === "assistant_message" ? "AI 对话记录" : kind === "daily_dump" ? "随手记录" : "邮件详情";
  return (
    <Modal title={title} close={close} className="email-detail-dialog">
      {error ? (
        <div>
          <Toast message={error} tone="error" />
          <button
            type="button"
            onClick={() => {
              setError("");
              setRetry(retry + 1);
            }}
          >
            重试
          </button>
        </div>
      ) : !mail ? (
        <p role="status">正在加载内容…</p>
      ) : (
        <div>
          <h3>{mail.subject}</h3>
          {mail.sender && <p>发件人：{mail.sender}</p>}
          <p>{new Date(mail.created_at).toLocaleString("zh-CN")}</p>
          <p style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>
            {mail.body || "没有可读取的正文"}
          </p>
        </div>
      )}
    </Modal>
  );
}
