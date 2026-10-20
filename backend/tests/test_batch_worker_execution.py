from types import SimpleNamespace
from uuid import uuid4

from backend.core.security import APIError
from backend.features.assistant import agent_tasks


def test_worker_attempts_every_approved_action_and_reports_partial_failure(monkeypatch):
    run = SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        status="queued",
        progress=None,
        graph_resumed=True,
    )
    user = SimpleNamespace(id=uuid4())
    actions = [
        SimpleNamespace(
            id=uuid4(),
            status="approved",
            title=f"修改待办{i}",
            tool_name="edit_todo",
            arguments={"id": str(uuid4())},
            result=None,
            error=None,
        )
        for i in range(3)
    ]
    by_id = {action.id: action for action in actions}

    class Session:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def scalars(self, _):
            return actions

        def get(self, model, identifier):
            return run if model.__name__ == "AgentRun" else by_id[identifier]

        def refresh(self, *_args, **_kwargs):
            pass

        def commit(self):
            pass

        def rollback(self):
            pass

    called, published = [], []
    from backend.features.assistant import summary_jobs

    scheduled = []
    monkeypatch.setattr(summary_jobs, "schedule", lambda *args: scheduled.append(args))
    monkeypatch.setattr(agent_tasks, "Session", lambda _: Session())
    monkeypatch.setattr(agent_tasks, "claim", lambda *_: (run, user))
    monkeypatch.setattr(agent_tasks, "fail_stale_actions", lambda *_: None)
    monkeypatch.setattr(
        agent_tasks,
        "finish",
        lambda session, row, status, answer, **kwargs: published.append(answer),
    )

    def invoke(name, arguments, *_args, **kwargs):
        called.append(kwargs["idempotency_token"])
        if len(called) == 2:
            raise APIError(404, "NOT_FOUND", "目标已不存在")
        return SimpleNamespace(model_dump=lambda **_: {"kind": "success", "items": []})

    monkeypatch.setattr(agent_tasks, "invoke", invoke)
    agent_tasks.execute_plan(str(run.id), str(user.id))
    assert called == [action.id for action in actions]
    assert [action.status for action in actions] == ["completed", "failed", "completed"]
    assert "修改待办0已完成" in published[0]
    assert "修改待办1失败：目标已不存在" in published[0]
    assert "修改待办2已完成" in published[0]

    assert scheduled == [(str(user.id), str(run.thread_id))]
