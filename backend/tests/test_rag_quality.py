import json
from types import SimpleNamespace
from uuid import uuid4

from backend.features.assistant import agent_resume, rag_quality


def test_grade_chunks_keeps_only_returned_candidate_ids(monkeypatch):
    def create(**_):
        return SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(
                        tool_calls=[
                            SimpleNamespace(
                                function=SimpleNamespace(
                                    name="grade_passages",
                                    arguments=json.dumps(
                                        {"relevant_ids": ["chunk-2", "invented"]}
                                    ),
                                )
                            )
                        ]
                    )
                )
            ]
        )

    monkeypatch.setattr(
        rag_quality,
        "client",
        lambda: SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=create))
        ),
    )
    chunks = [
        {"chunk_id": "chunk-1", "content": "无关片段"},
        {"chunk_id": "chunk-2", "content": "相关片段"},
    ]
    assert rag_quality.grade_chunks("问题", chunks) == chunks[1:]


def test_retrieval_rewrites_at_most_once_and_stops_at_three_reads(monkeypatch):
    queries = []
    monkeypatch.setattr(
        agent_resume,
        "retrieve",
        lambda _session, _user, query: (
            queries.append(query) or [{"chunk_id": query, "content": query}]
        ),
    )
    monkeypatch.setattr(
        agent_resume,
        "grade_chunks",
        lambda _question, chunks: chunks if chunks[0]["chunk_id"] == "重写词" else [],
    )
    monkeypatch.setattr(agent_resume, "rewrite_query", lambda *_: "重写词")
    context = agent_resume.context_for(
        object(),
        SimpleNamespace(prompt="资料问题", thread_id=uuid4()),
        SimpleNamespace(id=uuid4()),
    )

    assert context.retriever("首次词")[0]["chunk_id"] == "重写词"
    context.retriever("第三次词")
    assert context.retriever("第四次词") == []
    assert queries == ["首次词", "重写词", "第三次词"]
