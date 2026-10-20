import Input from "@rc-component/input";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { Toast } from "../../shared/Toast";
import { PickerInput } from "../../shared/PickerInput";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import type { Appointment, ServiceCapabilities } from "./types";

const labels: Record<Appointment["status"], string> = {
  draft: "草稿",
  planned: "应用内计划",
  submitted: "已提交",
  confirmed: "已确认",
  cancelled: "已取消",
  unknown: "结果待核验",
};

export function AppointmentsPage() {
  const { call } = useSession();
  const sharing = useSharingEditor("appointment");
  const [items, setItems] = useState<Appointment[]>([]);
  const [capabilities, setCapabilities] = useState<ServiceCapabilities | null>(null);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    try {
      const [data, caps] = await Promise.all([
        call<{ items: Appointment[] }>("/life/appointments"),
        call<ServiceCapabilities>("/life/capabilities"),
      ]);
      setItems(data.items);
      setCapabilities(caps);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call]);
  useEffect(() => void load(), [load]);
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const preferredAt = String(data.get("preferred_at") ?? "");
    try {
      await sharing.save(() =>
        call<Appointment>("/life/appointments", {
          method: "POST",
          body: JSON.stringify({
            patient_name: data.get("patient_name"),
            institution: data.get("institution"),
            service_type: data.get("service_type"),
            preferred_at: new Date(preferredAt).toISOString(),
            fee_note: data.get("fee_note") || null,
          }),
        }),
      );
      sharing.reset();
      form.reset();
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }
  async function confirm(id: string) {
    try {
      await call(`/life/appointments/${id}/confirm`, { method: "POST", body: "{}" });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
    }
  }
  return (
    <main className="page feature-page">
      <PageHeader title="医疗安排" />
      <section className="feature-intro">
        <h2>先准备时间和材料</h2>
        <p>医疗功能不提供诊断；没有服务商凭据时只保存应用内计划。</p>
      </section>
      {error && <Toast message={error} tone="error" />}
      {!loaded ? (
        <Loading compact />
      ) : (
        <section className="feature-card">
          <h2>安排记录</h2>
          {!items.length ? (
            <p className="muted">还没有医疗安排</p>
          ) : (
            <ul className="plain-list">
              {items.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>
                      {item.patient_name} · {item.service_type}
                    </strong>
                    <span>
                      {item.institution} · {new Date(item.preferred_at).toLocaleString("zh-CN")}
                    </span>
                  </div>
                  <VisibilityControl kind="appointment" id={item.id} />
                  <span className="status-tag">{labels[item.status]}</span>
                  {item.external_receipt && <small>服务凭据：{item.external_receipt}</small>}
                  <div className="link-row">
                    {item.calendar_url && <Link to={item.calendar_url}>查看日程</Link>}
                    {item.todo_url && <Link to={item.todo_url}>查看准备待办</Link>}
                    {!item.calendar_url && !item.todo_url && (
                      <button className="text-button" onClick={() => void confirm(item.id)}>
                        加入日程与准备待办
                      </button>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
      <section className="feature-card">
        <h2>新建应用内安排</h2>
        <form className="compact-form" onSubmit={create}>
          <label>
            就诊人
            <Input
              disabled={sharing.recovering}
              autoComplete="off"
              name="patient_name"
              required
              maxLength={60}
            />
          </label>
          <label>
            机构
            <Input
              disabled={sharing.recovering}
              autoComplete="off"
              name="institution"
              required
              maxLength={100}
            />
          </label>
          <label>
            服务类型
            <Input
              disabled={sharing.recovering}
              autoComplete="off"
              name="service_type"
              required
              maxLength={80}
            />
          </label>
          <label>
            期望时间
            <PickerInput
              disabled={sharing.recovering}
              autoComplete="off"
              name="preferred_at"
              type="datetime-local"
              required
            />
          </label>
          <label className="wide-field">
            费用或材料备注
            <Input
              disabled={sharing.recovering}
              autoComplete="off"
              name="fee_note"
              maxLength={300}
            />
          </label>
          <SharingEditor sharing={sharing} />
          <button className="primary wide-field">保存安排</button>
        </form>
      </section>
      <button
        className="full"
        disabled={!capabilities?.medical_booking}
        aria-describedby="booking-note"
      >
        提交真实预约
      </button>
      <p id="booking-note" className="muted small">
        真实预约尚未接入，当前不会联系机构或产生费用。
      </p>
    </main>
  );
}
