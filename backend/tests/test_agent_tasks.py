from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

from fastapi import Response

from backend.features.assistant.agent_celery import celery, index_material_task
from backend.features.assistant.agent_plan_results import summarize
from backend.features.assistant.agent_tasks import (
    CANCELLING_PROGRESS,
    claim,
    fail_stale_actions,
    finish,
)


class Session:
    def __init__(self, claimed=None):
        self.claimed = claimed
        self.added = []
        self.commits = 0

    def scalar(self, statement):
        self.statement = statement
        return self.claimed

    def scalars(self, statement):
        self.statement = statement
        return [self.claimed] if self.claimed else []

    def get(self, model, key):
        if model.__name__ == "AssistantMessage":
            return next((item for item in self.added if item.id == key), None)
        if model.__name__ == "User":
            return SimpleNamespace(id=key, active=True)
        if model.__name__ == "AgentRun":
            return SimpleNamespace(id=key)
        return SimpleNamespace(updated_at=None)

    def add(self, value):
        self.added.append(value)

    def refresh(self, value, **kwargs):
        return None

    def flush(self):
        return None

    def rollback(self):
        return None

    def commit(self):
        self.commits += 1


def test_claim_returns_nothing_when_atomic_update_loses():
    session = Session()
    assert claim(session, uuid4(), uuid4()) == (None, None)
    sql = str(session.statement)
    assert "UPDATE agent_runs" in sql
    assert "lease_expires_at <" in sql


def test_finish_appends_assistant_history_only_once():
    session = Session()
    run = SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        status="running",
        progress=None,
        error=None,
        updated_at=datetime.now(UTC),
        history_saved=False,
        final_answer=None,
        lease_expires_at=datetime.now(UTC),
    )

    finish(session, run, "completed", "已创建清单「同学录」，包含 3 项。")
    finish(session, run, "completed", "已创建清单「同学录」，包含 3 项。")

    assert len(session.added) == 1
    assert session.added[0].content == run.final_answer
    assert run.history_saved is True
    assert run.lease_expires_at is None


def test_finish_reports_started_action_after_cancel_request():
    session = Session()
    run = SimpleNamespace(
        id=uuid4(),
        thread_id=uuid4(),
        status="running",
        progress=CANCELLING_PROGRESS,
        error=None,
        updated_at=datetime.now(UTC),
        history_saved=False,
        final_answer=None,
        lease_expires_at=datetime.now(UTC),
    )

    finish(session, run, "completed", "已创建清单。")

    assert run.status == "cancelled"
    assert run.final_answer == "已创建清单。 后续操作已取消。"


def test_embedding_index_task_has_bounded_retry():
    assert index_material_task.max_retries == 3
    assert index_material_task.autoretry_for


def test_worker_remote_control_is_disabled():
    assert celery.conf.worker_enable_remote_control is False


def test_stale_executing_actions_require_manual_check():
    action = SimpleNamespace(status="executing", error=None)

    class StaleSession(Session):
        def scalars(self, statement):
            return [action]

    fail_stale_actions(StaleSession(), uuid4())

    assert action.status == "failed"
    assert action.error == "执行结果待核对，请勿重复提交"


def test_plan_reply_names_completed_changes_and_failures():
    actions = [
        SimpleNamespace(
            status="completed",
            tool_name="create_checklist",
            title="创建清单及清单项",
            arguments={"body": {"title": "同学录", "items": ["刘", "洲", "网"]}},
            result={"items": [{"title": "同学录"}]},
        ),
        SimpleNamespace(
            status="completed",
            tool_name="set_sharing",
            title="修改共享范围",
            arguments={"body": {"scope": "household"}},
            result={"items": [{"title": "同学录"}]},
        ),
        SimpleNamespace(status="failed", title="删除清单项", error="目标不存在"),
    ]

    assert summarize(actions) == (
        "已创建清单「同学录」，包含 3 项；"
        "已将「同学录」设为家庭可见；"
        "删除清单项失败：目标不存在。"
    )


def test_active_run_and_reindex_routes_are_published():
    from backend.app import app

    paths = app.openapi()["paths"]
    assert "get" in paths["/api/agent/runs/active/{thread_id}"]
    assert "post" in paths["/api/agent/runs/knowledge/reindex"]


def test_active_run_without_match_returns_no_content(monkeypatch):
    from backend.api.routes import agent_runs

    monkeypatch.setattr(agent_runs.history, "owned", lambda *_: object())
    result = agent_runs.active(uuid4(), SimpleNamespace(id=uuid4()), Session())

    assert isinstance(result, Response)
    assert result.status_code == 204
    assert result.body == b""


def test_follow_up_revises_pending_plan_instead_of_targeting_uncreated_object():
    from backend.api.routes.agent_runs import revision_prompt

    pending = SimpleNamespace(
        id=uuid4(),
        status="waiting",
        progress=None,
        final_answer=None,
        updated_at=None,
    )
    action = SimpleNamespace(
        title="创建清单及清单项",
        tool_name="create_checklist",
        arguments={"body": {"title": "旅行准备清单", "items": ["证件与钱包"]}},
        status="proposed",
    )

    class PendingSession(Session):
        def scalars(self, statement):
            return [action]

    prompt = revision_prompt(
        PendingSession(claimed=pending), pending, "感觉东西不全，再补充下"
    )

    assert pending.status == "waiting"
    assert action.status == "proposed"
    assert "不代表对象已经创建" in prompt
    assert '"operation": "创建清单及清单项"' in prompt
    assert '"tool_name": "create_checklist"' in prompt
    assert "请保留旧草稿的创建工具及参数结构" in prompt
    assert prompt.endswith("用户补充：感觉东西不全，再补充下")


def test_date_change_keeps_unconfirmed_create_todo_draft():
    from backend.api.routes.agent_runs import revision_prompt

    action = SimpleNamespace(
        title="创建待办",
        tool_name="create_todo",
        arguments={
            "body": {
                "title": "给植物换盆",
                "due_date": "2026-10-04",
                "due_time": "10:00",
            }
        },
    )

    class PendingSession(Session):
        def scalars(self, statement):
            return [action]

    prompt = revision_prompt(
        PendingSession(),
        SimpleNamespace(id=uuid4()),
        "下个月 3 号上午十点提醒我给植物换盆。",
    )

    assert '"tool_name": "create_todo"' in prompt
    assert '"due_date": "2026-10-04"' in prompt
    assert "不要改用编辑工具" in prompt
    assert prompt.endswith("用户补充：下个月 3 号上午十点提醒我给植物换盆。")


def test_new_topic_does_not_inherit_pending_plan():
    from backend.features.assistant.turn_tasks import pending_draft

    action = SimpleNamespace(
        title="创建待办",
        tool_name="create_todo",
        arguments={"body": {"title": "给植物换盆"}},
    )
    session = Mock()
    session.scalars.return_value = [action]
    pending = SimpleNamespace(id=uuid4(), plan_version=1)

    assert pending_draft(session, pending, "你好") is None
    assert pending_draft(session, pending, "查看今天的待办") is None
    revision = pending_draft(session, pending, "把它改成后天")
    assert revision["plan_version"] == 1
    assert revision["draft"][0]["tool_name"] == "create_todo"
