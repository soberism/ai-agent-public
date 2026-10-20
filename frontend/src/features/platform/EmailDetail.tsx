import { Modal } from "../../shared/Modal";
import { RetryEmail } from "./RetryEmail";
import type { Delivery } from "./ConnectionsPage";

export function EmailDetail({
  item,
  close,
  refresh,
}: {
  item: Delivery;
  close: () => void;
  refresh: () => void;
}) {
  return (
    <Modal title="邮件详情" close={close} className="email-detail-dialog">
      <h3>{item.subject}</h3>
      <p className="muted">
        {{
          sent: "已发送",
          failed: "发送失败",
          pending: "待发送",
          sending: "发送中／结果待确认",
          unknown: "结果待确认",
        }[item.status] ?? item.status}
      </p>
      <p className="muted">创建时间：{new Date(item.created_at).toLocaleString("zh-CN")}</p>
      {item.sent_at && (
        <p className="muted">发送时间：{new Date(item.sent_at).toLocaleString("zh-CN")}</p>
      )}
      {item.error_message && <p className="muted">失败原因：{item.error_message}</p>}
      <p className="email-body">{item.body}</p>
      {item.status === "failed" && (
        <RetryEmail
          id={item.id}
          done={() => {
            close();
            refresh();
          }}
        />
      )}
    </Modal>
  );
}
