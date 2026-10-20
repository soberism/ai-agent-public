import { VisibilityControl } from "../sharing/VisibilityControl";
import { Toast } from "../../shared/Toast";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import { MealEditor } from "./MealEditor";
import type { MealPlan } from "./types";

export function MealDetailPage() {
  const navigate = useNavigate();
  const { id } = useParams();
  const { call } = useSession();
  const [meal, setMeal] = useState<MealPlan | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    void call<MealPlan>(`/life/meal-plans/${id}`).then(
      (item) => {
        if (active) setMeal(item);
      },
      (failure) => {
        if (active) setError(messageOf(failure));
      },
    );
    return () => {
      active = false;
    };
  }, [call, id]);
  return (
    <main className="page feature-page">
      <PageHeader title="餐食详情" back="/meals" />
      {error ? (
        <Toast message={error} tone="error" />
      ) : !meal ? (
        <Loading compact />
      ) : (
        <>
          <section className="feature-card">
            <h2>餐食信息</h2>
            <VisibilityControl kind="meal" id={meal.id} />
            <MealEditor key={meal.id} meal={meal} onSaved={setMeal} />
            <div className="meal-detail-actions">
              {meal.shopping_url ? (
                <Link className="button primary full" to={meal.shopping_url}>
                  查看清单
                </Link>
              ) : (
                <Link
                  className="button primary full"
                  to={`/shopping?meal_id=${encodeURIComponent(meal.id)}`}
                >
                  创建清单
                </Link>
              )}
              <ConfirmButton
                title="删除餐食计划"
                message="删除后无法恢复。关联的清单和日程会保留。"
                ariaLabel={`删除餐食计划 ${meal.dish}`}
                className="danger full"
                onConfirm={async () => {
                  await call(`/life/meal-plans/${meal.id}`, { method: "DELETE" });
                  navigate("/meals", { replace: true });
                }}
              >
                删除餐食计划
              </ConfirmButton>
              {meal.calendar_url && (
                <Link className="button full" to={meal.calendar_url}>
                  查看餐食日程
                </Link>
              )}
            </div>
          </section>
        </>
      )}
    </main>
  );
}
