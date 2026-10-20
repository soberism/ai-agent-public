import { Toast } from "../shared/Toast";
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, Outlet, useLocation } from "react-router-dom";
import { ApiError, messageOf, request } from "../shared/api";
import { Loading } from "../shared/Loading";
import type { User } from "../features/auth/types";
type State = "unknown" | "authenticated" | "anonymous" | "error";
type SessionContext = {
  user: User | null;
  state: State;
  authBusy: boolean;
  notice: string;
  generation: React.MutableRefObject<number>;
  establish: (user: User) => void;
  beginAuth: () => void;
  endAuth: (abandoned: boolean) => void;
  verify: () => Promise<void>;
  logout: () => Promise<void>;
  deactivate: () => Promise<void>;
  call: <T>(path: string, options?: RequestInit) => Promise<T>;
};
const Context = createContext<SessionContext>(null!);
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [state, setState] = useState<State>("unknown");
  const [notice, setNotice] = useState("");
  const [authBusy, setAuthBusy] = useState(false);
  const generation = useRef(0);
  const identity = useRef<User | null>(null);
  const verification = useRef(0);
  const authRequests = useRef(0);
  const deferredVerify = useRef(false);
  const establish = useCallback((next: User) => {
    if (identity.current?.id !== next.id) generation.current++;
    identity.current = next;
    setUser(next);
    setState("authenticated");
    setNotice("");
  }, []);
  const expire = useCallback(() => {
    generation.current++;
    identity.current = null;
    setUser(null);
    setState("anonymous");
    setNotice("登录已失效，请重新登录");
  }, []);
  const verify = useCallback(async () => {
    const token = generation.current;
    const check = ++verification.current;
    const wasAuthenticated = identity.current !== null;
    // Background checks keep the current form mounted until identity changes.
    setState((current) => (current === "error" ? "unknown" : current));
    try {
      const next = await request<User>("/auth/me");
      if (token === generation.current && check === verification.current) establish(next);
    } catch (error) {
      if (token !== generation.current || check !== verification.current) return;
      generation.current++;
      identity.current = null;
      setUser(null);
      if (error instanceof ApiError && error.status === 401) {
        setState("anonymous");
        setNotice(wasAuthenticated ? "登录已失效，请重新登录" : "");
      } else {
        setState("error");
        setNotice(messageOf(error));
      }
    }
  }, [establish]);
  const beginAuth = useCallback(() => {
    authRequests.current++;
    setAuthBusy(true);
    generation.current++;
  }, []);
  const endAuth = useCallback(
    (abandoned: boolean) => {
      authRequests.current = Math.max(0, authRequests.current - 1);
      if (!authRequests.current) setAuthBusy(false);
      if (authRequests.current === 0 && (deferredVerify.current || abandoned)) {
        deferredVerify.current = false;
        void verify();
      }
    },
    [verify],
  );
  useEffect(() => {
    void verify();
    const recheck = () => {
      if (authRequests.current) deferredVerify.current = true;
      else void verify();
    };
    const show = (event: PageTransitionEvent) => {
      if (event.persisted) {
        setState("unknown");
        recheck();
      }
    };
    const focus = () => {
      if (document.visibilityState === "visible") recheck();
    };
    window.addEventListener("pageshow", show);
    window.addEventListener("focus", focus);
    return () => {
      window.removeEventListener("pageshow", show);
      window.removeEventListener("focus", focus);
    };
  }, [verify]);
  const call = useCallback(
    async <T,>(path: string, options?: RequestInit): Promise<T> => {
      const token = generation.current;
      const owner = identity.current?.id;
      try {
        const data = await request<T>(path, options);
        if (token !== generation.current || owner !== identity.current?.id)
          throw new ApiError(-1, "STALE_RESPONSE", "请求已失效");
        return data;
      } catch (error) {
        if (token !== generation.current) throw new ApiError(-1, "STALE_RESPONSE", "请求已失效");
        if (error instanceof ApiError && error.status === 401) expire();
        throw error;
      }
    },
    [expire],
  );
  const deactivate = async () => {
    await call("/auth/account", { method: "DELETE" });
    expire();
    setNotice("");
  };
  const logout = async () => {
    generation.current++;
    setState("unknown");
    try {
      await request("/auth/logout", { method: "POST" });
      identity.current = null;
      setUser(null);
      setNotice("");
      setState("anonymous");
    } catch {
      setUser(null);
      setNotice("退出失败，请重试");
      setState("error");
    }
  };
  return (
    <Context
      value={{
        user,
        state,
        authBusy,
        notice,
        generation,
        establish,
        beginAuth,
        endAuth,
        verify,
        logout,
        deactivate,
        call,
      }}
    >
      {children}
    </Context>
  );
}
export const useSession = () => useContext(Context);
export function Protected() {
  const session = useSession();
  const location = useLocation();
  if (session.state === "unknown") return <Loading />;
  if (session.state === "error")
    return (
      <div className="state">
        <h1>暂时无法连接</h1>
        <Toast message={session.notice} tone="error" />
        <button
          onClick={() =>
            void (session.notice.startsWith("退出失败") ? session.logout() : session.verify())
          }
        >
          重试
        </button>
      </div>
    );
  if (!session.user)
    return (
      <Navigate
        to={`/login?returnTo=${encodeURIComponent(`${location.pathname}${location.search}${location.hash}`)}`}
        replace
      />
    );
  return <Outlet key={session.user.id} />;
}
