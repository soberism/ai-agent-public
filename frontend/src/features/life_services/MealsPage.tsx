import { VisibilityControl } from "../sharing/VisibilityControl";
import { useToast } from "../../shared/useToast";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import { mealTypeLabels, type MealPlan } from "./types";

export function MealsPage() {
  const { call } = useSession();
  const { setNotice, toastProps } = useToast();
  const [plans, setPlans] = useState<MealPlan[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    try {
      const data = await call<{
        items: MealPlan[];
      }>("/life/meal-plans");
      setPlans(data.items);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
      setNotice(messageOf(failure), "error");
    } finally {
      setLoaded(true);
    }
  }, [call, setNotice]);
  useEffect(() => void load(), [load]);
  async function confirm(id: string) {
    try {
      await call(`/life/meal-plans/${id}/confirm`, { method: "POST", body: "{}" });
      await load();
    } catch (failure) {
      setError(messageOf(failure));
      setNotice(messageOf(failure), "error");
    }
  }
  return (
    <main className="page feature-page">
      <PageHeader title="餐食计划" />
      <div className={loaded && !error && !plans.length ? "meal-welcome" : "section-heading"}>
        {loaded && !error && !plans.length && (
          <>
            <svg className="meal-welcome-art" viewBox="0 0 240 180" aria-hidden="true">
              <ellipse cx="120" cy="160" rx="70" ry="8" fill="var(--line)" />
              <circle cx="120" cy="85" r="68" fill="var(--purple)" />
              <circle cx="120" cy="85" r="53" fill="var(--surface)" />
              <circle cx="120" cy="85" r="39" fill="none" stroke="var(--line)" strokeWidth="2" />
              <path
                d="M42 48v24m8-24v24m8-24v24M42 65q0 16 8 16t8-16M50 81v49M192 48v82m0-82q-16 10-16 36h16"
                fill="none"
                stroke="var(--purple-ink)"
                strokeWidth="4"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              <path d="M103 94q-10-29 15-34 9 24-15 34" fill="var(--green)" />
              <path d="M113 97q1-30 26-23-1 26-26 23" fill="var(--peach)" />
            </svg>
            <h2>把每一餐，安排得刚刚好</h2>
            <p>
              记下想吃的菜和用餐安排，
              <br />
              让下一餐少一点纠结。
            </p>
          </>
        )}
        <Link className="button primary" to="/meals/new">
          新建餐食计划
        </Link>
        {loaded && !error && !plans.length && (
          <span className="meal-welcome-note">菜品、偏好、清单，一起记在这里</span>
        )}
      </div>
      <Toast {...toastProps} />
      {!loaded ? (
        <Loading compact />
      ) : error && !plans.length ? null : (
        <MealRows
          items={plans}
          confirm={confirm}
          remove={async (id) => {
            await call(`/life/meal-plans/${id}`, { method: "DELETE" });
            setPlans((current) => current.filter((item) => item.id !== id));
          }}
        />
      )}
    </main>
  );
}

function MealRows({
  items,
  confirm,
  remove,
}: {
  items: MealPlan[];
  confirm: (id: string) => Promise<void>;
  remove: (id: string) => Promise<void>;
}) {
  if (!items.length) return null;
  return (
    <ul className="checklist-list meal-plan-items">
      {items.map((item) => (
        <li key={item.id}>
          <Link className="meal-plan-summary" to={`/meals/${item.id}`}>
            <strong>{item.title ?? item.dish}</strong>
            {item.title && item.title !== item.dish && <small>{item.dish}</small>}
            {item.date && (
              <span>
                <time dateTime={item.date}>{item.date}</time>
              </span>
            )}
            <span>
              {(item.schedule_text?.trim() === item.title ? "" : item.schedule_text) ??
                [
                  item.meal_type ? (mealTypeLabels[item.meal_type] ?? item.meal_type) : "",
                  item.diners != null ? `${item.diners} 人` : "",
                ]
                  .filter(Boolean)
                  .join(" · ")}
            </span>
            {item.notes && <small>{item.notes}</small>}
          </Link>
          <div className="link-row">
            <VisibilityControl kind="meal" id={item.id} />
            {item.shopping_url ? (
              <Link to={item.shopping_url}>清单</Link>
            ) : (
              <Link to={`/shopping?meal_id=${encodeURIComponent(item.id)}`}>创建清单</Link>
            )}
            {item.calendar_url ? (
              <Link to={item.calendar_url}>查看餐食日程</Link>
            ) : (
              <button className="text-button" onClick={() => void confirm(item.id)}>
                加入日历
              </button>
            )}
            <ConfirmButton
              title="删除餐食计划"
              message="删除后无法恢复。关联的清单和日程会保留。"
              ariaLabel={`删除餐食计划 ${item.dish}`}
              className="text-button danger"
              onConfirm={() => remove(item.id)}
            >
              删除
            </ConfirmButton>
          </div>
        </li>
      ))}
    </ul>
  );
}
