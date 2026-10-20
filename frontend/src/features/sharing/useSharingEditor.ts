import { useCallback, useEffect, useRef, useState } from "react";
import { useSession } from "../../app/session";
import { messageOf } from "../../shared/api";
import { sharingOptions, invalidateSharingOptions } from "./options";
import type { SharingHousehold, SharingPolicy } from "./types";

const privatePolicy = (): SharingPolicy => ({
  scope: "private",
  household_id: null,
  member_ids: [],
});

export function useSharingEditor(kind: string, id?: string) {
  const { call, user, generation } = useSession();
  const [policy, setPolicy] = useState<SharingPolicy>(privatePolicy);
  const original = useRef(JSON.stringify(privatePolicy()));
  const [homes, setHomes] = useState<SharingHousehold[]>([]);
  const [ready, setReady] = useState(!id);
  const [canEdit, setCanEdit] = useState(!id);
  const [error, setError] = useState("");
  const [recovering, setRecovering] = useState(false);
  const revision = useRef<object>({});
  const pending = useRef(false);
  const saved = useRef<{ owner: string; value: { id: string } } | null>(null);
  const load = useCallback(async () => {
    const token = {};
    revision.current = token;
    saved.current = null;
    setRecovering(false);
    if (!id) {
      setPolicy(privatePolicy());
      original.current = JSON.stringify(privatePolicy());
      setReady(true);
      setCanEdit(true);
      return;
    }
    setReady(false);
    setError("");
    try {
      const result = await call<{ editable: string[] }>(
        `/sharing/states?resources=${encodeURIComponent(`${kind}:${id}`)}`,
      );
      if (token !== revision.current) return;
      const editable = result.editable?.includes(`${kind}:${id}`) ?? false;
      setCanEdit(editable);
      if (editable) {
        const value = await call<SharingPolicy>(`/sharing/${kind}/${id}`);
        if (token !== revision.current) return;
        original.current = JSON.stringify(value);
        setPolicy(value);
      }
      setReady(true);
    } catch (failure) {
      if (token === revision.current) setError(messageOf(failure));
    }
  }, [call, kind, id]);
  useEffect(() => {
    void load();
    return () => {
      revision.current = {};
    };
  }, [load]);
  const loadOptions = useCallback(async () => {
    try {
      const options = await sharingOptions(user!.id, generation.current, () =>
        call<{ households: SharingHousehold[] }>("/sharing/options"),
      );
      setHomes(options.households);
      setPolicy((current) =>
        current.scope !== "private" && !current.household_id
          ? { ...current, household_id: options.households[0]?.id ?? null }
          : current,
      );
      setError("");
    } catch (failure) {
      invalidateSharingOptions();
      setError(messageOf(failure));
    }
  }, [call, user, generation]);
  useEffect(() => {
    if (canEdit && policy.scope !== "private") void loadOptions();
  }, [canEdit, policy.scope, loadOptions]);
  const changed = JSON.stringify(policy) !== original.current;
  async function save<T extends { id: string }>(write: () => Promise<T>): Promise<T> {
    if (pending.current) throw new Error("正在保存，请稍后");
    pending.current = true;
    try {
      if (!ready) throw new Error(error || "可见范围正在加载，请稍后保存");
      if (canEdit && policy.scope !== "private") {
        if (!homes.some((home) => home.id === policy.household_id)) throw new Error("请选择家庭");
        if (policy.scope === "members" && !policy.member_ids.length)
          throw new Error("请选择可见成员");
      }
      const owner = `${user!.id}:${generation.current}`;
      if (saved.current && saved.current.owner !== owner)
        throw new Error("会话已变化，请重新打开表单");
      // A permission retry reuses the saved item instead of creating a duplicate.
      const value = (saved.current?.value as T | undefined) ?? (await write());
      if (canEdit && (changed || saved.current)) {
        saved.current = { owner, value };
        try {
          await call(`/sharing/${kind}/${value.id}`, {
            method: "PUT",
            body: JSON.stringify(policy),
          });
        } catch (failure) {
          setRecovering(true);
          invalidateSharingOptions();
          throw new Error(
            `内容已保存，但可见范围未确认：${messageOf(failure)}。再次保存仅重试可见范围。`,
            { cause: failure },
          );
        }
      }
      saved.current = null;
      setRecovering(false);
      original.current = JSON.stringify(policy);
      return value;
    } finally {
      pending.current = false;
    }
  }

  function reset() {
    setPolicy(privatePolicy());
    original.current = JSON.stringify(privatePolicy());
    saved.current = null;
    setRecovering(false);
  }
  return {
    policy,
    setPolicy,
    homes,
    ready,
    canEdit,
    error,
    changed,
    recovering,
    save,
    reset,
    retry: id && !ready ? load : loadOptions,
  };
}
