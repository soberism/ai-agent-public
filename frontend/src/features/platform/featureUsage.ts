import { orderedSections, unavailable } from "./features";

const available = orderedSections.filter((item) => !unavailable.has(item.to));
const windowMs = 30 * 24 * 60 * 60 * 1000;
const storageKey = (userId: string) => `feature-usage:${userId}`;
type Visit = { to: string; at: number };

function readVisits(userId: string, now: number): Visit[] {
  try {
    const value: unknown = JSON.parse(localStorage.getItem(storageKey(userId)) ?? "[]");
    if (!Array.isArray(value)) return [];
    return value.filter(
      (visit): visit is Visit =>
        typeof visit === "object" &&
        visit !== null &&
        typeof visit.at === "number" &&
        visit.at > now - windowMs &&
        visit.at <= now &&
        available.some((item) => item.to === visit.to),
    );
  } catch {
    return [];
  }
}

export function recordFeatureVisit(userId: string, pathname: string) {
  const feature = available.find(
    (item) => pathname === item.to || pathname.startsWith(`${item.to}/`),
  );
  if (!feature) return;
  const now = Date.now();
  try {
    // ponytail: 本机记录；需要跨设备统计时迁移到服务端。
    localStorage.setItem(
      storageKey(userId),
      JSON.stringify([...readVisits(userId, now), { to: feature.to, at: now }]),
    );
  } catch {
    // 浏览器禁止存储时，入口仍可使用并显示默认排序。
  }
}

export function frequentFeatures(userId: string) {
  const counts = new Map<string, number>();
  for (const visit of readVisits(userId, Date.now()))
    counts.set(visit.to, (counts.get(visit.to) ?? 0) + 1);
  return [...available]
    .sort((a, b) => (counts.get(b.to) ?? 0) - (counts.get(a.to) ?? 0))
    .slice(0, 5);
}
