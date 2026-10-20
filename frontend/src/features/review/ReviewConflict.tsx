import { Toast } from "../../shared/Toast";
import { useState } from "react";
import { Link } from "react-router-dom";
import { messageOf } from "../../shared/api";
import { ConfirmButton } from "../../shared/ConfirmButton";
type Item = { id: string; title: string };

export function ReviewConflict({
  left,
  right,
  call,
  reload,
}: {
  left: Item;
  right: Item;
  call: <T>(path: string, init?: RequestInit) => Promise<T>;
  reload: () => Promise<void>;
}) {
  const [suggestions, setSuggestions] = useState<{ starts_at: string; ends_at: string }[]>([]);
  const [error, setError] = useState("");
  async function suggest() {
    try {
      const value = await call<{ suggestions: { starts_at: string; ends_at: string }[] }>(
        `/workflows/conflicts/${right.id}/suggestions`,
      );
      setSuggestions(value.suggestions);
    } catch (reason) {
      setError(messageOf(reason));
    }
  }
  async function apply(value: { starts_at: string; ends_at: string }) {
    await call(`/workflows/conflicts/${right.id}/apply`, {
      method: "POST",
      body: JSON.stringify(value),
    });
    await reload();
  }
  return (
    <article className="review-conflict">
      <div className="review-conflict-heading">
        <p>
          <Link to={`/calendar/${left.id}/edit`}>{left.title}</Link> 与{" "}
          <Link to={`/calendar/${right.id}/edit`}>{right.title}</Link>
        </p>
        <button className="text-button" onClick={() => void suggest()}>
          推荐空闲时间
        </button>
      </div>
      {suggestions.map((value) => (
        <ConfirmButton
          key={value.starts_at}
          className=""
          confirmClassName="primary"
          title="调整日程时间"
          message={`确认将“${right.title}”调整为 ${new Date(value.starts_at).toLocaleString("zh-CN")} 至 ${new Date(value.ends_at).toLocaleString("zh-CN")}？`}
          confirmLabel="确认调整"
          onConfirm={() => apply(value)}
        >
          {new Date(value.starts_at).toLocaleString("zh-CN")} 调整到这里
        </ConfirmButton>
      ))}
      {error && <Toast message={error} tone="error" />}
    </article>
  );
}
