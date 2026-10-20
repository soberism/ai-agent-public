from sqlalchemy import or_, select

from backend.api.hub_schemas import SearchItem
from backend.db.document_models import DocumentFolder, DocumentMaterial
from backend.features.sharing.access import visible_condition


def search_materials(session, user, terms):
    rows = session.execute(
        select(DocumentMaterial, DocumentFolder.name)
        .outerjoin(
            DocumentFolder,
            (DocumentMaterial.folder_id == DocumentFolder.id)
            & visible_condition(DocumentFolder, user.id),
        )
        .where(
            visible_condition(DocumentMaterial, user.id),
            or_(
                *(DocumentMaterial.name.ilike(term, escape="\\") for term in terms),
                *(DocumentFolder.name.ilike(term, escape="\\") for term in terms),
            ),
        )
        .order_by(DocumentMaterial.created_at.desc(), DocumentMaterial.id)
    )
    values = [
        SearchItem(
            id=row.id,
            kind="document",
            title=row.name,
            detail=f"目录：{folder or '未分类'}",
            url=f"/documents?folder={row.folder_id or ''}#material-{row.id}",
        )
        for row, folder in rows
    ]
    for folder in session.scalars(
        select(DocumentFolder)
        .where(
            visible_condition(DocumentFolder, user.id),
            or_(*(DocumentFolder.name.ilike(term, escape="\\") for term in terms)),
        )
        .order_by(DocumentFolder.name, DocumentFolder.id)
    ):
        values.append(
            SearchItem(
                id=folder.id,
                kind="folder",
                title=folder.name,
                detail="材料目录",
                url=f"/documents?folder={folder.id}#directory-{folder.id}",
            )
        )
    return values
