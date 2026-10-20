"""Permission-filtered retrieval over extracted document text."""

import hashlib

from kombu.exceptions import OperationalError
from openai import OpenAI, OpenAIError
from sqlalchemy import delete, select

from backend.core.security import unavailable
from backend.db.agent_models import KnowledgeChunk
from backend.db.document_models import DocumentMaterial
from backend.features.sharing.access import visible_condition


def chunks(text: str, size: int = 1000, overlap: int = 120) -> list[str]:
    value = " ".join(text.split())
    if not value:
        return []
    return [
        value[start : start + size] for start in range(0, len(value), size - overlap)
    ]


def embed(values: list[str]) -> list[list[float]]:
    from backend.core.security import settings

    if not settings.embedding_model:
        raise unavailable("知识库向量模型尚未配置")
    base_url = settings.embedding_base_url or settings.transcription_base_url
    api_key = (
        settings.embedding_api_key.get_secret_value()
        or settings.transcription_api_key.get_secret_value()
    )
    if not base_url or not api_key:
        raise unavailable("知识库向量服务尚未配置")
    try:
        response = OpenAI(base_url=base_url, api_key=api_key).embeddings.create(
            model=settings.embedding_model,
            input=values,
            dimensions=1536,
            timeout=20,
        )
        vectors = [item.embedding for item in response.data]
    except OpenAIError:
        raise unavailable("知识库向量服务暂时不可用") from None
    if any(len(value) != 1536 for value in vectors):
        raise unavailable("知识库向量维度必须为1536")
    return vectors


def refresh_material(session, material: DocumentMaterial) -> int:
    values = chunks(material.extracted_text or "")
    session.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.material_id == material.id)
    )
    if not values:
        return 0
    for content, vector in zip(values, embed(values), strict=True):
        session.add(
            KnowledgeChunk(
                material_id=material.id,
                owner_id=material.owner_id,
                content_hash=hashlib.sha256(content.encode()).hexdigest(),
                content=content,
                embedding=vector,
            )
        )
    session.flush()
    return len(values)


def locator(material: DocumentMaterial, content: str) -> dict | None:
    text = " ".join((material.extracted_text or "").split())
    if text.count(content) != 1:
        return None
    return {"char_offset": text.index(content)}


def retrieve(session, owner_id, query: str, limit: int = 5) -> list[dict]:
    query_vector = embed([query])[0]
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)
    rows = session.execute(
        select(KnowledgeChunk, DocumentMaterial, distance.label("distance"))
        .join(DocumentMaterial, DocumentMaterial.id == KnowledgeChunk.material_id)
        .where(visible_condition(DocumentMaterial, owner_id))
        .order_by(distance)
        .limit(limit)
    )
    return [
        {
            "chunk_id": str(chunk.id),
            "material_id": str(material.id),
            "document_version": material.content_hash,
            "locator": locator(material, chunk.content),
            "title": material.name,
            "content": chunk.content,
            "score": round(1 - float(distance_value), 4),
            "url": f"/documents#material-{material.id}",
        }
        for chunk, material, distance_value in rows
    ]


def enqueue_material(material) -> None:
    if not material.extracted_text:
        return
    try:
        from backend.features.assistant.agent_celery import index_material_task

        index_material_task.delay(str(material.id), str(material.owner_id))
    except OperationalError:
        # Indexing is eventually consistent; document writes must still succeed.
        return
