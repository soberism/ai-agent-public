"""Enabled search, todo, calendar and checklist tools missing from the base map."""

PLANNING_CAPABILITIES = {
    "search_business": (
        "assistant_tool_adapters.search_business",
        "全局搜索系统内可访问事项",
        True,
        "search",
        "/search",
    ),
    "open_connections": (
        "assistant_tool_adapters.open_connections",
        "打开连接管理页面",
        True,
        "navigation",
        "/connections",
    ),
    "list_todos": (
        "todos.listing",
        "查询待办，支持今天、明天、逾期和日期范围",
        True,
        "todo",
        "/todos",
    ),
    "get_todo": ("todos.detail", "查看待办详情", True, "todo", "/todos"),
    "create_todo": ("todos.create", "创建待办", False, "todo", "/todos"),
    "create_daily_todos": (
        "assistant_tool_adapters.create_daily_todos",
        "按起止日期每天同一时间创建一条待办（最多50天）",
        False,
        "todo",
        "/todos",
    ),
    "delete_todo": ("todos.remove", "删除待办", False, "todo", "/todos"),
    "delete_event": ("calendar_events.remove", "删除日程", False, "event", "/calendar"),
    "delete_events": (
        "calendar_events.remove_batch",
        "按查询结果批量删除日期范围内的日程（最多50条）",
        False,
        "event",
        "/calendar",
    ),
    "create_checklist": (
        "planning.create_checklist",
        "创建清单及清单项",
        False,
        "checklist",
        "/checklists",
    ),
    "rename_checklist": (
        "planning.rename_checklist",
        "重命名清单",
        False,
        "checklist",
        "/checklists",
    ),
    "delete_checklist": (
        "planning.delete_checklist",
        "删除清单",
        False,
        "checklist",
        "/checklists",
    ),
}
