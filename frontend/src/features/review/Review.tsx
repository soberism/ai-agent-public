import { Toast } from "../../shared/Toast";
import { PickerInput } from "../../shared/PickerInput";
import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ReviewConflict } from "./ReviewConflict";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { addDays, todayInZone } from "../todos/rules";

type Item = { id: string; title: string };
type Data = {
  summary: {
    completed_todos: number;
    ongoing_todos: number;
    events: number;
  };
  details: { completed: Item[]; ongoing: Item[]; events: Item[] };
  organize: { overdue: Item[]; unscheduled: Item[]; conflicts: { left: Item; right: Item }[] };
};

import { BackButton } from "../../shared/BackButton";

export function Review() {
  const session = useSession();
  const { call } = session;
  const [dates, setDates] = useState(() => {
    const today = todayInZone(new Date());
    const offset = (new Date(`${today}T12:00:00Z`).getUTCDay() + 6) % 7;
    const from = addDays(today, -offset);
    return { from, to: addDays(from, 6) };
  });
  const [data, setData] = useState<Data | null>(null);
  const [error, setError] = useState("");
  const requestVersion = useRef(0);
  const load = useCallback(async () => {
    const version = ++requestVersion.current;
    try {
      setError("");
      if (!dates.from || !dates.to || dates.from > dates.to) {
        setData(null);
        setError("请选择有效的起止日期，结束日期不能早于开始日期");
        return;
      }
      setData(null);
      const result = await call<Data>(
        `/planning/review?date_from=${dates.from}&date_to=${dates.to}`,
      );
      if (version === requestVersion.current) setData(result);
    } catch (reason) {
      if (version === requestVersion.current) setError(messageOf(reason));
    }
  }, [call, dates]);
  useEffect(() => void load(), [load]);
  return (
    <main className="page review-page">
      <header className="page-header">
        <BackButton className="back button" fallback="/features" />
        <h1>计划回顾</h1>
      </header>
      <p className="muted">查看完成情况，处理待办和需要调整的安排。</p>
      <fieldset className="review-date-range">
        <legend>时间范围</legend>
        <div className="event-time-grid">
          <label>
            开始日期
            <PickerInput
              type="date"
              value={dates.from}
              onChange={(e) => setDates({ ...dates, from: e.target.value })}
            />
          </label>
          <label>
            结束日期
            <PickerInput
              type="date"
              value={dates.to}
              onChange={(e) => setDates({ ...dates, to: e.target.value })}
            />
          </label>
        </div>
      </fieldset>
      {error && <Toast message={error} tone="error" />}
      {data && (
        <>
          <section className="review-summary" aria-label="完成情况">
            <a href="#review-completed">
              <strong>{data.summary.completed_todos}</strong> 已完成待办
            </a>
            <a href="#review-events">
              <strong>{data.summary.events}</strong> 期间日程
            </a>
          </section>
          <ReviewList
            title="逾期待办"
            note={`截止日期早于 ${dates.from}，尚未完成`}
            items={data.organize.overdue}
          />
          <ReviewList
            title={`期间待办（${data.summary.ongoing_todos}）`}
            note="截止日期在所选范围内，尚未完成"
            items={data.details.ongoing}
          />
          <section className="review-card">
            <h2>日程冲突</h2>
            <p className="muted small">检查所选范围内时间重叠的日程</p>
            {data.organize.conflicts.length === 0 ? (
              <p className="muted">没有发现冲突</p>
            ) : (
              data.organize.conflicts.map(({ left, right }) => (
                <ReviewConflict
                  key={`${left.id}-${right.id}`}
                  left={left}
                  right={right}
                  call={call}
                  reload={load}
                />
              ))
            )}
            {data.organize.conflicts.length > 0 && (
              <p className="muted small review-conflict-note">
                打开任一日程可调整；也可保留或稍后处理。
              </p>
            )}
          </section>
          <ReviewList
            title="未设日期"
            note="全部未设置截止日期的待办，不受日期筛选影响"
            items={data.organize.unscheduled}
          />
          <ReviewList
            id="review-completed"
            title="已完成待办"
            note="在所选范围内完成"
            items={data.details.completed}
          />
          <ReviewList
            id="review-events"
            title="期间日程"
            note="与所选范围有交集的日程"
            items={data.details.events}
            calendar
          />
        </>
      )}
    </main>
  );
}

function ReviewList({
  title,
  note,
  items,
  id,
  calendar = false,
}: {
  title: string;
  note: string;
  items: Item[];
  id?: string;
  calendar?: boolean;
}) {
  return (
    <section className="review-card" id={id}>
      <h2>{title}</h2>
      <p className="muted small">{note}</p>
      {items.length === 0 ? (
        <p className="muted">暂无</p>
      ) : (
        <ul>
          {items.map((item) => (
            <li key={item.id}>
              <Link to={calendar ? `/calendar/${item.id}/edit` : `/todos/${item.id}`}>
                {item.title}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
