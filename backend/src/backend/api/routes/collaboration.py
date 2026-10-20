from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.hub_schemas import (
    AssignmentFeedback,
    AssignmentInput,
    AssignmentItem,
    AssignmentOut,
    HouseholdInput,
    ObjectLinkInput,
)
from backend.api.routes.documents import material_owned
from backend.api.routes.households import participant
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.household_models import (
    HouseholdParticipant,
    HouseholdProfile,
    Notification,
    Pet,
)
from backend.db.models import Todo, utcnow
from backend.features.sharing.access import visible_condition

router = APIRouter(
    prefix="/api/collaboration", tags=["跨系统协作"], responses=ERROR_RESPONSES
)


def assignment_out(todo):
    return AssignmentOut(
        todo_id=todo.id,
        household_id=todo.household_id,
        assignee_id=todo.assignee_id,
        status=todo.assignment_status,
        note=todo.assignment_note or "",
    )


@router.get("/assignments", response_model=list[AssignmentItem])
def assignments(user: Principal, session: DB):
    rows = session.scalars(
        select(Todo)
        .where(
            visible_condition(Todo, user.id),
            Todo.household_id.is_not(None),
        )
        .order_by(Todo.updated_at.desc())
    )
    return [
        AssignmentItem(
            **assignment_out(row).model_dump(), title=row.title, owner_id=row.owner_id
        )
        for row in rows
    ]


@router.post("/todos/{todo_id}/assign", response_model=AssignmentOut)
def assign(todo_id: UUID, body: AssignmentInput, user: Principal, session: DB):
    participant(session, user, body.household_id)
    assignee = session.scalar(
        select(HouseholdParticipant).where(
            HouseholdParticipant.household_id == body.household_id,
            HouseholdParticipant.account_id == body.assignee_id,
            HouseholdParticipant.status == "active",
        )
    )
    todo = session.scalar(
        select(Todo)
        .where(Todo.id == todo_id, visible_condition(Todo, user.id))
        .with_for_update()
    )
    if todo is None or assignee is None:
        raise APIError(404, "ASSIGNMENT_TARGET_NOT_FOUND", "待办或家庭成员不存在")
    todo.household_id = body.household_id
    todo.assignee_id = body.assignee_id
    todo.assignment_status = "assigned"
    todo.assignment_note = None
    session.add(
        Notification(
            recipient_id=body.assignee_id,
            household_id=body.household_id,
            kind="todo_assignment",
            title="新的家庭任务",
            message=todo.title,
        )
    )
    from backend.api.routes.sharing import SharingSettings, put_settings

    put_settings(
        "todo",
        todo.id,
        SharingSettings(
            scope="members",
            household_id=body.household_id,
            member_ids=[body.assignee_id],
        ),
        user,
        session,
    )
    return assignment_out(todo)


@router.post("/todos/{todo_id}/feedback", response_model=AssignmentOut)
def feedback(todo_id: UUID, body: AssignmentFeedback, user: Principal, session: DB):
    todo = session.scalar(
        select(Todo)
        .where(
            Todo.id == todo_id,
            visible_condition(Todo, user.id),
            Todo.assignment_status == "assigned",
        )
        .with_for_update()
    )
    if todo is None:
        raise APIError(404, "ASSIGNMENT_NOT_FOUND", "指派不存在或已处理")
    todo.assignment_status = body.status
    todo.assignment_note = body.note or None
    if body.status == "completed":
        todo.status = "completed"
        todo.completed_at = utcnow()
    session.add(
        Notification(
            recipient_id=todo.owner_id,
            household_id=todo.household_id,
            kind="assignment_feedback",
            title="家庭任务已反馈",
            message=f"{todo.title}：{'已完成' if body.status == 'completed' else '已拒绝'}",
        )
    )
    session.commit()
    return assignment_out(todo)


@router.post("/events/{event_id}/share")
def share_event(event_id: UUID, body: HouseholdInput, user: Principal, session: DB):
    from backend.api.routes.sharing import SharingSettings, put_settings

    put_settings(
        "event",
        event_id,
        SharingSettings(scope="household", household_id=body.household_id),
        user,
        session,
    )
    return {"id": event_id, "household_id": body.household_id}


@router.post("/documents/{material_id}/link")
def link_document(
    material_id: UUID, body: ObjectLinkInput, user: Principal, session: DB
):
    participant(session, user, body.household_id)
    model = HouseholdProfile if body.subject_type == "profile" else Pet
    if (
        session.scalar(
            select(model.id).where(
                model.id == body.subject_id, model.household_id == body.household_id
            )
        )
        is None
    ):
        raise APIError(404, "SUBJECT_NOT_FOUND", "关联对象不存在或无法访问")
    material = material_owned(session, user, material_id)
    material.subject_type = body.subject_type
    material.subject_id = body.subject_id
    session.commit()
    return {
        "id": material.id,
        "subject_type": material.subject_type,
        "subject_id": material.subject_id,
    }
