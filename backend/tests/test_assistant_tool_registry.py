import pytest

from backend.features.assistant.tool_registry import search


@pytest.mark.parametrize(
    "query",
    [
        "把刚才新创建的日程改成 我爱我家 可见",
        "把待办设为家庭可见",
        "把清单分享给家人",
        "这个库存项仅自己可见",
    ],
)
def test_registry_prioritizes_sharing_changes(query):
    assert search(query)[0]["name"] == "set_sharing"


@pytest.mark.parametrize("query", ["标记完成", "完成待办", "待办做完"])
def test_registry_prioritizes_todo_completion(query):
    assert search(query)[0]["name"] == "edit_todo"


def test_registry_keeps_explicit_checklist_completion():
    assert search("把清单项标记完成")[0]["name"] == "check_item"
