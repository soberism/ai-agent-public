import { Toast } from "../../shared/Toast";
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useSession } from "../../app/session";
import { ApiError } from "../../shared/api";
import { Avatar } from "../../shared/Avatar";
import { Loading } from "../../shared/Loading";
import { TodoSummary } from "./TodoSummary";
import { RecentUpdates } from "./RecentUpdates";
import { TodaySchedule } from "./TodaySchedule";
import { todayInZone } from "../todos/rules";
import type { PlatformHome, HubSummary } from "./types";

import { FamilyAttention } from "../family/FamilyAttention";

import { FrequentFeatures } from "./FrequentFeatures";

const homeCache = new Map<string, { home: PlatformHome; hub: HubSummary }>();

export function Home() {
  const session = useSession();
  const { call } = session;
  const cached = homeCache.get(session.user!.id);
  const [home, setHome] = useState<PlatformHome | null>(() => cached?.home ?? null);
  const [hub, setHub] = useState<HubSummary | null>(() => cached?.hub ?? null);
  const [error, setError] = useState("");
  const [familyCount, setFamilyCount] = useState(0);
  const [upcoming, setUpcoming] = useState<number | null>(null);
  const load = useCallback(async () => {
    setError("");
    try {
      const [nextHome, nextHub] = await Promise.all([
        call<PlatformHome>("/platform/home"),
        call<HubSummary>("/hub/summary"),
      ]);
      setHome(nextHome);
      setHub(nextHub);
      homeCache.set(session.user!.id, { home: nextHome, hub: nextHub });
    } catch (failure) {
      if (!(failure instanceof ApiError && (failure.status === -1 || failure.status === 401)))
        setError("首页加载失败，请重试");
    }
  }, [call, session.user]);
  useEffect(() => void load(), [load]);
  const attentionItems =
    home && hub
      ? [
          { title: "待办逾期", to: "/todos", count: home.overdue.count },
          { title: "文档待审核", to: "/document-review", count: hub.pending_reviews },
          {
            title: "邮件发送失败",
            to: "/connections",
            count: hub.failed_emails,
          },
          {
            title: "发信服务未配置",
            to: "/connections",
            count: hub.connection_issues,
          },
          {
            title: "日程即将开始",
            to: `/calendar?date=${todayInZone(new Date())}`,
            count: upcoming,
          },
        ].filter((item) => item.count !== null && item.count > 0)
      : [];

  return (
    <main className="page platform-page">
      <header className="platform-header">
        <div>
          <h1>今天，一起安排好</h1>
        </div>
        <Link className="avatar-link" to="/settings" aria-label="打开我的">
          <Avatar {...session.user!} />
        </Link>
      </header>
      <section aria-labelledby="quick-title">
        <div className="section-heading">
          <h2 id="quick-title">快捷操作</h2>
        </div>
        <div className="quick-grid">
          <Link className="quick-card primary-card" to="/todos/new">
            <span>＋</span>
            <strong>新建待办</strong>
          </Link>
          <Link className="quick-card" to="/assistant">
            <span>✦</span>
            <strong>问问 AI</strong>
          </Link>
          <Link className="quick-card" to="/search">
            <svg aria-hidden="true" viewBox="0 0 24 24">
              <circle cx="11" cy="11" r="6" />
              <path d="m16 16 4 4" />
            </svg>
            <strong>全局搜索</strong>
          </Link>
        </div>
      </section>
      <FrequentFeatures />
      {error && home && <Toast message={[error, "，当前显示上次数据"].join("")} tone="error" />}
      {error && !home ? (
        <section className="state compact">
          <Toast message={error} tone="error" />
          <button onClick={() => void load()}>重新加载</button>
        </section>
      ) : !home || !hub ? (
        <Loading compact />
      ) : (
        <>
          {
            <section
              className="home-card attention-card"
              hidden={!attentionItems.length && !familyCount}
              aria-labelledby="attention-title"
            >
              <div className="section-heading">
                <h2 id="attention-title">需要关注</h2>
              </div>
              <div className="service-grid attention-grid">
                <FamilyAttention onCount={setFamilyCount} />
                {attentionItems.map((item) => (
                  <Link key={item.to} to={item.to}>
                    <strong className={item.to === "/todos" ? "overdue" : undefined}>
                      {item.count}
                    </strong>
                    <small>{item.title}</small>
                  </Link>
                ))}
              </div>
            </section>
          }
          <TodaySchedule onUpcomingChange={setUpcoming} />
          <section className="home-card home-summary" aria-labelledby="today-title">
            <div className="section-heading">
              <h2 id="today-title">
                今天的待办 <span className="summary-total">{home.today.count} 项</span>
              </h2>
              <Link to="/todos">查看全部</Link>
            </div>
            <TodoSummary items={home.today.items} serverTime={home.server_time} />
          </section>
          <section className="home-card" aria-labelledby="recent-title">
            <div className="section-heading">
              <h2 id="recent-title">最近更新</h2>
            </div>
            <RecentUpdates home={home} />
          </section>
        </>
      )}
      <section aria-labelledby="future-title">
        <div className="section-heading">
          <h2 id="future-title">更多生活服务</h2>
        </div>
        <div
          className="service-grid"
          role="region"
          aria-label="更多生活服务，横向滚动"
          tabIndex={0}
        >
          <Link to="/family">
            <strong>家庭</strong>
            <small>家庭成员管理</small>
          </Link>
          <Link to="/documents">
            <strong>文档</strong>
            <small>上传文件、分目录整理</small>
          </Link>
          <Link to="/meals">
            <strong>餐食</strong>
            <small>偏好与购物准备</small>
          </Link>
          <button disabled>
            <strong>医疗</strong>
            <small>暂未开放</small>
          </button>
        </div>
        <Link className="app-nav-link" to="/features">
          查看全部功能
        </Link>
      </section>
    </main>
  );
}
