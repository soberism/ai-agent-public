import hashlib
from pathlib import Path
from typing import Annotated
from urllib.parse import quote
from uuid import UUID

from fastapi import APIRouter, File, Form, Response, UploadFile
from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError

from backend.api.document_schemas import (
    DocumentCapabilities,
    FolderCreate,
    FolderOut,
    MaterialList,
    MaterialOut,
    MaterialPatch,
)
from backend.api.schemas import ERROR_RESPONSES
from backend.core.security import DB, APIError, Principal
from backend.db.document_models import (
    DocumentFolder,
    DocumentMaterial,
    DocumentReviewItem,
)
from backend.features.documents.extraction import decode_text, extract_candidates
from backend.features.documents.preview import preview_type
from backend.features.sharing.access import visible_condition
from backend.features.sharing.cleanup import delete_resource

router = APIRouter(prefix="/api/documents", tags=["文档"], responses=ERROR_RESPONSES)
MAX_FILE_SIZE = 20 * 1024 * 1024


def folder_owned(session, user, folder_id):
    if folder_id is None:
        return None
    row = session.scalar(
        select(DocumentFolder).where(
            DocumentFolder.id == folder_id, DocumentFolder.owner_id == user.id
        )
    )
    if row is None:
        raise APIError(404, "FOLDER_NOT_FOUND", "文件夹不存在或无法访问")
    return row


def material_owned(session, user, material_id):
    row = session.scalar(
        select(DocumentMaterial).where(
            DocumentMaterial.id == material_id,
            visible_condition(DocumentMaterial, user.id),
        )
    )
    if row is None:
        raise APIError(404, "MATERIAL_NOT_FOUND", "材料不存在或无法访问")
    return row


def material_out(session, row):
    review_count = session.scalar(
        select(func.count()).where(
            DocumentReviewItem.material_id == row.id,
            DocumentReviewItem.status == "pending",
        )
    )
    return MaterialOut(
        id=row.id,
        name=row.name,
        kind=row.kind,
        status=row.status,
        created_at=row.created_at,
        folder_id=row.folder_id,
        error_message=row.error_message,
        review_count=review_count,
    )


def folders_out(session, user):
    rows = session.execute(
        select(DocumentFolder, func.count(DocumentMaterial.id))
        .outerjoin(
            DocumentMaterial,
            and_(
                DocumentMaterial.folder_id == DocumentFolder.id,
                visible_condition(DocumentMaterial, user.id),
            ),
        )
        .where(visible_condition(DocumentFolder, user.id))
        .group_by(DocumentFolder.id)
        .order_by(DocumentFolder.name, DocumentFolder.id)
    )
    return [
        FolderOut(
            id=row.id, name=row.name, count=count, editable=row.owner_id == user.id
        )
        for row, count in rows
    ]


@router.get("/capabilities", response_model=DocumentCapabilities)
def capabilities():
    return DocumentCapabilities()


@router.get("/materials", response_model=MaterialList)
def materials(user: Principal, session: DB):
    rows = session.scalars(
        select(DocumentMaterial)
        .where(visible_condition(DocumentMaterial, user.id))
        .order_by(DocumentMaterial.created_at.desc(), DocumentMaterial.id)
    )
    return MaterialList(
        items=[material_out(session, row) for row in rows],
        folders=folders_out(session, user),
    )


@router.post("/materials", response_model=MaterialOut, status_code=201)
def upload(
    user: Principal,
    session: DB,
    file: Annotated[UploadFile, File()],
    folder_id: Annotated[UUID | None, Form()] = None,
    recognize: Annotated[bool, Form()] = False,
):
    folder_owned(session, user, folder_id)
    content = file.file.read(MAX_FILE_SIZE + 1)
    if not content:
        raise APIError(422, "EMPTY_FILE", "请选择非空文件")
    if len(content) > MAX_FILE_SIZE:
        raise APIError(413, "FILE_TOO_LARGE", "单个文件不能超过20 MiB")
    digest = hashlib.sha256(content).hexdigest()
    if session.scalar(
        select(DocumentMaterial.id).where(
            visible_condition(DocumentMaterial, user.id),
            DocumentMaterial.content_hash == digest,
        )
    ):
        raise APIError(409, "MATERIAL_DUPLICATE", "该材料已上传，请查看现有记录")
    name = Path(file.filename or "未命名材料").name[:255]
    extracted = decode_text(content, name, file.content_type) if recognize else None
    candidates = extract_candidates(extracted, Path(name).stem) if extracted else []
    row = DocumentMaterial(
        owner_id=user.id,
        folder_id=folder_id,
        name=name,
        kind="photo" if (file.content_type or "").startswith("image/") else "file",
        media_type=(file.content_type or "application/octet-stream")[:100],
        size=len(content),
        content_hash=digest,
        content=content,
        extracted_text=extracted,
        status=("ready" if extracted is not None else "partial")
        if recognize
        else "uploaded",
        error_message=None
        if not recognize or extracted is not None
        else "文件已保存，当前仅支持 UTF-8 文本提取",
    )
    session.add(row)
    session.flush()
    session.add_all(
        [
            DocumentReviewItem(owner_id=user.id, material_id=row.id, **item)
            for item in candidates
        ]
    )
    session.commit()
    from backend.features.assistant.rag import enqueue_material

    enqueue_material(row)
    return material_out(session, row)


@router.get("/materials/{material_id}/content", response_class=Response)
def content(material_id: UUID, user: Principal, session: DB, download: bool = False):
    row = material_owned(session, user, material_id)
    safe_type = preview_type(row.content, row.media_type)
    disposition = "attachment" if download or safe_type is None else "inline"
    return Response(
        content=row.content,
        media_type=safe_type or "application/octet-stream",
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "sandbox; default-src 'none'; base-uri 'none'; form-action 'none'",
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(row.name)}",
        },
    )


@router.get("/materials/{material_id}/download", response_class=Response)
def download_material(material_id: UUID, user: Principal, session: DB):
    return content(material_id, user, session, download=True)


@router.patch("/materials/{material_id}", response_model=MaterialOut)
def move(
    material_id: UUID,
    body: MaterialPatch,
    user: Principal,
    session: DB,
):
    row = material_owned(session, user, material_id)
    if "folder_id" in body.model_fields_set:
        folder_owned(session, user, body.folder_id)
        row.folder_id = body.folder_id
    if body.name is not None:
        row.name = body.name
    session.commit()
    return material_out(session, row)


@router.delete("/materials/{material_id}", status_code=204)
def remove_material(material_id: UUID, user: Principal, session: DB):
    delete_resource(session, material_owned(session, user, material_id))
    session.commit()


@router.post("/folders", response_model=FolderOut, status_code=201)
def create_folder(body: FolderCreate, user: Principal, session: DB):
    if session.scalar(
        select(DocumentFolder.id).where(
            visible_condition(DocumentFolder, user.id), DocumentFolder.name == body.name
        )
    ):
        raise APIError(409, "FOLDER_DUPLICATE", "目录名称已存在，请换一个名称")
    row = DocumentFolder(owner_id=user.id, name=body.name)
    session.add(row)
    try:
        session.commit()
    except IntegrityError as failure:
        session.rollback()
        if getattr(failure.orig, "sqlstate", None) == "23505":
            raise APIError(
                409, "FOLDER_DUPLICATE", "目录名称已存在，请换一个名称"
            ) from None
        raise
    return FolderOut(id=row.id, name=row.name, count=0)


@router.put("/folders/{folder_id}", response_model=FolderOut)
def rename_folder(folder_id: UUID, body: FolderCreate, user: Principal, session: DB):
    row = folder_owned(session, user, folder_id)
    row.name = body.name
    session.commit()
    count = session.scalar(
        select(func.count()).where(
            DocumentMaterial.folder_id == row.id,
            visible_condition(DocumentMaterial, user.id),
        )
    )
    return FolderOut(
        id=row.id, name=row.name, count=count, editable=row.owner_id == user.id
    )


@router.delete("/folders/{folder_id}", status_code=204)
def remove_folder(folder_id: UUID, user: Principal, session: DB):
    row = folder_owned(session, user, folder_id)
    session.execute(
        DocumentMaterial.__table__.update()
        .where(DocumentMaterial.folder_id == row.id)
        .values(folder_id=None)
    )
    delete_resource(session, row)
    session.commit()
