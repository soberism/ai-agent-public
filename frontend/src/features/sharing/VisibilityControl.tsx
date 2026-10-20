import { useEffect, useState } from "react";
import { useSession } from "../../app/session";
import { Modal } from "../../shared/Modal";
import { Select } from "../../shared/Select";
import { messageOf } from "../../shared/api";
import { knownVisibilityState, rememberVisibilityState, visibilityState } from "./states";
import { sharingOptions, invalidateSharingOptions } from "./options";
import type { SharingHousehold, SharingPolicy } from "./types";

export function VisibilityControl({ kind, id }: { kind: string; id: string }) {
  const { call, user, generation } = useSession();
  const owner = `${user!.id}:${generation.current}`;
  const key = `${kind}:${id}`;
  const [scope, setScope] = useState<SharingPolicy["scope"] | null>(() =>
    knownVisibilityState(owner, key),
  );
  useEffect(() => {
    let active = true;
    void visibilityState(owner, key, (keys) =>
      call<{ states: Record<string, SharingPolicy["scope"]>; editable: string[] }>(
        `/sharing/states?resources=${encodeURIComponent(keys.join(","))}`,
      ),
    )
      .then((value) => {
        if (active) setScope(value ?? null);
      })
      .catch(() => {
        if (active) setScope(null);
      });
    return () => {
      active = false;
    };
  }, [call, owner, key]);
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [homes, setHomes] = useState<SharingHousehold[]>([]);
  const [policy, setPolicy] = useState<SharingPolicy>({
    scope: "private",
    household_id: null,
    member_ids: [],
  });
  const home = homes.find((item) => item.id === policy.household_id);
  const members = home?.members ?? [];
  async function load() {
    setOpen(true);
    setLoaded(false);
    setError("");
    try {
      const [value, options] = await Promise.all([
        call<SharingPolicy>(`/sharing/${kind}/${id}`),
        sharingOptions(user!.id, generation.current, () =>
          call<{ households: SharingHousehold[] }>("/sharing/options"),
        ),
      ]);
      setPolicy(value);
      setScope(value.scope);
      rememberVisibilityState(owner, key, value.scope);
      setHomes(options.households);
      setLoaded(true);
    } catch (failure) {
      invalidateSharingOptions();
      setError(messageOf(failure));
    }
  }
  async function save(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError("");
    try {
      const saved = await call<SharingPolicy>(`/sharing/${kind}/${id}`, {
        method: "PUT",
        body: JSON.stringify(policy),
      });
      setScope(saved.scope);
      rememberVisibilityState(owner, key, saved.scope);
      setOpen(false);
    } catch (failure) {
      invalidateSharingOptions();
      setError(messageOf(failure));
    } finally {
      setBusy(false);
    }
  }
  if (!scope) return null;
  return (
    <>
      <button type="button" className="text-button" onClick={() => void load()}>
        {scope ? { private: "自己可见", household: "家庭可见", members: "部分可见" }[scope] : "…"}
      </button>
      {open && (
        <Modal
          title="可见范围"
          className="visibility-dialog"
          close={() => {
            if (!busy) setOpen(false);
          }}
        >
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {!loaded ? (
            error ? (
              <button type="button" onClick={() => void load()}>
                重新加载
              </button>
            ) : (
              <p role="status">正在加载可见范围…</p>
            )
          ) : (
            <form className="stack" onSubmit={save}>
              <p className="muted small">
                获授权的人可以编辑和删除内容，只有内容创建者可以修改可见范围。创建者和管理员可邀请、移出成员，角色变更仅限创建者。
              </p>
              <label>
                谁可以访问
                <Select
                  value={policy.scope}
                  onChange={(event) => {
                    const scope = event.target.value as SharingPolicy["scope"];
                    setPolicy({
                      scope,
                      household_id:
                        scope === "private" ? null : (policy.household_id ?? homes[0]?.id ?? null),
                      member_ids: [],
                    });
                  }}
                >
                  <option value="private">自己可见</option>
                  <option value="household">家庭可见</option>
                  <option value="members">部分可见</option>
                </Select>
              </label>
              {policy.scope === "private" && (
                <p className="muted small">
                  私有内容仅创建者可访问。已共享成员改为私有后会失去访问权。
                </p>
              )}
              {policy.scope !== "private" && (
                <>
                  <label>
                    家庭
                    <Select
                      required
                      value={policy.household_id ?? ""}
                      onChange={(event) =>
                        setPolicy({ ...policy, household_id: event.target.value, member_ids: [] })
                      }
                    >
                      <option value="">请选择家庭</option>
                      {homes.map((item) => (
                        <option key={item.id} value={item.id}>
                          {item.name}
                        </option>
                      ))}
                    </Select>
                  </label>
                  {policy.scope === "household" ? (
                    <p className="muted small">所有家庭成员可访问。</p>
                  ) : (
                    <fieldset>
                      <legend>选择成员</legend>
                      {!members.length && <p className="muted">暂无可选人员</p>}
                      {members.map((item) => (
                        <label className="check-row" key={item.account_id}>
                          <input
                            type="checkbox"
                            checked={policy.member_ids.includes(item.account_id)}
                            onChange={(event) =>
                              setPolicy({
                                ...policy,
                                member_ids: event.target.checked
                                  ? [...policy.member_ids, item.account_id]
                                  : policy.member_ids.filter((value) => value !== item.account_id),
                              })
                            }
                          />
                          {item.display_name}
                        </label>
                      ))}
                    </fieldset>
                  )}
                </>
              )}
              <button
                className="primary"
                disabled={
                  busy ||
                  (policy.scope !== "private" && !home) ||
                  (policy.scope === "members" && !policy.member_ids.length)
                }
              >
                {busy ? "保存中…" : "保存可见范围"}
              </button>
            </form>
          )}
        </Modal>
      )}
    </>
  );
}
