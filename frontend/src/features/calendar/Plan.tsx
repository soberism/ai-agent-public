import { Link } from "react-router-dom";

export function Plan() {
  return (
    <main className="page platform-page">
      <header className="platform-header">
        <div>
          <p className="eyebrow">安排儿</p>
          <h1>计划</h1>
        </div>
      </header>
      <section className="plan-grid" aria-label="计划功能">
        <Link className="plan-card" to="/todos">
          <span aria-hidden="true">✓</span>
          <strong>待办</strong>
          <small>记录、筛选并完成要做的事</small>
        </Link>
        <Link className="plan-card" to="/calendar">
          <span aria-hidden="true">▦</span>
          <strong>日程</strong>
          <small>安排有明确起止时间的活动</small>
        </Link>
        <Link className="plan-card" to="/checklists">
          <span aria-hidden="true">☷</span>
          <strong>清单</strong>
          <small>维护可以重复使用的准备事项</small>
        </Link>
        <Link className="plan-card" to="/review">
          <span aria-hidden="true">◴</span>
          <strong>整理与摘要</strong>
          <small>处理遗漏、冲突并查看日周概览</small>
        </Link>
      </section>
      <p className="muted small">提醒仅保存在应用内，不代表系统通知已经送达。</p>
    </main>
  );
}
