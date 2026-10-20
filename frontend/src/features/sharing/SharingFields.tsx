import { Select } from "../../shared/Select";
import type { SharingHousehold, SharingPolicy } from "./types";

export function SharingFields({
  policy,
  homes,
  change,
  disabled = false,
}: {
  policy: SharingPolicy;
  homes: SharingHousehold[];
  change: (policy: SharingPolicy) => void;
  disabled?: boolean;
}) {
  const home = homes.find((item) => item.id === policy.household_id);
  return (
    <fieldset className="stack sharing-fields" disabled={disabled}>
      <legend>可见范围</legend>
      <label>
        谁可以访问
        <Select
          value={policy.scope}
          onChange={(event) => {
            const scope = event.target.value as SharingPolicy["scope"];
            change({
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
      {policy.scope !== "private" && (
        <>
          <label>
            家庭
            <Select
              value={policy.household_id ?? ""}
              onChange={(event) =>
                change({ ...policy, household_id: event.target.value, member_ids: [] })
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
          {policy.scope === "members" && (
            <fieldset>
              <legend>选择成员</legend>
              {!home?.members.length && <p className="muted small">暂无可选成员</p>}
              {home?.members.map((item) => (
                <label className="check-row" key={item.account_id}>
                  <input
                    type="checkbox"
                    checked={policy.member_ids.includes(item.account_id)}
                    onChange={(event) =>
                      change({
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
      <p className="muted small">共享成员可以编辑和删除内容，可见范围仅创建者可以修改。</p>
    </fieldset>
  );
}
