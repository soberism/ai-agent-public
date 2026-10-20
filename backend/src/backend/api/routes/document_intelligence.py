import base64
from uuid import UUID

from fastapi import APIRouter, Query
from openai import OpenAI, OpenAIError
from sqlalchemy import or_, select

from backend.api.hub_schemas import DocumentSearchItem
from backend.api.routes.documents import material_owned
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal, settings
from backend.db.document_models import DocumentMaterial, DocumentReviewItem
from backend.db.household_models import Household, HouseholdProfile, Pet
from backend.db.models import CalendarEvent, Todo, utcnow
from backend.features.documents.extraction import extract_candidates
from backend.features.sharing.access import visible_condition

router = APIRouter(
    prefix="/api/documents", tags=["文档智能"], responses=ERROR_RESPONSES
)


@router.get("/search", response_model=list[DocumentSearchItem])
def search(user: Principal, session: DB, q: str = Query(min_length=1, max_length=100)):
    term = f"%{q.strip()}%"
    rows = session.scalars(
        select(DocumentMaterial)
        .where(
            visible_condition(DocumentMaterial, user.id),
            or_(
                DocumentMaterial.name.ilike(term),
                DocumentMaterial.extracted_text.ilike(term),
            ),
        )
        .order_by(DocumentMaterial.created_at.desc())
        .limit(30)
    )
    return [
        DocumentSearchItem(
            id=row.id,
            name=row.name,
            excerpt=(row.extracted_text or "")[:180],
            subject_type=row.subject_type,
            subject_id=row.subject_id,
            status=row.status,
        )
        for row in rows
    ]


@router.post("/materials/{material_id}/ocr")
def ocr(material_id: UUID, user: Principal, session: DB):
    row = material_owned(session, user, material_id)
    if not row.media_type.startswith("image/"):
        raise APIError(422, "OCR_UNSUPPORTED", "仅支持图片 OCR")
    if not all(
        (
            settings.llm_base_url,
            settings.llm_api_key.get_secret_value(),
            settings.ocr_model,
        )
    ):
        raise APIError(503, "OCR_UNAVAILABLE", "OCR 服务尚未配置，可继续手工录入")
    encoded = base64.b64encode(row.content).decode()
    try:
        response = OpenAI(
            api_key=settings.llm_api_key.get_secret_value(),
            base_url=settings.llm_base_url,
        ).chat.completions.create(
            model=settings.ocr_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "逐字提取图片中的文字，只返回识别文本。",
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{row.media_type};base64,{encoded}"
                            },
                        },
                    ],
                }
            ],
            temperature=0,
            timeout=30,
        )
        text = (response.choices[0].message.content or "").strip()
        if not text:
            raise APIError(503, "OCR_FAILED", "没有识别到文字，可继续手工录入")
        row.extracted_text = text
        row.ocr_confidence = 0.8
        row.status = "ready"
        row.error_message = None
        row.updated_at = utcnow()
        session.query(DocumentReviewItem).filter(
            DocumentReviewItem.material_id == row.id,
            DocumentReviewItem.status == "pending",
        ).delete()
        session.add_all(
            [
                DocumentReviewItem(
                    owner_id=row.owner_id, material_id=row.id, **candidate
                )
                for candidate in extract_candidates(text, row.name)
            ]
        )
        session.commit()
        from backend.features.assistant.rag import enqueue_material

        enqueue_material(row)
        return {"id": row.id, "text": text, "confidence": row.ocr_confidence}
    except OpenAIError:
        raise APIError(503, "OCR_FAILED", "OCR 识别失败，请稍后重试") from None


@router.post("/materials/{material_id}/analyze")
def analyze(material_id: UUID, user: Principal, session: DB):
    row = material_owned(session, user, material_id)
    text = row.extracted_text or ""
    subjects = []
    for model, kind in ((HouseholdProfile, "profile"), (Pet, "pet")):
        for value in session.scalars(
            select(model)
            .join(Household, model.household_id == Household.id)
            .where(Household.owner_id == user.id)
        ):
            if value.name and value.name in text:
                subjects.append({"type": kind, "id": str(value.id), "name": value.name})
    changes = []
    for review in session.scalars(
        select(DocumentReviewItem).where(
            DocumentReviewItem.material_id == row.id,
            DocumentReviewItem.status == "pending",
        )
    ):
        model = Todo if review.target_type == "todo" else CalendarEvent
        cancelled = review.title.startswith("取消")
        lookup_title = (
            review.title.removeprefix("取消").strip() if cancelled else review.title
        )
        existing = session.scalar(
            select(model)
            .where(visible_condition(model, user.id), model.title == lookup_title)
            .limit(1)
        )
        if existing:
            current_date = (
                existing.due_date
                if review.target_type == "todo"
                else existing.starts_at.date()
            )
            review.change_kind = (
                "cancelled"
                if cancelled
                else "changed"
                if review.proposed_date and str(current_date) != review.proposed_date
                else "duplicate"
            )
            review.previous_value = f"{existing.title} · {current_date}"
            review.target_id = existing.id
            changes.append(
                {
                    "review_id": str(review.id),
                    "kind": review.change_kind,
                    "existing_id": str(existing.id),
                }
            )
    session.commit()
    return {"subjects": subjects, "changes": changes}
