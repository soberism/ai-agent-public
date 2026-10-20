export function Loading({ compact = false }: { compact?: boolean }) {
  return (
    <div className={`loading-state${compact ? " compact" : ""}`} role="status" aria-live="polite">
      <span className="loading-spinner" aria-hidden="true" />
      <span>加载中</span>
    </div>
  );
}
