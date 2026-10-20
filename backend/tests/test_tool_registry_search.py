from backend.features.assistant.tool_registry import search


def test_read_prompts_find_list_tools_before_writes():
    for prompt in ("看下旅行清单", "看下清单"):
        results = search(prompt)
        assert results[0]["name"] == "list_checklists"
        assert any(item["mode"] == "write" for item in results)


def test_recording_alias_finds_voice_memo_reader():
    assert search("现在有几个录音")[0]["name"] == "list_voice_memos"


def test_explicit_write_search_and_mode_filter_still_work():
    assert search("创建清单")[0]["name"] == "create_checklist"
    assert search("创建清单", mode="write", limit=1)[0]["name"] == "create_checklist"
    assert all(item["mode"] == "read" for item in search("清单", mode="read"))


def test_colloquial_existing_item_queries_expose_reader_in_first_model_tools():
    for prompt in ("有什么待办", "有啥待办", "现在有什么待办"):
        assert search(prompt)[0]["name"] == "list_todos"
