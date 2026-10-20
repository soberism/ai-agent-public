from fastapi import APIRouter, Query
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.dialects.postgresql import JSONB

from backend.api.hub_schemas import (
    HubSummary,
    SearchItem,
    SearchResult,
)
from backend.api.routes.hub_search_detail import router as detail_router
from backend.api.routes.hub_search_materials import search_materials
from backend.api.routes.hub_search_patterns import search_patterns
from backend.api.routes.hub_search_sources import SOURCES
from backend.api.routes.hub_search_voice import search_voice
from backend.api.routes.mail import capabilities
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.cross_system_models import EmailDelivery, MailImport, VoiceMemo
from backend.db.document_models import (
    DocumentReviewItem,
)
from backend.db.household_models import Household, HouseholdParticipant
from backend.db.life_models import MealPlan, MedicalAppointment
from backend.db.models import (
    AssistantMemory,
    AssistantProfile,
    CalendarEvent,
    Checklist,
    ChecklistItem,
    Reminder,
    Todo,
)
from backend.features.sharing.access import visible_condition

router = APIRouter(prefix="/api/hub", tags=["跨系统入口"], responses=ERROR_RESPONSES)

router.include_router(detail_router)


@router.get("/search", response_model=SearchResult)
def search(user: Principal, session: DB, q: str = Query(min_length=1, max_length=100)):
    query = q.strip()
    if not query:
        raise APIError(422, "INVALID_SEARCH", "请输入搜索内容")
    terms = search_patterns(query)
    households = select(HouseholdParticipant.household_id).where(
        HouseholdParticipant.account_id == user.id,
        HouseholdParticipant.status == "active",
    )
    # ponytail: 按类直接查询适合当前小规模数据，数据增长后改为分类分页和全文索引。
    values = []
    for model, kind, title, fields, url in SOURCES:
        if model is Household:
            scope = model.id.in_(households)
        elif model not in (AssistantMemory, MailImport, EmailDelivery) and hasattr(
            model, "owner_id"
        ):
            scope = visible_condition(model, user.id)
        elif hasattr(model, "owner_id"):
            scope = model.owner_id == user.id
        else:
            scope = model.household_id.in_(households)
        if model is MedicalAppointment:
            scope &= model.status != "cancelled"
        elif model is CalendarEvent:
            scope &= ~model.id.in_(
                select(MedicalAppointment.event_id).where(
                    MedicalAppointment.status == "cancelled",
                    MedicalAppointment.event_id.is_not(None),
                )
            )
        matches = [
            cast(
                cast(getattr(model, field), JSONB)
                if field in ("ingredients", "preferences", "candidates", "items")
                and session.get_bind().dialect.name == "postgresql"
                else getattr(model, field),
                String,
            ).ilike(pattern, escape="\\")
            for field in fields
            for pattern in terms
        ]
        if model is Checklist:
            matches.append(
                model.id.in_(
                    select(ChecklistItem.checklist_id).where(
                        or_(
                            *(
                                ChecklistItem.title.ilike(pattern, escape="\\")
                                for pattern in terms
                            )
                        )
                    )
                )
            )
        for row in session.scalars(
            select(model)
            .where(scope, or_(*matches))
            .order_by(model.created_at.desc(), model.id)
        ):
            detail = " · ".join(
                str(getattr(row, field) or "") for field in fields if field != title
            )
            values.append(
                SearchItem(
                    id=row.id,
                    kind=kind,
                    title=str(
                        getattr(row, title) or (row.dish if model is MealPlan else "")
                    )[:100],
                    detail=detail[:160],
                    url=url.format(id=row.id),
                )
            )
    for row, title in session.execute(
        select(Reminder, func.coalesce(Todo.title, CalendarEvent.title))
        .outerjoin(Todo, Reminder.todo_id == Todo.id)
        .outerjoin(CalendarEvent, Reminder.event_id == CalendarEvent.id)
        .where(
            visible_condition(Reminder, user.id),
            or_(
                *(Todo.title.ilike(pattern, escape="\\") for pattern in terms),
                *(CalendarEvent.title.ilike(pattern, escape="\\") for pattern in terms),
                *(
                    cast(Reminder.remind_at, String).ilike(pattern, escape="\\")
                    for pattern in terms
                ),
            ),
        )
        .order_by(Reminder.created_at.desc(), Reminder.id)
    ):
        values.append(
            SearchItem(
                id=row.id,
                kind="reminder",
                title=title,
                detail=str(row.remind_at),
                url=f"/todos/{row.todo_id}/edit"
                if row.todo_id
                else f"/calendar/{row.event_id}/edit",
            )
        )
    profile = session.scalar(
        select(AssistantProfile).where(
            AssistantProfile.owner_id == user.id,
            or_(
                *(
                    AssistantProfile.custom_instructions.ilike(pattern, escape="\\")
                    for pattern in terms
                )
            ),
        )
    )
    if profile is not None:
        values.append(
            SearchItem(
                id=user.id,
                kind="assistant_profile",
                title="AI 自定义偏好",
                detail=profile.custom_instructions[:160],
                url="/assistant/preferences",
            )
        )
    values.extend(search_voice(session, user, terms))
    values.extend(search_materials(session, user, terms))
    return SearchResult(items=values)


@router.get("/summary", response_model=HubSummary)
def summary(user: Principal, session: DB):
    pending_reviews = (
        session.scalar(
            select(func.count())
            .select_from(DocumentReviewItem)
            .where(
                visible_condition(DocumentReviewItem, user.id),
                DocumentReviewItem.status == "pending",
            )
        )
        or 0
    )
    pending_assignments = (
        session.scalar(
            select(func.count())
            .select_from(Todo)
            .where(
                visible_condition(Todo, user.id),
                Todo.assignee_id == user.id,
                Todo.assignment_status == "assigned",
                Todo.status == "ongoing",
            )
        )
        or 0
    )
    failed_emails = (
        session.scalar(
            select(func.count())
            .select_from(EmailDelivery)
            .where(EmailDelivery.owner_id == user.id, EmailDelivery.status == "failed")
        )
        or 0
    )
    mail = capabilities()
    connection_issues = int(not mail.smtp)

    def count(model, *conditions):
        return (
            session.scalar(select(func.count()).select_from(model).where(*conditions))
            or 0
        )

    return HubSummary(
        pending_reviews=pending_reviews,
        pending_assignments=pending_assignments,
        failed_emails=failed_emails,
        connection_issues=connection_issues,
        pending_voice_memos=count(
            VoiceMemo,
            visible_condition(VoiceMemo, user.id),
            VoiceMemo.status == "draft",
        ),
    )
