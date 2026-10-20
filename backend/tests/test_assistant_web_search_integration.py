"""使用专用云端测试库验证联网草稿的确认与原子写入。"""

from fastapi.testclient import TestClient
from helpers import HEADERS, register
from sqlalchemy.orm import Session

from backend.api.routes import assistant, assistant_actions
from backend.app import app
from backend.core import security
from backend.db.models import ChecklistItem
from backend.features.assistant import graph, replies


def prepare(monkeypatch):
    intent = graph.Intent(
        action="create_checklist",
        title="出国必备",
        items=["护照", "转换插头", "充电宝"],
    )
    intent._sources = [{"title": "旅行准备参考", "url": "https://example.com/travel"}]
    monkeypatch.setattr(assistant, "interpret", lambda *_: intent)
    monkeypatch.setattr(assistant, "personalize", lambda reply, *_: reply)
    monkeypatch.setattr(replies, "personalize_for_user", lambda reply, *_: reply)


def request_draft(client):
    thread = client.post("/api/assistant/threads", json={}).json()["thread_id"]
    response = client.post(
        "/api/assistant/messages",
        json={"thread_id": thread, "message": "参考网上清单，创建出国必备"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def list_checklists(client):
    response = client.get("/api/planning/checklists")
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_draft_confirm_sources_order_and_token_boundaries(cloud, monkeypatch):
    prepare(monkeypatch)
    register(cloud)
    assert list_checklists(cloud) == []
    draft = request_draft(cloud)
    assert draft["kind"] == "confirm"
    assert "1. 护照\n2. 转换插头\n3. 充电宝" in draft["message"]
    assert "旅行准备参考\nhttps://example.com/travel" in draft["message"]
    assert list_checklists(cloud) == []
    token = draft["action_token"]
    path = f"/api/assistant/actions/{token}/confirm"
    with TestClient(app, headers=HEADERS) as other:
        register(other)
        assert other.post(path, json={}).status_code == 404
    result = cloud.post(path, json={})
    assert result.status_code == 200, result.text
    assert "共3项" in result.json()["message"]
    checklist_id = result.json()["items"][0]["id"]
    checklist = cloud.get(f"/api/planning/checklists/{checklist_id}").json()
    assert checklist["total_count"] == 3 and checklist["completed_count"] == 0
    assert [item["title"] for item in checklist["items"]] == [
        "护照",
        "转换插头",
        "充电宝",
    ]
    assert [item["position"] for item in checklist["items"]] == [0, 1, 2]
    assert cloud.post(path, json={}).status_code == 404
    expired = request_draft(cloud)["action_token"]
    security.redis.delete(assistant_actions.action_key(expired))
    assert (
        cloud.post(f"/api/assistant/actions/{expired}/confirm", json={}).status_code
        == 404
    )
    assert len(list_checklists(cloud)) == 1


def test_item_database_failure_rolls_back_parent(cloud, monkeypatch):
    prepare(monkeypatch)
    register(cloud)
    draft = request_draft(cloud)
    original = Session.add_all

    def invalid_items(session, instances):
        instances = list(instances)
        for instance in instances:
            if isinstance(instance, ChecklistItem):
                instance.title = ""
        return original(session, instances)

    with monkeypatch.context() as patch:
        patch.setattr(Session, "add_all", invalid_items)
        result = cloud.post(
            f"/api/assistant/actions/{draft['action_token']}/confirm", json={}
        )
        assert result.status_code == 503, result.text
        assert result.json()["error"]["code"] == "SERVICE_UNAVAILABLE"
    assert list_checklists(cloud) == []
