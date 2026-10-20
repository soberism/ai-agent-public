"""按账号修正旧时区，保留日期和墙上时间；默认仅预览。"""

import argparse
from datetime import UTC, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import Settings
from backend.db.models import CalendarEvent, Todo, User
from backend.db.session import engine


def shanghai_time(value, old_zone):
    return (
        value.astimezone(ZoneInfo(old_zone))
        .replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        .astimezone(UTC)
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("account", type=UUID)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    if Settings().app_env != "development":
        raise SystemExit("仅允许开发环境运行")
    with Session(engine) as session, session.begin():
        user = session.scalar(
            select(User).where(User.id == args.account).with_for_update()
        )
        if user is None:
            raise SystemExit("账号不存在")
        todos = list(
            session.scalars(
                select(Todo)
                .where(Todo.owner_id == user.id, Todo.timezone != "Asia/Shanghai")
                .with_for_update()
            )
        )
        events = list(
            session.scalars(
                select(CalendarEvent)
                .where(
                    CalendarEvent.owner_id == user.id,
                    CalendarEvent.timezone != "Asia/Shanghai",
                )
                .with_for_update()
            )
        )
        print(f"待办 {len(todos)} 条，日程 {len(events)} 条；保留日期和时间")
        if not args.apply:
            return
        for todo in todos:
            todo.due_at = (
                datetime.combine(
                    todo.due_date, todo.due_time, ZoneInfo("Asia/Shanghai")
                ).astimezone(UTC)
                if todo.due_date and todo.due_time
                else None
            )
            todo.timezone = "Asia/Shanghai"
        for event in events:
            event.starts_at = shanghai_time(event.starts_at, event.timezone)
            event.ends_at = shanghai_time(event.ends_at, event.timezone)
            event.timezone = "Asia/Shanghai"
        user.timezone = "Asia/Shanghai"
        session.flush()
        print("修正完成（事务提交后生效）")


if __name__ == "__main__":
    assert shanghai_time(
        datetime(2026, 9, 17, 12, tzinfo=UTC), "America/Montevideo"
    ) == datetime(2026, 9, 17, 1, tzinfo=UTC)
    main()
