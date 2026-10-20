import { ConfirmButton } from "../../shared/ConfirmButton";
import { InviteForm } from "./FamilyForms";
import { MemberAccess } from "./MemberAccess";
import type { HouseholdDetail } from "./types";

const roleLabel: Record<string, string> = {
  owner: "家庭创建者",
  admin: "管理员",
  member: "家庭成员",
};

export function FamilyContent({
  detail,
  submit,
  saveMember,
  onDelete,
  onLeave,
}: {
  detail: HouseholdDetail;
  onDelete: () => Promise<void>;
  onLeave: () => Promise<void>;
  submit: (path: string, body: Record<string, string | null>) => Promise<boolean>;
  saveMember: (memberId: string, body: Record<string, unknown>) => Promise<boolean>;
}) {
  const canManage = detail.role === "owner";
  const canManageMembers = canManage || detail.role === "admin";
  return (
    <>
      <section className="feature-hero purple-surface">
        <div className="family-hero-heading">
          <h2>{detail.name}</h2>
          {canManage ? (
            <ConfirmButton
              title="删除家庭"
              className="text-button family-delete"
              confirmLabel="删除家庭"
              onConfirm={onDelete}
              message={`删除“${detail.name}”将解除成员关系、取消邀请并撤回该家庭共享。各账号创建的待办、日程、文件等业务内容保留，家庭托管档案和宠物资料将删除。此操作无法撤销。`}
            >
              删除家庭
            </ConfirmButton>
          ) : (
            <ConfirmButton
              title="退出家庭"
              className="text-button family-delete"
              confirmLabel="退出家庭"
              onConfirm={onLeave}
              message={`退出“${detail.name}”后将失去该家庭的共享访问权，你创建的内容会保留，并停止向该家庭共享。再次加入需要重新接受邀请。`}
            >
              退出家庭
            </ConfirmButton>
          )}
        </div>
        <p>
          {detail.member_count} 位成员 · 我的角色：{roleLabel[detail.role] ?? detail.role}
        </p>
      </section>
      <section className="family-group" aria-labelledby="family-members-title">
        <h2 id="family-members-title">家庭成员</h2>
        <div className="feature-card family-members-card">
          <h3>成员列表</h3>
          <p className="muted small">
            创建者和管理员可以邀请、移出成员；只有创建者可以修改角色。业务内容默认仅自己可见，可在各模块设置共享。
          </p>
          <MemberAccess
            householdId={detail.id}
            items={detail.members}
            save={saveMember}
            canManage={canManage}
            canRemove={canManageMembers}
          />
          {canManageMembers && (
            <>
              <details className="family-disclosure">
                <summary>
                  <span>邀请成员</span>
                </summary>
                <p className="muted small">邀请通过站内通知处理。加入家庭不会自动公开个人内容。</p>
                <InviteForm householdId={detail.id} submit={submit} />
              </details>
              <details className="family-disclosure">
                <summary>
                  <span>已发出邀请</span>
                  <span className="family-invite-count">{detail.invitations.length}</span>
                </summary>
                {!detail.invitations.length ? (
                  <p className="muted family-empty">暂无邀请</p>
                ) : (
                  <ul className="plain-list">
                    {detail.invitations.map((item) => (
                      <li key={item.id}>
                        {item.email} · {roleLabel[item.role] ?? item.role} ·{" "}
                        {item.status === "pending"
                          ? "待接受"
                          : item.status === "accepted"
                            ? "已接受"
                            : item.status === "rejected"
                              ? "已拒绝"
                              : "已失效"}
                      </li>
                    ))}
                  </ul>
                )}
              </details>
            </>
          )}
        </div>
      </section>
    </>
  );
}
