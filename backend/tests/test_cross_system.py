from helpers import register


def test_search_mail_boundary_and_voice_memo(cloud):
    register(cloud)
    created = cloud.post("/api/planning/checklists", json={"title": "出行准备"})
    assert created.status_code == 201
    results = cloud.get("/api/hub/search", params={"q": "出行"}).json()["items"]
    assert results[0]["kind"] == "checklist"

    capabilities = cloud.get("/api/mail/capabilities").json()
    assert capabilities["third_party_calendar"] is False
    assert capabilities["notification_channels"] == ["email"]

    memo = cloud.post(
        "/api/assistant/voice-memos", json={"transcript": "明天下午整理行李"}
    ).json()
    converted = cloud.post(
        f"/api/assistant/voice-memos/{memo['id']}/convert",
        json={"target_type": "todo", "title": "整理行李"},
    )
    assert converted.status_code == 200
    assert converted.json()["status"] == "converted"
    replay = cloud.post(
        f"/api/assistant/voice-memos/{memo['id']}/convert",
        json={"target_type": "event", "title": "不应重复创建"},
    )
    assert replay.json()["target_id"] == converted.json()["target_id"]


def test_search_complete_results_literal_query_and_isolation(cloud):
    from uuid import UUID

    from sqlalchemy.orm import Session

    from backend.db.life_models import PantryItem
    from backend.db.models import Checklist, ChecklistItem
    from backend.db.session import engine

    user, _ = register(cloud)
    with Session(engine) as db:
        owner = UUID(user["id"])
        lists = [Checklist(owner_id=owner, title=f"搜索验证{i}") for i in range(35)]
        db.add_all(lists)
        db.flush()
        db.add(ChecklistItem(checklist_id=lists[0].id, title="字面%_匹配", position=0))
        db.add(PantryItem(owner_id=owner, name="搜索验证食材", quantity=1, unit="个"))
        db.add(
            ChecklistItem(checklist_id=lists[1].id, title="搜索验证商品", position=0)
        )
        db.commit()
    result = cloud.get("/api/hub/search", params={"q": "搜索验证"}).json()["items"]
    assert len([r for r in result if r["kind"] == "checklist"]) == 35
    assert {"pantry", "checklist"} <= {r["kind"] for r in result}
    result = cloud.get("/api/hub/search", params={"q": "%_"}).json()["items"]
    assert len(result) == 1 and result[0]["kind"] == "checklist"
    assert cloud.get("/api/hub/search", params={"q": "   "}).status_code == 422
    register(cloud)
    assert cloud.get("/api/hub/search", params={"q": "搜索验证"}).json()["items"] == []


def test_search_mail_detail_is_private(cloud):
    from uuid import UUID

    from sqlalchemy.orm import Session

    from backend.db.cross_system_models import EmailDelivery, MailImport
    from backend.db.session import engine

    user, _ = register(cloud)
    with Session(engine) as db:
        incoming = MailImport(
            owner_id=UUID(user["id"]),
            message_id="private-test",
            subject="测试来信",
            sender="demo@example.com",
            body="完整来信正文",
        )
        outgoing = EmailDelivery(
            owner_id=UUID(user["id"]),
            kind="manual",
            subject="测试通知",
            body="完整通知正文",
        )
        db.add_all([incoming, outgoing])
        db.commit()
        ids = {"mail": str(incoming.id), "email": str(outgoing.id)}
    for kind, mail_id in ids.items():
        response = cloud.get(f"/api/hub/search/{kind}/{mail_id}")
        assert response.status_code == 200
        assert response.json()["body"].startswith("完整")
    register(cloud)
    for kind, mail_id in ids.items():
        assert cloud.get(f"/api/hub/search/{kind}/{mail_id}").status_code == 404
    cloud.post("/api/auth/logout")
    assert cloud.get(f"/api/hub/search/mail/{ids['mail']}").status_code == 401
