"""True Cookie/Redis/PostgreSQL sharing checks; dedicated cloud test DB only."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from helpers import create, family_accounts, login_as
from sqlalchemy.orm import Session

from backend.api.routes import assistant
from backend.db.cross_system_models import VoiceMemo
from backend.db.document_models import DocumentFolder, DocumentMaterial
from backend.db.household_models import Contact, ContactGroup
from backend.db.life_models import (
    LifePreference,
    MealPlan,
    MedicalAppointment,
    PantryItem,
)
from backend.db.models import CalendarEvent, Checklist, ChecklistItem
from backend.db.parity_models import DailyDump
from backend.db.session import engine
from backend.features.assistant.graph import Intent


def test_shared_items_search_crud_ai_and_revocation(cloud, monkeypatch):
    _owner, own_cookie, home, member, member_cookie, helper, helper_cookie = (
        family_accounts(cloud)
    )
    login_as(cloud, own_cookie)
    todo = create(cloud, title="权限测试待办")
    path = f"/api/sharing/todo/{todo['id']}"
    login_as(cloud, member_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 404
    assert cloud.get(path).status_code == 404
    login_as(cloud, own_cookie)
    policy = {"scope": "household", "household_id": home["id"], "member_ids": []}
    assert cloud.put(path, json=policy).status_code == 200
    login_as(cloud, helper_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 200
    login_as(cloud, member_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 200
    assert any(x["id"] == todo["id"] for x in cloud.get("/api/todos").json()["items"])
    assert any(
        x["id"] == todo["id"]
        for x in cloud.get("/api/hub/search", params={"q": "权限测试"}).json()["items"]
    )
    assert (
        cloud.patch(
            f"/api/todos/{todo['id']}", json={"title": "权限测试修改"}
        ).status_code
        == 200
    )
    thread = cloud.post("/api/assistant/threads", json={"fresh": True}).json()[
        "thread_id"
    ]
    monkeypatch.setattr(assistant, "interpret", lambda *_: Intent(action="query_todos"))
    reply = cloud.post(
        "/api/assistant/messages", json={"thread_id": thread, "message": "查询待办"}
    )
    assert reply.status_code == 200, reply.text
    assert any(x["id"] == todo["id"] for x in reply.json()["items"])
    monkeypatch.setattr(
        assistant,
        "interpret",
        lambda *_: Intent(action="complete_todo", title="权限测试修改"),
    )
    pending = cloud.post(
        "/api/assistant/messages", json={"thread_id": thread, "message": "完成待办"}
    )
    assert pending.json()["kind"] == "confirm", pending.text
    token = pending.json()["action_token"]
    login_as(cloud, own_cookie)
    assert cloud.put(path, json={"scope": "private"}).status_code == 200
    login_as(cloud, member_cookie)
    assert (
        cloud.post(f"/api/assistant/actions/{token}/confirm", json={}).status_code
        == 404
    )
    contexts = []

    def inspect_context(*args):
        contexts.append(args)
        return Intent(action="query_todos", reference_index=1)

    monkeypatch.setattr(assistant, "interpret", inspect_context)
    revoked = cloud.post(
        "/api/assistant/messages", json={"thread_id": thread, "message": "查看第一条"}
    )
    assert revoked.status_code == 200, revoked.text
    assert revoked.json()["kind"] == "clarify"
    assert revoked.json()["items"] == []
    assert "权限测试修改" not in str(contexts[0][1:3])
    assert (
        cloud.patch(f"/api/todos/{todo['id']}", json={"title": "不应修改"}).status_code
        == 404
    )
    login_as(cloud, own_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").json()["status"] == "ongoing"
    assert (
        cloud.put(
            path,
            json={
                "scope": "members",
                "household_id": home["id"],
                "member_ids": [helper["id"]],
            },
        ).status_code
        == 200
    )
    login_as(cloud, helper_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 200
    # Shared users cannot change visibility or manage the family.
    assert cloud.put(path, json=policy).status_code == 403
    assert (
        cloud.post(
            f"/api/households/{home['id']}/invitations",
            json={"email": "other@example.com", "role": "member"},
        ).status_code
        == 404
    )
    login_as(cloud, own_cookie)
    assert cloud.put(path, json=policy).status_code == 200
    members = cloud.get(f"/api/households/{home['id']}").json()["members"]
    removed_id = next(x["id"] for x in members if x["account_id"] == member["id"])
    assert (
        cloud.patch(
            f"/api/households/{home['id']}/members/{removed_id}",
            json={"status": "removed"},
        ).status_code
        == 200
    )
    login_as(cloud, member_cookie)
    assert cloud.get(f"/api/todos/{todo['id']}").status_code == 404
    assert not any(
        x["id"] == todo["id"]
        for x in cloud.get("/api/hub/search", params={"q": "权限测试"}).json()["items"]
    )


def test_all_business_kinds_list_search_and_attachment(cloud):
    owner, own_cookie, home, member, member_cookie, _, _ = family_accounts(cloud)
    owner_id = UUID(owner["id"])
    now = datetime.now(UTC)
    rows = [
        (
            "event",
            CalendarEvent(
                owner_id=owner_id,
                title="共享验证日程",
                timezone="Asia/Shanghai",
                starts_at=now,
                ends_at=now + timedelta(hours=1),
            ),
        ),
        ("checklist", Checklist(owner_id=owner_id, title="共享验证清单")),
        ("folder", DocumentFolder(owner_id=owner_id, name="共享验证目录")),
        (
            "material",
            DocumentMaterial(
                owner_id=owner_id,
                name="共享验证文件.txt",
                status="uploaded",
                kind="file",
                media_type="text/plain",
                size=4,
                content_hash=uuid4().hex,
                content=b"test",
            ),
        ),
        ("meal", MealPlan(owner_id=owner_id, title="共享验证餐食", dish="米饭")),
        (
            "voice_memo",
            VoiceMemo(
                owner_id=owner_id,
                transcript="共享验证录音",
                audio=b"audio",
                mime_type="audio/webm",
            ),
        ),
        ("daily_dump", DailyDump(owner_id=owner_id, source_text="共享验证随手记")),
        ("contact", Contact(owner_id=owner_id, name="共享验证联系人")),
        ("contact_group", ContactGroup(owner_id=owner_id, name="共享验证分组")),
        (
            "pantry",
            PantryItem(owner_id=owner_id, name="共享验证食材", quantity=1, unit="份"),
        ),
        (
            "preference",
            LifePreference(owner_id=owner_id, label="共享验证偏好", kind="diet"),
        ),
        (
            "appointment",
            MedicalAppointment(
                owner_id=owner_id,
                patient_name="共享验证患者",
                provider_name="测试机构",
                service_type="体检",
                scheduled_date=now.astimezone(ZoneInfo("Asia/Shanghai")).date(),
                scheduled_time=now.time().replace(tzinfo=None),
            ),
        ),
    ]
    with Session(engine) as db:
        db.add_all([row for _, row in rows])
        db.flush()
        ids = {kind: str(row.id) for kind, row in rows}
        dict(rows)["material"].folder_id = UUID(ids["folder"])
        db.add(
            ChecklistItem(
                checklist_id=UUID(ids["checklist"]), title="共享验证子项", position=0
            )
        )
        db.commit()
    login_as(cloud, own_cookie)
    for kind, resource_id in ids.items():
        if kind == "folder":
            continue
        response = cloud.put(
            f"/api/sharing/{kind}/{resource_id}",
            json={
                "scope": "members",
                "household_id": home["id"],
                "member_ids": [member["id"]],
            },
        )
        assert response.status_code == 200, (kind, response.text)
    login_as(cloud, member_cookie)
    for kind, resource_id in ids.items():
        assert cloud.get(f"/api/sharing/{kind}/{resource_id}").status_code == (
            404 if kind == "folder" else 200
        ), kind
    search = cloud.get("/api/hub/search", params={"q": "共享验证"})
    assert search.status_code == 200, search.text
    found = {item["id"] for item in search.json()["items"]}
    assert set(ids.values()) - {ids["daily_dump"]} <= found
    assert ids["daily_dump"] not in found
    assert (
        cloud.get(f"/api/planning/checklists/{ids['checklist']}").json()["items"][0][
            "title"
        ]
        == "共享验证子项"
    )
    assert (
        cloud.get(f"/api/documents/materials/{ids['material']}/content").status_code
        == 200
    )
    assert (
        cloud.get(f"/api/assistant/voice-memos/{ids['voice_memo']}/audio").status_code
        == 200
    )
    for path, kind, key in [
        ("/api/calendar/events", "event", "items"),
        ("/api/life/meal-plans", "meal", "items"),
        ("/api/assistant/voice-memos", "voice_memo", None),
        ("/api/documents/materials", "material", "items"),
    ]:
        response = cloud.get(
            path,
            params={
                "date_from": now.astimezone(ZoneInfo("Asia/Shanghai"))
                .date()
                .isoformat(),
                "date_to": now.astimezone(ZoneInfo("Asia/Shanghai")).date().isoformat(),
            }
            if kind == "event"
            else {},
        )
        assert response.status_code == 200, (path, response.text)
        items = response.json()[key] if key else response.json()
        assert any(item["id"] == ids[kind] for item in items), kind
