"""真实模型验证常识、公开信息路由和原生业务证据；联网响应隔离替身。"""

import os
from pathlib import Path
from uuid import uuid4

import pytest
import test_assistant_priority_fixes_live as priority
from test_assistant_priority_fixes_live import agent  # noqa: F401

from backend.features.assistant import autonomous_workflow

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.fixture(autouse=True)
def output_file(monkeypatch):
    monkeypatch.setattr(
        priority,
        "OUTPUT",
        Path(__file__).parent
        / "results"
        / "assistant_remaining_fixes_2026-10-16.jsonl",
    )


@pytest.mark.parametrize(
    "prompt,words",
    [
        ("为什么天空会是蓝色的？", ["散射"]),
        ("解释一下 RAG。", ["检索"]),
        ("雨后泥土为什么有气味？", ["土"]),
        ("冰为什么浮在水面上？", ["密度"]),
        ("帮我写一封简短的感谢信。", ["感谢"]),
        ("周末带孩子出门玩有什么思路？", ["公园", "博物馆", "户外"]),
        ("能帮我发邮件给朋友吗？", ["起草", "草稿", "撰写"]),
        ("直接从我的银行卡扣钱付水费。", ["无法", "不能", "不支持", "没法", "没有"]),
    ],
)
def test_general_answer_avoids_private_retrieval(request, monkeypatch, prompt, words):
    def forbidden(*args, **kwargs):
        pytest.fail("普通问答不应读取私人知识库或联网")

    monkeypatch.setattr(autonomous_workflow, "search_web", forbidden)
    monkeypatch.setattr(autonomous_workflow, "retrieve", forbidden)
    send = request.getfixturevalue("agent")
    run, tools = send(prompt)
    assert run["status"] == "completed" and not tools, run
    assert any(word in run["final_answer"] for word in words), run
    assert "证据尚不足" not in run["final_answer"]
    assert not any(
        send.traces[-1].get(key) for key in ("observations", "knowledge", "web_results")
    )


@pytest.mark.parametrize(
    "prompt",
    [
        "今天上海的空气质量是多少？如果没有实时来源请直说。",
        "今天人民币兑美元的汇率是多少？",
        "今天沪电股份收盘价是多少？",
        "这周末有哪场足球比赛？",
    ],
)
def test_public_realtime_uses_web_or_clarifies_scope(request, monkeypatch, prompt):
    searches = []

    def search(args):
        searches.append(args)
        return [
            {
                "title": "测试公开来源",
                "url": "https://example.com/public",
                "content": "公开测试来源没有提供所问的实时数值或赛事安排。",
            }
        ]

    monkeypatch.setattr(autonomous_workflow, "search_web", search)
    send = request.getfixturevalue("agent")
    run, tools = send(prompt)
    assert run["status"] == "completed" and not tools, run
    assert "请明确说明需要联网" not in run["final_answer"]
    assert "证据尚不足" not in run["final_answer"]
    if "足球" in prompt and not searches:
        assert any(word in run["final_answer"] for word in ("联赛", "赛事", "地区")), (
            run
        )
    else:
        assert len(searches) == 1, run
    assert "日程0项" not in run["final_answer"]
    assert not send.traces[-1].get("observations")
    assert not send.traces[-1].get("knowledge")


@pytest.mark.parametrize(
    "setup,path,prompt,expected",
    [
        (
            {"name": "测试燕麦", "quantity": 3, "unit": "袋"},
            "/api/life/pantry",
            "现有库存有哪些？",
            "测试燕麦",
        ),
        (
            {"label": "测试花生过敏", "kind": "allergy"},
            "/api/life/preferences",
            "我有哪些长期饮食偏好？",
            "测试花生过敏",
        ),
        (
            {"transcript": "测试语音备忘内容"},
            "/api/assistant/voice-memos",
            "我的语音备忘有哪些？",
            "测试语音备忘内容",
        ),
        (
            {"content": "测试记忆喜欢步行"},
            "/api/assistant/memories",
            "我保存的长期记忆有哪些？",
            "测试记忆喜欢步行",
        ),
        ({"name": "测试家庭"}, "/api/households", "我有哪些家庭？", "测试家庭"),
        (
            {"title": "测试采购"},
            "/api/life/shopping-lists",
            "我的购物清单有哪些？",
            "测试采购",
        ),
    ],
)
def test_seeded_business_lists_publish_native_evidence(
    request, cloud, setup, path, prompt, expected
):
    send = request.getfixturevalue("agent")
    created = cloud.post(path, json=setup)
    assert created.status_code == 201, created.text
    run, tools = send(prompt)
    assert run["status"] == "completed" and not tools, run
    assert (
        expected in run["final_answer"] and "证据尚不足" not in run["final_answer"]
    ), run


@pytest.mark.parametrize(
    "prompt,expected",
    [
        ("我设置的时区是什么？", "Asia/Shanghai"),
        ("我的AI回答偏好是什么？", "先结论再步骤"),
        ("长期记忆功能现在启用了吗？", "是"),
    ],
)
def test_settings_fields_are_verifiable(request, cloud, prompt, expected):
    send = request.getfixturevalue("agent")
    changed = cloud.patch(
        "/api/assistant/preferences",
        json={"custom_instructions": "先结论再步骤", "memory_enabled": True},
    )
    assert changed.status_code == 200, changed.text
    run, tools = send(prompt)
    assert run["status"] == "completed" and not tools, run
    assert expected in run["final_answer"], run


def test_reminder_list_preserves_timestamp(request, cloud):
    send = request.getfixturevalue("agent")
    todo = cloud.post(
        "/api/todos",
        json={"title": "提醒关联测试", "due_date": "2026-12-01"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert todo.status_code == 201, todo.text
    created = cloud.post(
        "/api/planning/reminders",
        json={
            "todo_id": todo.json()["id"],
            "remind_date": "2026-12-01",
            "remind_time": "09:00",
        },
    )
    assert created.status_code == 201, created.text
    run, tools = send("我有哪些应用内提醒？")
    assert run["status"] == "completed" and not tools, run
    assert "2026-12-01" in run["final_answer"], run


def test_material_list_is_metadata_not_private_document_contents(request, cloud):
    send = request.getfixturevalue("agent")
    uploaded = cloud.post(
        "/api/documents/materials",
        files={"file": ("测试材料.txt", "测试文件内容".encode(), "text/plain")},
    )
    assert uploaded.status_code == 201, uploaded.text
    run, tools = send("我上传了哪些材料？")
    assert run["status"] == "completed" and not tools, run
    assert "测试材料.txt" in run["final_answer"], run
    assert not send.traces[-1].get("knowledge")


def test_memory_learning_advice_does_not_read_saved_private_memories(request):
    send = request.getfixturevalue("agent")
    run, tools = send("我想提升记忆，有什么学习方法？")
    assert run["status"] == "completed" and not tools, run
    assert not any(
        send.traces[-1].get(k) for k in ("observations", "knowledge", "web_results")
    )
    assert any(word in run["final_answer"] for word in ("复习", "回忆", "练习")), run
