from types import SimpleNamespace

from pydantic import SecretStr

from backend.features.assistant import rag
from backend.features.assistant.rag import chunks


def test_chunks_normalizes_and_overlaps_long_text():
    values = chunks("  第一段\n" + "字" * 1200, size=1000, overlap=100)

    assert len(values) == 2
    assert values[0][-100:] == values[1][:100]


def test_retrieval_query_uses_shared_material_visibility(monkeypatch):
    class Session:
        statement = None

        def execute(self, statement):
            self.statement = statement
            return []

    session = Session()
    monkeypatch.setattr(rag, "embed", lambda _: [[0.0] * 1536])

    assert rag.retrieve(session, "00000000-0000-0000-0000-000000000001", "保单") == []
    assert "item_sharing" in str(session.statement)


def test_embeddings_use_separate_provider_and_fixed_dimension(monkeypatch):
    captured = {}

    class Embeddings:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(data=[SimpleNamespace(embedding=[0.0] * 1536)])

    def client(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(embeddings=Embeddings())

    monkeypatch.setattr(rag, "OpenAI", client)
    monkeypatch.setattr(
        "backend.core.security.settings",
        SimpleNamespace(
            embedding_model="text-embedding-v4",
            embedding_base_url="",
            embedding_api_key=SecretStr(""),
            transcription_base_url="https://example.test/v1",
            transcription_api_key=SecretStr("test-key"),
        ),
    )
    assert len(rag.embed(["检索测试"])[0]) == 1536
    assert captured["base_url"] == "https://example.test/v1"
    assert captured["dimensions"] == 1536
