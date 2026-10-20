import Input, { TextArea } from "@rc-component/input";
import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { Toast } from "../../shared/Toast";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { EventTimeFields } from "./EventTimeFields";
import { Select } from "../../shared/Select";
import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { validateEvent } from "./rules";
import { eventPayload, valuesOf, type CalendarEvent, type EventValues } from "./types";

import { todayInZone } from "../todos/rules";
import { BackButton } from "../../shared/BackButton";

export function EventEditor() {
  const { id } = useParams();
  const sharing = useSharingEditor("event", id);
  const [search] = useSearchParams();
  const session = useSession();
  const { call } = session;
  const navigate = useNavigate();
  const initial = valuesOf();
  initial.start_date = initial.end_date = search.get("date") ?? todayInZone(new Date());
  initial.todo_id = search.get("todo");
  initial.title = search.get("title") ?? "";
  const [values, setValues] = useState<EventValues>(initial);
  const [loaded, setLoaded] = useState(!id);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [feedbackRevision, setFeedbackRevision] = useState(0);
  useEffect(() => {
    if (!id) return;
    call<CalendarEvent>(`/calendar/events/${id}`).then(
      (event) => {
        setValues(valuesOf(event));
        setLoaded(true);
      },
      (reason) => {
        setError(messageOf(reason));
        setLoaded(true);
      },
    );
  }, [call, id]);
  const update = (key: keyof EventValues, value: string) =>
    setValues((current) => ({ ...current, [key]: value }));
  async function save(event: FormEvent) {
    event.preventDefault();
    setFeedbackRevision((value) => value + 1);
    const next = { ...values, title: values.title.trim() || "未命名日程" };
    setValues(next);
    const validation = validateEvent(next);
    if (Object.keys(validation).length) {
      setError(Object.values(validation)[0]);
      return;
    }
    setBusy(true);
    setError("");
    try {
      await sharing.save(() =>
        call<CalendarEvent>(id ? `/calendar/events/${id}` : "/calendar/events", {
          method: id ? "PUT" : "POST",
          body: JSON.stringify(eventPayload(next)),
        }),
      );
      navigate(`/calendar?date=${values.start_date}`);
    } catch (reason) {
      setError(messageOf(reason));
      setBusy(false);
    }
  }
  async function remove() {
    if (!id) return;
    setBusy(true);
    setError("");
    try {
      await call(`/calendar/events/${id}`, { method: "DELETE" });
      navigate("/calendar");
    } catch (reason) {
      setError(messageOf(reason));
      setBusy(false);
    }
  }
  if (!loaded)
    return (
      <main className="page">
        <p role="status">正在加载日程…</p>
      </main>
    );
  return (
    <main className="page calendar-page">
      <header className="page-header">
        <BackButton className="back button" fallback="/calendar" />
        <h1>{id ? "日程详情" : "新建日程"}</h1>
      </header>
      <form autoComplete="off" className="stack editor" noValidate onSubmit={save}>
        <label>
          标题（可选）
          <Input
            disabled={sharing.recovering}
            placeholder="留空自动使用“未命名日程”"
            value={values.title}
            onChange={(e) => update("title", e.target.value)}
          />
        </label>
        <EventTimeFields values={values} setValues={setValues} />
        <label>
          地点（可选）
          <Input
            disabled={sharing.recovering}
            className="event-location"
            value={values.location}
            onChange={(e) => update("location", e.target.value)}
          />
        </label>
        <label>
          说明（可选）
          <TextArea
            disabled={sharing.recovering}
            className="event-description"
            rows={1}
            value={values.description}
            onChange={(e) => update("description", e.target.value)}
          />
        </label>
        {id && (
          <label>
            状态
            <Select
              value={values.status}
              onChange={(event) => update("status", event.target.value)}
            >
              <option value="scheduled">已安排</option>
              <option value="cancelled">已取消</option>
            </Select>
          </label>
        )}
        {id && <p className="muted small">来源：应用内</p>}
        {values.todo_id && <p className="success-box">此日程将作为待办时间块保存。</p>}
        <SharingEditor sharing={sharing} disabled={busy} />
        {error && <Toast key={feedbackRevision} message={error} tone="error" />}
        <button className="primary full" disabled={busy}>
          {busy ? "保存中…" : "保存日程"}
        </button>
        {id && (
          <ConfirmButton
            className="danger full"
            disabled={busy}
            title="删除日程"
            message={`确认删除“${values.title}”吗？删除后无法恢复。`}
            onConfirm={remove}
          >
            删除日程
          </ConfirmButton>
        )}
      </form>
    </main>
  );
}
