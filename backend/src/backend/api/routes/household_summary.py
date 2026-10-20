from uuid import UUID

from fastapi import APIRouter
from sqlalchemy import select

from backend.api.routes.household_deletion import router as deletion_router
from backend.api.routes.households import participant
from backend.core.security import DB, Principal
from backend.db.models import Todo
from backend.features.sharing.access import visible_condition

router = APIRouter(tags=["家庭汇总"])
router.include_router(deletion_router)


@router.get("/{household_id}/summary")
def household_summary(household_id: UUID, user: Principal, session: DB):
    participant(session, user, household_id)
    rows = session.scalars(
        select(Todo)
        .where(
            Todo.household_id == household_id,
            Todo.status == "ongoing",
            visible_condition(Todo, user.id),
        )
        .order_by(Todo.due_date.nulls_last())
        .limit(20)
    )
    return {
        "todos": [
            {
                "id": row.id,
                "title": row.title,
                "assignee_id": row.assignee_id,
                "due_date": row.due_date,
            }
            for row in rows
        ]
    }
