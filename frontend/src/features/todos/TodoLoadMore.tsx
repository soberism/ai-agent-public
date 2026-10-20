import { useEffect, useRef } from "react";

export function TodoLoadMore({
  cursor,
  loading,
  error,
  load,
}: {
  cursor: string;
  loading: boolean;
  error: string;
  load: (cursor: string) => Promise<void>;
}) {
  const target = useRef<HTMLDivElement>(null);
  const pending = useRef(false);
  useEffect(() => {
    if (loading || error || !target.current) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (!entry.isIntersecting || pending.current) return;
        pending.current = true;
        void load(cursor).finally(() => {
          pending.current = false;
        });
      },
      { rootMargin: "200px" },
    );
    observer.observe(target.current);
    return () => observer.disconnect();
  }, [cursor, loading, error, load]);
  return (
    <div ref={target} className="load-more">
      {error ? (
        <button disabled={loading} onClick={() => void load(cursor)}>
          重试加载更多
        </button>
      ) : (
        <span role="status" className="muted">
          {loading ? "正在加载更多…" : "继续下滑加载更多"}
        </span>
      )}
    </div>
  );
}
