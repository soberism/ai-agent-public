from itertools import groupby


def summary_body(todos, start, end, timezone):
    items = sorted(
        todos, key=lambda todo: (todo.due_date, todo.due_time or "99:99", todo.title)
    )
    lines = [
        "待办摘要",
        f"日期范围：{start:%Y-%m-%d} 至 {end:%Y-%m-%d}",
        f"时区：{timezone}",
        f"未完成待办：{len(items)} 项",
        "",
    ]
    if not items:
        lines.append("此日期范围内暂无未完成待办。")
    for day, group in groupby(items, key=lambda todo: todo.due_date):
        lines.append(
            f"{day:%Y-%m-%d}（{['周一', '周二', '周三', '周四', '周五', '周六', '周日'][day.weekday()]}）"
        )
        for index, todo in enumerate(group, 1):
            lines.extend(
                [
                    f"{index}. {todo.title}",
                    f"   时间：{todo.due_time or '未设置具体时间'}",
                    "   状态：未完成",
                ]
            )
            if todo.description:
                lines.append(f"   备注：{todo.description}")
            if todo.assignment_note:
                lines.append(f"   协作说明：{todo.assignment_note}")
        lines.append("")
    lines.append(
        "本摘要仅包含上述日期范围内未完成的待办，不包含日历日程；内容以发送时为准。"
    )
    return "\n".join(lines)
