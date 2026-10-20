"""每条用例独立账号、业务对象、日期锚点及前置条件审计。"""

import json
from datetime import datetime
from pathlib import Path
from uuid import UUID
from zoneinfo import ZoneInfo

from eval_seed_family import seed_family
from eval_seed_rows import seed_row
from eval_seed_state import snapshot
from helpers import register
from sqlalchemy.orm import Session

from backend.core.security import settings
from backend.db.models import AssistantProfile, User
from backend.db.session import engine
from backend.features.assistant.rag import refresh_material

FIXTURE = Path(__file__).parent / "fixtures" / "assistant_eval_setup.json"
SETUPS = json.loads(FIXTURE.read_text())["cases"]


def dependencies():
    embedding = bool(
        settings.embedding_model
        and (settings.embedding_base_url or settings.transcription_base_url)
        and (
            settings.embedding_api_key.get_secret_value()
            or settings.transcription_api_key.get_secret_value()
        )
    )
    transcription = bool(
        settings.transcription_model
        and settings.transcription_base_url
        and settings.transcription_api_key.get_secret_value()
    )
    return {"embedding": embedding, "transcription": transcription}


def prepare(cloud, case):
    spec = SETUPS[case["id"]]
    cloud.cookies.clear()
    main, _ = register(cloud)
    cookies = dict(cloud.cookies)
    accounts = {"A": UUID(main["id"])}
    families = any(o["kind"] == "household" for o in spec["objects"])
    needs_other = (
        families
        or spec.get("access_case")
        or spec.get("invitee")
        or any(o.get("owner") == "B" for o in spec["objects"])
    )
    if needs_other:
        cloud.cookies.clear()
        other, _ = register(cloud)
        accounts["B"] = UUID(other["id"])
    if families and any(o.get("owner") == "B" for o in spec["objects"]):
        cloud.cookies.clear()
        third, _ = register(cloud)
        accounts["C"] = UUID(third["id"])
    cloud.cookies.clear()
    cloud.cookies.update(cookies)
    anchor = datetime.now(ZoneInfo("Asia/Shanghai")).date()
    available = dependencies()
    blockers = [
        f"{key}服务未配置"
        for key in set(spec.get("requires", []))
        if not available[key]
    ]
    seeded, guards, folders = [], [], {}
    with Session(engine) as db:
        users = {key: db.get(User, id) for key, id in accounts.items()}
        users["A"].nickname = "测试原昵称"
        users["A"].timezone = "Asia/Shanghai"
        db.add(
            AssistantProfile(
                owner_id=users["A"].id,
                custom_instructions=spec.get("instructions", ""),
                memory_enabled=True,
            )
        )
        objects = sorted(spec["objects"], key=lambda o: o["kind"] != "folder")
        for obj in objects:
            user = users[obj.get("owner", "A")]
            row = (
                seed_family(
                    db,
                    users,
                    {**obj, "invitee_only": spec.get("invitee", False)},
                    spec.get("access_case", False),
                )
                if obj["kind"] == "household"
                else seed_row(db, user, obj, anchor, folders)
            )
            if obj["kind"] == "folder":
                folders[(user.id, obj["title"])] = row.id
            if (
                obj["kind"] == "material"
                and not obj.get("deleted")
                and available["embedding"]
            ):
                refresh_material(db, row)
            seeded.append(
                {
                    "kind": obj["kind"],
                    "id": str(row.id),
                    "title": obj["title"],
                    "owner": obj.get("owner", "A"),
                    "deleted": obj.get("deleted", False),
                }
            )
            if obj.get("guard"):
                guards.append(str(row.id))
        # 单独的旁观记录不与请求目标同名，也不额外引入第二个家庭造成歧义。
        for key, user in users.items():
            row = seed_row(
                db,
                user,
                {"kind": "todo", "title": f"旁观事项{key}", "date": "+50"},
                anchor,
                folders,
            )
            guards.append(str(row.id))
        db.commit()
        state = snapshot(db, users)
        for item in seeded:
            if not item["deleted"]:
                assert any(item["id"] in values for values in state.values()), item
        if spec.get("access_case"):
            assert all(o["owner"] == "B" for o in seeded if o["id"] not in guards), (
                seeded
            )
        user_ids = {key: str(user.id) for key, user in users.items()}
    return {
        "setup_ready": not any(
            "不能合法预置" in note for note in spec.get("fixture_notes", [])
        ),
        "environment_ready": not blockers,
        "dependency_blockers": blockers,
        "fixture_notes": spec.get("fixture_notes", []),
        "anchor_date": anchor.isoformat(),
        "timezone": "Asia/Shanghai",
        "accounts": user_ids,
        "objects": seeded,
        "guard_ids": guards,
        "before": state,
    }


def current_state(setup):
    with Session(engine) as db:
        users = {
            key: db.get(User, UUID(value)) for key, value in setup["accounts"].items()
        }
        return snapshot(db, users)
