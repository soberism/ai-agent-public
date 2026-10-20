"""Background indexing jobs for assistant materials."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.document_models import DocumentMaterial
from backend.db.session import engine
from backend.features.assistant.rag import refresh_material


def execute_index(material_id: str, owner_id: str):
    with Session(engine) as session:
        material = session.scalar(
            select(DocumentMaterial).where(
                DocumentMaterial.id == material_id,
                DocumentMaterial.owner_id == owner_id,
            )
        )
        if material is None:
            return
        refresh_material(session, material)
        session.commit()


def execute_reindex(owner_id: str):
    with Session(engine) as session:
        materials = session.scalars(
            select(DocumentMaterial).where(
                DocumentMaterial.owner_id == owner_id,
                DocumentMaterial.extracted_text.is_not(None),
            )
        )
        for material in materials:
            refresh_material(session, material)
        session.commit()
