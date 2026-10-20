import json
from datetime import UTC, date, datetime, time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, MetaData, create_engine
from sqlalchemy.orm import Session

from backend.api.routes.hub import search
from backend.api.routes.hub_search_detail import search_mail_detail
from backend.core.security import APIError
from backend.db.document_models import DocumentFolder, DocumentMaterial
from backend.db.life_models import MealPlan, MedicalAppointment, PantryItem
from backend.db.models import (
    AssistantMessage,
    AssistantProfile,
    AssistantThread,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    Reminder,
    Todo,
)
from backend.db.parity_models import DailyDump
from backend.db.session import Base


def test_global_search_fields_links_literal_and_account_isolation():
    engine = create_engine(
        "sqlite://", json_serializer=lambda value: json.dumps(value, ensure_ascii=False)
    )
    metadata = MetaData()
    for table in Base.metadata.sorted_tables:
        copy = table.to_metadata(metadata)
        for constraint in list(copy.constraints):
            if isinstance(constraint, CheckConstraint) and "::" in str(
                constraint.sqltext
            ):
                copy.constraints.remove(constraint)
    metadata.create_all(engine)
    user = SimpleNamespace(timezone="Asia/Shanghai", id=uuid4())
    stranger = SimpleNamespace(timezone="Asia/Shanghai", id=uuid4())
    with Session(engine) as session:
        check_search(session, user, stranger)


def check_search(session, user, stranger):
    meal = MealPlan(
        owner_id=user.id,
        title="周末晚餐",
        schedule_text="三个人",
        dish="炖牛肉",
        meal_date=date(2026, 9, 20),
        preferences=[{"label": "花生过敏"}],
        notes="少盐",
        ingredients=[{"name": "土豆"}],
    )
    checklist = Checklist(owner_id=user.id, title="采购")
    thread = AssistantThread(owner_id=user.id)
    dump = DailyDump(
        owner_id=user.id, source_text="明天寄快递", candidates=[{"title": "邮局"}]
    )
    pantry = PantryItem(owner_id=user.id, name="面粉", quantity=1, unit="袋")
    todo = Todo(
        owner_id=user.id,
        title="已买牛奶",
        description="低脂",
        status="completed",
        completed_at=datetime.now(UTC),
        create_key=uuid4(),
        create_fingerprint="test",
    )
    converted_todo = Todo(
        owner_id=user.id,
        title="去邮局寄快递",
        status="ongoing",
        create_key=uuid4(),
        create_fingerprint="daily-dump-test",
    )
    event = CalendarEvent(
        owner_id=user.id,
        title="出门",
        location="公园",
        timezone="Asia/Shanghai",
        starts_at=datetime(2026, 9, 21, 9, tzinfo=UTC),
        ends_at=datetime(2026, 9, 21, 10, tzinfo=UTC),
    )
    profile = AssistantProfile(owner_id=user.id, custom_instructions="回答用中文")
    session.add_all(
        [meal, checklist, thread, dump, pantry, todo, converted_todo, event, profile]
    )
    session.flush()
    message = AssistantMessage(
        thread_id=thread.id, role="user", content="查找字面%_符号"
    )
    session.add_all(
        [
            message,
            ChecklistItem(checklist_id=checklist.id, title="买酱油", position=0),
        ]
    )
    reminder = Reminder(
        owner_id=user.id,
        todo_id=todo.id,
        remind_at=datetime(2026, 9, 22, 9, tzinfo=UTC),
        timezone="Asia/Shanghai",
    )
    session.add(reminder)
    folder = DocumentFolder(owner_id=user.id, name="学校资料")
    session.add(folder)
    session.flush()
    material = DocumentMaterial(
        owner_id=user.id,
        folder_id=folder.id,
        name="家长会%_.pdf",
        media_type="application/pdf",
        size=3,
        content_hash="test-material",
        content=b"pdf",
        kind="file",
        status="uploaded",
    )
    session.add(material)
    session.commit()
    for term in ["家长会", ".pdf", "学校资料", "%_"]:
        result = search(user, session, term).items
        assert any(
            item.kind == "document"
            and item.id == material.id
            and item.url == f"/documents?folder={folder.id}#material-{material.id}"
            for item in result
        )
        assert search(stranger, session, term).items == []
    material.folder_id = None
    session.flush()
    assert (
        next(
            item
            for item in search(user, session, "家长会").items
            if item.kind == "document"
        ).url
        == f"/documents?folder=#material-{material.id}"
    )
    material.folder_id = folder.id
    session.flush()
    assert any(
        item.kind == "folder"
        and item.url == f"/documents?folder={folder.id}#directory-{folder.id}"
        for item in search(user, session, "学校资料").items
    )
    for term in [
        "周末晚餐",
        "三个人",
        "炖牛肉",
        "2026-09-20",
        "花生过敏",
        "少盐",
        "土豆",
    ]:
        result = search(user, session, term).items
        assert any(
            item.kind == "meal"
            and item.url == f"/meals/{meal.id}"
            and item.title == "周末晚餐"
            for item in result
        )
    assert any(item.id == meal.id for item in search(user, session, "周未晚餐").items)
    assert any(item.id == meal.id for item in search(user, session, "周末 晚餐").items)
    assert search(stranger, session, "周未晚餐").items == []
    assert search(user, session, "买酱油").items[0].id == checklist.id
    assert search(user, session, "面粉").items[0].url == "/meals/settings"
    assert search(user, session, "明天寄快递").items == []
    assert search(user, session, "邮局").items[0].id == converted_todo.id
    assert search(user, session, "查找字面").items == []
    assert search(user, session, "低脂").items[0].url == f"/todos/{todo.id}/edit"
    assert search(user, session, "2026-09-21").items[0].id == event.id
    assert search(user, session, "2026-09-22").items[0].url == f"/todos/{todo.id}/edit"
    assert search(user, session, "回答用中文").items[0].kind == "assistant_profile"
    cancelled_event = CalendarEvent(
        owner_id=user.id,
        title="已删除的体检日程",
        timezone="Asia/Shanghai",
        starts_at=datetime(2026, 9, 23, 9, tzinfo=UTC),
        ends_at=datetime(2026, 9, 23, 10, tzinfo=UTC),
        status="cancelled",
    )
    session.add(cancelled_event)
    session.flush()
    session.add(
        MedicalAppointment(
            owner_id=user.id,
            patient_name="已删除的体检预约",
            provider_name="医院",
            service_type="体检",
            scheduled_date=date(2026, 9, 23),
            scheduled_time=time(9),
            status="cancelled",
            event_id=cancelled_event.id,
        )
    )
    session.flush()
    assert search(user, session, "已删除的体检").items == []
    session.add(
        MedicalAppointment(
            owner_id=user.id,
            patient_name="未确认即删除的预约",
            provider_name="医院",
            service_type="体检",
            scheduled_date=date(2026, 9, 24),
            scheduled_time=time(9),
            status="cancelled",
        )
    )
    session.flush()
    assert any(item.id == event.id for item in search(user, session, "出门").items)
    for term in [
        "低脂",
        "2026-09-21",
        "2026-09-22",
        "回答用中文",
        "晚餐",
        "酱油",
        "面粉",
        "邮局",
        "%_",
    ]:
        assert search(stranger, session, term).items == []
    for kind, row, body in [
        ("assistant_message", message, message.content),
        ("daily_dump", dump, dump.source_text),
    ]:
        assert search_mail_detail(kind, row.id, user, session).body == body
        with pytest.raises(APIError) as error:
            search_mail_detail(kind, row.id, stranger, session)
        assert error.value.status == 404


def test_global_search_authenticated_cloud(cloud):
    from uuid import UUID

    from helpers import PASSWORD, register

    from backend.db.session import engine

    account, email = register(cloud)
    other, other_email = register(cloud)
    user = SimpleNamespace(timezone="Asia/Shanghai", id=UUID(account["id"]))
    stranger = SimpleNamespace(timezone="Asia/Shanghai", id=UUID(other["id"]))
    with Session(engine) as session:
        check_search(session, user, stranger)
    assert (
        cloud.post(
            "/api/auth/login", json={"email": email, "password": PASSWORD}
        ).status_code
        == 200
    )
    for term, kind in [
        ("花生过敏", "meal"),
        ("邮局", "todo"),
        ("回答用中文", "assistant_profile"),
    ]:
        response = cloud.get("/api/hub/search", params={"q": term})
        assert response.status_code == 200
        result = next(item for item in response.json()["items"] if item["kind"] == kind)
        if kind == "assistant_message":
            detail = cloud.get(f"/api/hub/search/{kind}/{result['id']}")
            assert detail.status_code == 200 and detail.json()["body"]
    assert cloud.get("/api/hub/search", params={"q": "查找字面"}).json()["items"] == []
    from sqlalchemy import select

    with Session(engine) as session:
        message_id = str(
            session.scalar(
                select(AssistantMessage.id)
                .join(AssistantThread)
                .where(AssistantThread.owner_id == user.id)
            )
        )
    # Switch the real Cookie session before checking private data.
    cloud.post("/api/auth/logout")
    cloud.post("/api/auth/login", json={"email": other_email, "password": PASSWORD})
    assert (
        cloud.get(f"/api/hub/search/assistant_message/{message_id}").status_code == 404
    )
    assert cloud.get("/api/hub/search", params={"q": "周末晚餐"}).json()["items"] == []
    cloud.post("/api/auth/logout")
    assert cloud.get("/api/hub/search", params={"q": "周末晚餐"}).status_code == 401
