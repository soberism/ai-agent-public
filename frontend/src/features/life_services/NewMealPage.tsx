import { useSharingEditor } from "../sharing/useSharingEditor";
import { SharingEditor } from "../sharing/SharingEditor";
import { Toast } from "../../shared/Toast";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { PageHeader } from "../../shared/PageHeader";
import type { Checklist } from "../checklists/types";
import { MealForm } from "./MealForm";

export function NewMealPage() {
  const { call } = useSession();
  const sharing = useSharingEditor("meal");
  const navigate = useNavigate();
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  const [lists, setLists] = useState<Checklist[]>([]);
  const [listError, setListError] = useState("");
  useEffect(() => {
    let active = true;
    void call<{ items: Checklist[] }>("/planning/checklists").then(
      (data) => {
        if (active) setLists(data.items.filter((item) => !item.meal_id));
      },
      (failure) => {
        if (active) setListError(messageOf(failure));
      },
    );
    return () => {
      active = false;
    };
  }, [call]);
  async function create(path: string, body: Record<string, unknown>) {
    if (pending.current) return false;
    pending.current = true;
    setSaving(true);
    setError("");
    try {
      await sharing.save(() =>
        call<{ id: string }>(path, { method: "POST", body: JSON.stringify(body) }),
      );
      navigate("/meals", { replace: true });
      return true;
    } catch (failure) {
      setError(messageOf(failure));
      return false;
    } finally {
      pending.current = false;
      setSaving(false);
    }
  }
  return (
    <main className="page feature-page">
      <PageHeader title="新建餐食计划" back="/meals" />
      {error && <Toast message={error} tone="error" />}
      <section className="feature-card">
        <h2>餐食信息</h2>
        {listError && (
          <Toast
            message={["清单加载失败：", listError, "，仍可自动新建。"].join("")}
            tone="error"
          />
        )}
        <MealForm
          visibility={<SharingEditor sharing={sharing} disabled={saving} />}
          locked={sharing.recovering}
          create={create}
          saving={saving}
          checklists={lists}
        />
      </section>
    </main>
  );
}
