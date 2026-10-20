"""准备可访问/不可访问家庭和待处理邀请，不能把注册账号当作共享授权。"""

from datetime import UTC, datetime, timedelta

from backend.db.household_models import Household, HouseholdParticipant


def seed_family(db, users, spec, access_case):
    owner_key = spec.get("owner", "A")
    member_key = "C" if owner_key == "B" else "B"
    current, other = users[owner_key], users[member_key]
    incoming = spec.get("incoming", False)
    member = spec.get("role") == "member"
    owner, guest = (other, current) if incoming or member else (current, other)
    home = Household(owner_id=owner.id, name=spec["title"])
    db.add(home)
    db.flush()
    for who, role, status, name in [
        (owner, "owner", "active", "测试创建者"),
        (
            guest,
            spec.get("member_role", "member"),
            "pending" if incoming else "active",
            spec.get("member_name", "小林"),
        ),
    ]:
        if spec.get("invitee_only") and who.id == guest.id:
            continue
        if access_case and who.id == users["A"].id:
            raise ValueError("越权用例不得把当前账号加入他人家庭")
        db.add(
            HouseholdParticipant(
                household_id=home.id,
                account_id=who.id,
                email=who.email,
                display_name=name,
                role=role,
                status=status,
                permissions=[],
                invited_by=owner.id,
                expires_at=datetime.now(UTC) + timedelta(days=7)
                if status == "pending"
                else None,
                accepted_at=datetime.now(UTC) if status == "active" else None,
            )
        )
    db.flush()
    return home
