"""截图多轮日程查询使用真实模型，日期覆盖远年而非隐式拼接窗口。"""

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import test_assistant_priority_fixes_live as priority
from test_assistant_priority_fixes_live import agent  # noqa: F401

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_MODEL") != "1", reason="显式启用真实模型"
)


@pytest.fixture(autouse=True)
def capture(monkeypatch):
    monkeypatch.setattr(
        priority,
        "OUTPUT",
        Path(__file__).parent / "results/assistant_all_time_events_2026-10-19.jsonl",
    )


def add_event(cloud, title, day):
    response = cloud.post(
        "/api/calendar/events",
        json={
            "title": title,
            "start_date": day,
            "start_time": "08:00",
            "end_date": day,
            "end_time": "09:00",
        },
    )
    assert response.status_code == 201, response.text


def test_all_time_event_followups(cloud, request):
    send = request.getfixturevalue("agent")
    current_day = (
        datetime.now(ZoneInfo("Asia/Shanghai")).date().replace(day=21).isoformat()
    )
    for title, day in [
        ("本月会议", current_day),
        ("早年安排", "1990-01-10"),
        ("远期安排", "2035-12-20"),
    ]:
        add_event(cloud, title, day)
    first, tools = send("现在有什么日程")
    assert first["status"] == "completed" and not tools
    assert "本月会议" in first["final_answer"]
    assert (
        "早年安排" not in first["final_answer"]
        and "远期安排" not in first["final_answer"]
    )
    for prompt in ["全部时间日程呢额", "全部日程呢"]:
        run, tools = send(prompt)
        assert run["status"] == "completed" and not tools, run
        assert all(
            title in run["final_answer"]
            for title in ["本月会议", "早年安排", "远期安排"]
        ), run
        assert "全部时间" in run["final_answer"] and "日程3项" in run["final_answer"]
        reads = send.traces[-1]["observations"]
        assert len(reads) == 1 and reads[0]["tool_name"] == "list_all_events"
    final, tools = send("现在有什么日程")
    assert final["status"] == "completed" and not tools
    assert "本月会议" in final["final_answer"]
    assert (
        "上限" not in final["final_answer"]
        and "信息仍不完整" not in final["final_answer"]
    )


def test_empty_all_time_query_is_verified_zero(request):
    send = request.getfixturevalue("agent")
    run, tools = send("列出全部时间的所有日程，不限日期")
    assert run["status"] == "completed" and not tools
    assert "全部时间" in run["final_answer"] and "日程0项" in run["final_answer"]
    assert send.traces[-1]["observations"][0]["tool_name"] == "list_all_events"


def test_all_time_overflow_explains_limit_without_failed_run(cloud, request):
    send = request.getfixturevalue("agent")
    for i in range(51):
        add_event(cloud, f"日程{i}", "2035-12-20")
    run, tools = send("列出全部时间的日程")
    assert run["status"] == "completed" and not tools, run
    assert "超过50条" in run["final_answer"]
    assert "未返回完整列表" in run["final_answer"]
    assert "日程0项" not in run["final_answer"]
