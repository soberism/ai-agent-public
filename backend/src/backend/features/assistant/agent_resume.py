"""Resume a persisted approval checkpoint once."""

from langgraph.types import Command

from backend.api.routes.assistant_read_steps import inspect
from backend.core.security import redis, settings
from backend.features.assistant.autonomous_model import decide
from backend.features.assistant.autonomous_types import AutonomousContext
from backend.features.assistant.autonomous_workflow import run as run_graph
from backend.features.assistant.checkpoints import RunSaver as PostgresSaver
from backend.features.assistant.rag import retrieve
from backend.features.assistant.rag_quality import grade_chunks, rewrite_query


def context_for(session, agent_run, user):
    reads = 0
    rewritten = False

    def graded_retrieve(query):
        nonlocal reads, rewritten
        if reads >= 3:
            return []
        reads += 1
        graded = grade_chunks(agent_run.prompt, retrieve(session, user.id, query))
        if graded or rewritten or reads >= 3:
            return graded
        new_query = rewrite_query(agent_run.prompt, query)
        if not new_query:
            return []
        rewritten = True
        reads += 1
        return grade_chunks(agent_run.prompt, retrieve(session, user.id, new_query))

    return AutonomousContext(
        decide=decide,
        reader=lambda name, args: inspect(
            name, args, redis, user, session, agent_run.thread_id
        ),
        retriever=graded_retrieve,
    )


def resume_graph(agent_run, context):
    with PostgresSaver.from_conn_string(settings.checkpoint_url) as saver:
        saver.run_id = str(agent_run.id)
        config = {"configurable": {"thread_id": str(agent_run.id)}}
        checkpoint = saver.get(config)
        if checkpoint and checkpoint.get("channel_values", {}).get("approval", {}).get(
            "approved"
        ):
            return
        run_graph(
            agent_run.prompt,
            context,
            checkpointer=saver,
            config=config,
            command=Command(resume={"approved": True}),
        )
