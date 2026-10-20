from datetime import date
from types import SimpleNamespace

from backend.features.auth.email_summary import summary_body


def test_summary_groups_sorts_and_preserves_full_notes():
    day = date(2026, 9, 17)
    todos = [
        SimpleNamespace(
            due_date=day,
            due_time=time,
            title=title,
            description="详细备注" * 600,
            assignment_note="带上材料",
        )
        for time, title in [(None, "购物"), ("09:00", "开会")]
    ]
    body = summary_body(todos, day, day, "Asia/Shanghai")
    assert body.index("开会") < body.index("购物")
    assert "未完成待办：2 项" in body
    assert "2026-09-17（周四）" in body
    assert "时间：09:00" in body and "未设置具体时间" in body
    assert "详细备注" * 600 in body and "协作说明：带上材料" in body


def test_empty_summary_has_explicit_range():
    day = date(2026, 9, 17)
    body = summary_body([], day, day, "Asia/Shanghai")
    assert "未完成待办：0 项" in body
    assert "暂无未完成待办" in body
