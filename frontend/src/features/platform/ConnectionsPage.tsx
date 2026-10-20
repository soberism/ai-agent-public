import Input, { TextArea } from "@rc-component/input";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { EmailDetail } from "./EmailDetail";
import { PageHeader } from "../../shared/PageHeader";
import { EmailScheduleForm } from "./EmailScheduleForm";
import type { EmailSettings } from "./EmailScheduleForm";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";

type Caps = {
  smtp: boolean;
  third_party_calendar: false;
  notification_channels: string[];
};
export type Delivery = {
  id: string;
  subject: string;
  body: string;
  sent_at: string | null;
  status: string;
  error_message: string | null;
  created_at: string;
};
const deliveryStatus = (status: string) =>
  ({
    sent: "已发送",
    failed: "发送失败",
    pending: "待发送",
    sending: "发送中／结果待确认",
    unknown: "结果待确认",
  })[status] ?? status;

export function ConnectionsPage() {
  const { call } = useSession();
  const [caps, setCaps] = useState<Caps | null>(null);
  const [deliveries, setDeliveries] = useState<Delivery[]>([]);
  const [selected, setSelected] = useState<Delivery | null>(null);
  const [dispatching, setDispatching] = useState(false);
  const { setNotice, toastProps } = useToast();
  const [loaded, setLoaded] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [emailSettings, setEmailSettings] = useState<EmailSettings | null>(null);
  const load = useCallback(async () => {
    try {
      const [nextCaps, nextDeliveries] = await Promise.all([
        call<Caps>("/mail/capabilities"),
        call<Delivery[]>("/mail/notifications"),
      ]);
      setCaps(nextCaps);
      setDeliveries(nextDeliveries);
      try {
        setEmailSettings(await call<EmailSettings>("/workflows/email-settings"));
      } catch {
        setEmailSettings(null);
      }
    } catch (error) {
      setLoadError(messageOf(error));
    } finally {
      setLoaded(true);
    }
  }, [call]);
  useEffect(() => void load(), [load]);

  async function saveSettings(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!emailSettings) return;
    try {
      await call("/workflows/email-settings", {
        method: "PUT",
        body: JSON.stringify(emailSettings),
      });
      setNotice("邮件提醒设置已保存");
    } catch (error) {
      setNotice(messageOf(error), "error");
    }
  }

  async function dispatch() {
    if (dispatching) return;
    setDispatching(true);
    try {
      if (!emailSettings) return;
      await call("/workflows/email-settings", {
        method: "PUT",
        body: JSON.stringify(emailSettings),
      });
      const result = await call<{
        sent: number;
        failed: number;
        unknown: number;
        deferred: boolean;
      }>("/workflows/email-dispatch", {
        method: "POST",
        body: JSON.stringify({ manual: true, request_id: crypto.randomUUID() }),
      });
      setNotice(
        result.deferred
          ? "当前处于免打扰时段，请结束后再检查"
          : result.sent + result.failed + result.unknown === 0
            ? "暂无待发送邮件"
            : `发送成功 ${result.sent} 封，失败 ${result.failed} 封，结果待确认 ${result.unknown} 封`,
        result.failed > 0 ? "error" : "success",
      );
      await load();
    } catch (error) {
      setNotice(messageOf(error), "error");
    } finally {
      setDispatching(false);
    }
  }

  async function send(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    try {
      const result = await call<Delivery>("/mail/notifications", {
        method: "POST",
        body: JSON.stringify({ subject: data.get("subject"), body: data.get("body") }),
      });
      form.reset();
      setNotice(deliveryStatus(result.status), result.status === "failed" ? "error" : "success");
      await load();
    } catch (error) {
      setNotice(messageOf(error), "error");
      await load();
    }
  }

  return (
    <main className="page feature-page">
      <PageHeader title="邮件通知" back="/settings" />
      {!loaded ? (
        <Loading compact />
      ) : !caps ? (
        <section className="state compact">
          <Toast message={loadError} tone="error" />
          <button onClick={() => void load()}>重新加载</button>
        </section>
      ) : (
        <>
          {emailSettings && (
            <EmailScheduleForm
              value={emailSettings}
              change={setEmailSettings}
              save={saveSettings}
              dispatch={() => void dispatch()}
              dispatching={dispatching}
            />
          )}
        </>
      )}
      <Toast {...toastProps} />
      {loaded && caps && (
        <form className="feature-card stack" onSubmit={send}>
          <h2>邮件通知</h2>
          <p className="muted">发送至已保存的收件邮箱，未填写时使用注册邮箱。</p>
          <label>
            主题
            <Input autoComplete="off" name="subject" required maxLength={200} />
          </label>
          <label>
            内容
            <TextArea autoComplete="off" name="body" required maxLength={2000} />
          </label>
          <button
            className="primary"
            disabled={!caps.smtp || !emailSettings?.notifications_enabled}
          >
            {caps.smtp ? "发送测试通知" : "邮件服务未配置"}
          </button>
        </form>
      )}
      <section className="feature-card">
        <h2>最近邮件</h2>
        {!deliveries.length ? (
          <p className="muted">暂无发送记录</p>
        ) : (
          <ul className="plain-list">
            {deliveries.map((item) => (
              <li key={item.id}>
                <button className="email-record" onClick={() => setSelected(item)}>
                  <strong>{item.subject}</strong>
                  <span className="muted">{deliveryStatus(item.status)} · 查看详情</span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
      {selected && (
        <EmailDetail item={selected} close={() => setSelected(null)} refresh={() => void load()} />
      )}
    </main>
  );
}
