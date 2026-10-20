import { useEffect, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { Toast } from "../../shared/Toast";
import { Loading } from "../../shared/Loading";

export function ShoppingListsPage() {
  const [params] = useSearchParams();
  return params.has("meal_id") ? <ShoppingDetailRedirect /> : <Navigate to="/checklists" replace />;
}

export function ShoppingDetailRedirect() {
  const { call } = useSession();
  const { id } = useParams();
  const [params] = useSearchParams();
  const mealId = params.get("meal_id");
  const path = id
    ? `/life/shopping-lists/${id}`
    : `/life/shopping-lists?meal_id=${encodeURIComponent(mealId ?? "")}`;
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setError("");
    setUrl("");
    void call<{ checklist_url: string }>(path).then(
      (value) => {
        if (active) {
          if (/^\/checklists\/[^/]+$/u.test(value.checklist_url)) setUrl(value.checklist_url);
          else setError("清单不存在或无法访问");
        }
      },
      (reason) => {
        if (active) setError(messageOf(reason));
      },
    );
    return () => {
      active = false;
    };
  }, [call, path]);
  if (url) return <Navigate to={url} replace />;
  return (
    <main className="page">{error ? <Toast message={error} tone="error" /> : <Loading />}</main>
  );
}
