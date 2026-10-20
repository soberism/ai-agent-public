import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Link, Outlet, useLocation } from "react-router-dom";
import { useSession } from "../../app/session";
import { ApiError, messageOf } from "../../shared/api";
import { activeSection, DraggableAssistantButton, nav, NavIcon } from "./ShellNavigation";
import type { PlatformSettings } from "./types";

import { recordFeatureVisit } from "./featureUsage";

type PlatformContextValue = {
  assistantReturnTo: string;
  settings: PlatformSettings | null;
  settingsError: string;
  updateSettings: (body: { nickname?: string; timezone?: string }) => Promise<void>;
};

const PlatformContext = createContext<PlatformContextValue>(null!);
export const usePlatform = () => useContext(PlatformContext);

export function AppShell() {
  const session = useSession();
  const { call, establish } = session;
  const location = useLocation();
  const userId = session.user?.id;
  const lastFeaturePath = useRef("");
  useEffect(() => {
    const path = `${userId}:${location.pathname}`;
    if (userId && lastFeaturePath.current !== path) {
      recordFeatureVisit(userId, location.pathname);
      lastFeaturePath.current = path;
    }
  }, [userId, location.pathname]);
  const [settings, setSettings] = useState<PlatformSettings | null>(null);
  const [settingsError, setSettingsError] = useState("");
  const [online, setOnline] = useState(() => navigator.onLine);
  const inAssistant =
    location.pathname === "/assistant" || location.pathname.startsWith("/assistant/");
  const [previousPage, setPreviousPage] = useState<string | null>(() =>
    inAssistant ? null : location.pathname + location.search + location.hash,
  );
  useEffect(() => {
    if (!inAssistant) setPreviousPage(location.pathname + location.search + location.hash);
  }, [inAssistant, location.pathname, location.search, location.hash]);
  const currentSection = inAssistant
    ? previousPage
      ? activeSection(previousPage.split(/[?#]/)[0])
      : null
    : activeSection(location.pathname);
  const hasBottomAction =
    location.pathname === "/calendar" ||
    location.pathname.startsWith("/todos") ||
    /^\/checklists\/(?:shopping\/)?[^/]+$/u.test(location.pathname) ||
    location.pathname.startsWith("/shopping/") ||
    (location.pathname === "/shopping" && location.search.includes("meal_id="));

  const loadSettings = useCallback(async () => {
    setSettingsError("");
    try {
      setSettings(await call<PlatformSettings>("/platform/settings"));
    } catch (error) {
      if (!(error instanceof ApiError && (error.status === -1 || error.status === 401)))
        setSettingsError(messageOf(error));
    }
  }, [call]);

  useEffect(() => {
    void loadSettings();
  }, [loadSettings, session.user?.id]);

  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0 });
  }, [location.pathname]);

  async function updateSettings(body: { nickname?: string; timezone?: string }) {
    const next = await call<PlatformSettings>("/platform/settings", {
      method: "PATCH",
      body: JSON.stringify(body),
    });
    setSettings(next);
    establish({ id: next.id, email: next.email, nickname: next.nickname, timezone: next.timezone });
  }

  return (
    <PlatformContext
      value={{ settings, settingsError, updateSettings, assistantReturnTo: previousPage ?? "/" }}
    >
      <div className="app-shell">
        {!online && (
          <p className="offline-banner" role="status">
            当前处于离线状态，部分内容可能无法更新。
          </p>
        )}
        <Outlet />
        <DraggableAssistantButton
          hidden={location.pathname.startsWith("/assistant")}
          raised={hasBottomAction}
        />
        <nav className="bottom-nav" aria-label="全局导航">
          {nav.map(([to, label, icon]) => (
            <Link
              key={to}
              to={to}
              className={currentSection === to ? "active" : undefined}
              aria-current={currentSection === to ? "page" : undefined}
            >
              <NavIcon name={icon} />
              <span className="bottom-nav-label">{label}</span>
            </Link>
          ))}
        </nav>
      </div>
    </PlatformContext>
  );
}

export function LockedAction({
  children,
  descriptionId,
}: {
  children: ReactNode;
  descriptionId: string;
}) {
  return (
    <button className="locked-action" type="button" disabled aria-describedby={descriptionId}>
      {children}
    </button>
  );
}
