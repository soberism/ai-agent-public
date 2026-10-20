import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { VisibilityControl } from "../sharing/VisibilityControl";
import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { ConfirmButton } from "../../shared/ConfirmButton";
import { Loading } from "../../shared/Loading";
import { PageHeader } from "../../shared/PageHeader";
import { PantryForm } from "./MealSupportingForms";
import type { DietaryPreference, PantryItem } from "./types";

export function MealSettingsPage() {
  const { call } = useSession();
  const sharing = useSharingEditor("pantry");
  const [preferences, setPreferences] = useState<DietaryPreference[]>([]);
  const [pantry, setPantry] = useState<PantryItem[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const load = useCallback(async () => {
    try {
      const data = await call<{
        preferences: DietaryPreference[];
        pantry: PantryItem[];
      }>("/life/meal-plans");
      setPreferences(data.preferences);
      setPantry(data.pantry);
      setError("");
    } catch (failure) {
      setError(messageOf(failure));
    } finally {
      setLoaded(true);
    }
  }, [call]);
  useEffect(() => void load(), [load]);
  async function create(path: string, body: Record<string, unknown>) {
    try {
      await sharing.save(() =>
        call<{ id: string }>(path, { method: "POST", body: JSON.stringify(body) }),
      );
      sharing.reset();
      await load();
      return true;
    } catch (failure) {
      setError(messageOf(failure));
      return false;
    }
  }
  async function remove(path: string) {
    await call(path, { method: "DELETE" });
    await load();
  }
  return (
    <main className="page feature-page">
      <PageHeader title="现有库存" back="/meals" />
      {error && <Toast message={error} tone="error" />}
      {!loaded ? (
        <Loading compact />
      ) : (
        <>
          {preferences.length > 0 && (
            <details className="feature-card meal-settings">
              <summary>历史全局偏好（未关联餐食）</summary>
              <ul className="plain-list meal-setting-items">
                {preferences.map((item) => (
                  <li key={item.id}>
                    <strong>{item.label}</strong>
                    <VisibilityControl kind="preference" id={item.id} />
                    <ConfirmButton
                      title="删除偏好或限制"
                      message={`确认删除“${item.label}”？`}
                      ariaLabel={`删除偏好或限制 ${item.label}`}
                      className="text-button danger"
                      onConfirm={() => remove(`/life/preferences/${item.id}`)}
                    >
                      删除
                    </ConfirmButton>
                  </li>
                ))}
              </ul>
            </details>
          )}
          <section className="feature-card meal-settings">
            <h2>库存食材</h2>
            <ul className="plain-list meal-setting-items">
              {pantry.map((item) => (
                <li key={item.id}>
                  <div>
                    <strong>{item.name}</strong>
                    <span>
                      {item.quantity} {item.unit}
                    </span>
                  </div>
                  <VisibilityControl kind="pantry" id={item.id} />
                  <ConfirmButton
                    title="删除库存"
                    message={`确认删除库存“${item.name}”？`}
                    ariaLabel={`删除库存 ${item.name}`}
                    className="text-button danger"
                    onConfirm={() => remove(`/life/pantry/${item.id}`)}
                  >
                    删除
                  </ConfirmButton>
                </li>
              ))}
            </ul>
            <PantryForm
              locked={sharing.recovering}
              create={create}
              visibility={<SharingEditor sharing={sharing} />}
            />
          </section>
        </>
      )}
    </main>
  );
}
