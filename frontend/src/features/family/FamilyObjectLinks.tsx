import { Select } from "../../shared/Select";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import type { CalendarEvent } from "../calendar/types";
import type { SourceMaterial } from "../documents/types";
import type { HouseholdDetail } from "./types";
import { Toast } from "../../shared/Toast";
import { useToast } from "../../shared/useToast";

export function FamilyObjectLinks({ household }: { household: HouseholdDetail }) {
  const { call } = useSession();
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [materials, setMaterials] = useState<SourceMaterial[]>([]);
  const { setNotice, toastProps } = useToast();
  const load = useCallback(async () => {
    const start = new Date().toISOString().slice(0, 10);
    const end = `${Number(start.slice(0, 4)) + 1}${start.slice(4)}`;
    try {
      const [calendar, documents] = await Promise.all([
        call<{ items: CalendarEvent[] }>(`/calendar/events?date_from=${start}&date_to=${end}`),
        call<{ items: SourceMaterial[] }>("/documents/materials"),
      ]);
      setEvents(calendar.items);
      setMaterials(documents.items);
    } catch (failure) {
      setNotice(messageOf(failure), "error");
    }
  }, [call, setNotice]);
  useEffect(() => void load(), [load]);

  async function shareEvent(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const id = new FormData(event.currentTarget).get("event");
    try {
      await call(`/collaboration/events/${id}/share`, {
        method: "POST",
        body: JSON.stringify({ household_id: household.id }),
      });
      setNotice("日程已共享到家庭日历");
    } catch (failure) {
      setNotice(messageOf(failure), "error");
    }
  }

  async function linkDocument(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const [subject_type, subject_id] = String(data.get("subject")).split(":");
    try {
      await call(`/collaboration/documents/${data.get("document")}/link`, {
        method: "POST",
        body: JSON.stringify({ household_id: household.id, subject_type, subject_id }),
      });
      setNotice("文档归属已更新");
    } catch (failure) {
      setNotice(messageOf(failure), "error");
    }
  }

  const subjects = [
    ...household.profiles.map((item) => ({ value: `profile:${item.id}`, label: item.name })),
    ...household.pets.map((item) => ({ value: `pet:${item.id}`, label: item.name })),
  ];
  return (
    <section className="feature-card">
      <h3>共享日历与档案归属</h3>
      <Toast {...toastProps} />
      <form className="family-action-form" onSubmit={shareEvent}>
        <label>
          日程
          <Select name="event" required aria-label="选择日程">
            <option value="">选择日程</option>
            {events.map((item) => (
              <option key={item.id} value={item.id}>
                {item.title}
              </option>
            ))}
          </Select>
        </label>
        <button className="primary">共享到家庭日历</button>
      </form>
      <form className="family-action-form" onSubmit={linkDocument}>
        <label>
          文档
          <Select name="document" required aria-label="选择文档">
            <option value="">选择文档</option>
            {materials.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </Select>
        </label>
        <label>
          归属对象
          <Select name="subject" required aria-label="关联成员或宠物">
            <option value="">关联成员或宠物</option>
            {subjects.map((item) => (
              <option key={item.value} value={item.value}>
                {item.label}
              </option>
            ))}
          </Select>
        </label>
        <button className="primary">保存归属</button>
      </form>
    </section>
  );
}
