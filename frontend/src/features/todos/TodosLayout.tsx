import { useCallback, useEffect, useState } from "react";
import { Outlet } from "react-router-dom";
import { useSession } from "../../app/session";
import type { ListState } from "./context";
import { Context } from "./context";

const listCache = new Map<string, ListState>();

export function TodosLayout() {
  const session = useSession();
  const [list, setList] = useState<ListState>(
    () =>
      listCache.get(session.user!.id) ?? {
        status: "ongoing",
        due: "all",
        page: null,
        scroll: 0,
      },
  );
  const [notice, setNotice] = useState("");
  const [noticeTone, setNoticeTone] = useState<"success" | "error">("success");
  const notify = useCallback((value: string, tone: "success" | "error" = "success") => {
    setNotice(value);
    setNoticeTone(tone);
  }, []);
  useEffect(() => {
    listCache.set(session.user!.id, list);
  }, [list, session.user]);
  return (
    <Context value={{ list, setList, notice, noticeTone, notify }}>
      <main className="page todo-page">
        <Outlet />
      </main>
    </Context>
  );
}
