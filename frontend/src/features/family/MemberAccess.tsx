import { useSession } from "../../app/session";
import { RemoveMemberButton } from "./RemoveMemberButton";
import { Select } from "../../shared/Select";
import { useState } from "react";
import { Avatar } from "../../shared/Avatar";
import type { HouseholdMember } from "./types";

export function MemberAccess({
  householdId,
  items,
  save,
  canManage,
  canRemove,
}: {
  householdId: string;
  items: HouseholdMember[];
  canManage: boolean;
  canRemove: boolean;
  save: (memberId: string, body: Record<string, unknown>) => Promise<boolean>;
}) {
  const { user } = useSession();
  if (!items.length) return <p className="muted">暂无成员</p>;
  return (
    <div className="member-access-list">
      {items.map((member) => (
        <MemberAccessRow
          key={member.id}
          member={member}
          householdId={householdId}
          save={save}
          canManage={canManage}
          canRemove={canRemove && member.account_id !== user?.id}
        />
      ))}
    </div>
  );
}

function MemberAccessRow({
  householdId,
  member,
  save,
  canManage,
  canRemove,
}: {
  householdId: string;
  member: HouseholdMember;
  canManage: boolean;
  canRemove: boolean;
  save: (memberId: string, body: Record<string, unknown>) => Promise<boolean>;
}) {
  const [role, setRole] = useState(member.role);
  const owner = member.role === "owner";
  return (
    <article className="member-access-row">
      <div className="member-identity">
        <Avatar
          id={member.account_id ?? member.id}
          name={member.display_name}
          email={member.email}
        />
        <div>
          <strong>{member.display_name}</strong>
          <small>{member.email || "无登录邮箱"}</small>
        </div>
      </div>
      {owner || !canManage ? (
        <p className="family-owner-role">
          {owner ? "家庭创建者" : member.role === "admin" ? "管理员" : "家庭成员"}
        </p>
      ) : (
        <label>
          角色
          <Select value={role} onChange={(event) => setRole(event.target.value)}>
            <option value="admin">管理员</option>
            <option value="member">家庭成员</option>
          </Select>
        </label>
      )}
      {!owner && canRemove && (
        <div className="member-actions">
          {canManage && <button onClick={() => void save(member.id, { role })}>保存角色</button>}
          <RemoveMemberButton householdId={householdId} memberId={member.id} save={save} />
        </div>
      )}
    </article>
  );
}
