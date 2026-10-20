from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import func, select

from backend.api.planning_schemas import (
    ChecklistBulk,
    ChecklistCreate,
    ChecklistItemCreate,
    ChecklistItemPatch,
    ChecklistList,
    ChecklistOut,
    ChecklistShareInput,
    ChecklistWithItemsCreate,
)
from backend.api.routes.planning_checklists import (
    checklist_output,
    owned_checklist,
    owned_item,
)
from backend.api.routes.planning_reminders import router as reminders_router
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, Principal
from backend.db.models import (
    Checklist,
    ChecklistItem,
    utcnow,
)
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(
    prefix="/api/planning", tags=["计划工作流"], responses=ERROR_RESPONSES
)


@router.get("/checklists", response_model=ChecklistList)
def list_checklists(user: Principal, session: DB):
    rows = session.scalars(
        select(Checklist)
        .where(visible_condition(Checklist, user.id))
        .order_by(Checklist.pinned.desc(), Checklist.updated_at.desc(), Checklist.id)
    )
    return ChecklistList(items=[checklist_output(session, row) for row in rows])


@router.post("/checklists", response_model=ChecklistOut, status_code=201)
def create_checklist(body: ChecklistWithItemsCreate, user: Principal, session: DB):
    checklist = Checklist(owner_id=user.id, title=body.title)
    session.add(checklist)
    session.flush()
    session.add_all(
        [
            ChecklistItem(checklist_id=checklist.id, title=title, position=index)
            for index, title in enumerate(body.items)
        ]
    )
    session.commit()
    return checklist_output(session, checklist)


@router.get("/checklists/{checklist_id}", response_model=ChecklistOut)
def get_checklist(checklist_id: UUID, user: Principal, session: DB):
    value = owned_checklist(session, user, checklist_id)
    return checklist_output(session, value)


@router.post("/checklists/{checklist_id}/pin", response_model=ChecklistOut)
def pin_checklist(checklist_id: UUID, user: Principal, session: DB):
    value = owned_checklist(session, user, checklist_id, True)
    value.pinned = not value.pinned
    value.updated_at = utcnow()
    session.commit()
    return checklist_output(session, value)


@router.post("/checklists/{checklist_id}/bulk", response_model=ChecklistOut)
def bulk_checklist(
    checklist_id: UUID, body: ChecklistBulk, user: Principal, session: DB
):
    value = owned_checklist(session, user, checklist_id, True)
    for item in session.scalars(
        select(ChecklistItem).where(ChecklistItem.checklist_id == value.id)
    ):
        item.completed = body.completed
    value.updated_at = utcnow()
    session.commit()
    return checklist_output(session, value)


@router.post("/checklists/{checklist_id}/share", response_model=ChecklistOut)
def share_checklist(
    checklist_id: UUID, body: ChecklistShareInput, user: Principal, session: DB
):
    from backend.api.routes.sharing import SharingSettings, put_settings

    put_settings(
        "checklist",
        checklist_id,
        SharingSettings(scope="household", household_id=body.household_id),
        user,
        session,
    )
    return checklist_output(session, owned_checklist(session, user, checklist_id))


@router.patch("/checklists/{checklist_id}", response_model=ChecklistOut)
def rename_checklist(
    checklist_id: UUID, body: ChecklistCreate, user: Principal, session: DB
):
    checklist = owned_checklist(session, user, checklist_id, True)
    checklist.title = body.title
    checklist.updated_at = utcnow()
    session.commit()
    return checklist_output(session, checklist)


@router.post(
    "/checklists/{checklist_id}/duplicate", response_model=ChecklistOut, status_code=201
)
def duplicate_checklist(checklist_id: UUID, user: Principal, session: DB):
    source = owned_checklist(session, user, checklist_id)
    items = list(
        session.scalars(
            select(ChecklistItem)
            .where(ChecklistItem.checklist_id == source.id)
            .order_by(ChecklistItem.position, ChecklistItem.id)
        )
    )
    copy = Checklist(owner_id=user.id, title=f"{source.title[:11]}（副本）")
    session.add(copy)
    session.flush()
    session.add_all(
        [
            ChecklistItem(checklist_id=copy.id, title=item.title, position=index)
            for index, item in enumerate(items)
        ]
    )
    session.commit()
    return checklist_output(session, copy)


@router.delete("/checklists/{checklist_id}", status_code=204)
def delete_checklist(checklist_id: UUID, user: Principal, session: DB):
    delete_resource(session, owned_checklist(session, user, checklist_id, True))
    session.commit()


@router.post(
    "/checklists/{checklist_id}/items", response_model=ChecklistOut, status_code=201
)
def add_item(
    checklist_id: UUID, body: ChecklistItemCreate, user: Principal, session: DB
):
    checklist = owned_checklist(session, user, checklist_id, True)
    position = session.scalar(
        select(func.coalesce(func.min(ChecklistItem.position), 1)).where(
            ChecklistItem.checklist_id == checklist.id
        )
    )
    session.add(
        ChecklistItem(
            checklist_id=checklist.id, title=body.title, position=position - 1
        )
    )
    checklist.updated_at = utcnow()
    session.commit()
    return checklist_output(session, checklist)


@router.patch("/checklists/{checklist_id}/items/{item_id}", response_model=ChecklistOut)
def update_item(
    checklist_id: UUID,
    item_id: UUID,
    body: ChecklistItemPatch,
    user: Principal,
    session: DB,
):
    checklist, item = owned_item(session, user, checklist_id, item_id)
    item.completed = body.completed
    checklist.updated_at = utcnow()
    session.commit()
    return checklist_output(session, checklist)


@router.delete(
    "/checklists/{checklist_id}/items/{item_id}", response_model=ChecklistOut
)
def delete_item(checklist_id: UUID, item_id: UUID, user: Principal, session: DB):
    checklist, item = owned_item(session, user, checklist_id, item_id)
    delete_resource(session, item)
    checklist.updated_at = utcnow()
    session.commit()
    return checklist_output(session, checklist)


router.include_router(reminders_router)
