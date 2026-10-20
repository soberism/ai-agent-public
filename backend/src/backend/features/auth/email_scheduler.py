"""随 API 生命周期运行，每分钟检查启用提醒或摘要的用户。"""

import asyncio
import logging

from sqlalchemy import or_, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.api.routes.parity_email import EmailDispatch, dispatch_email
from backend.core.security import APIError, settings
from backend.db.models import User
from backend.db.parity_models import EmailPreference
from backend.db.session import engine

logger = logging.getLogger(__name__)


def run_once():
    if not all(
        (
            settings.smtp_host,
            settings.smtp_username,
            settings.smtp_password.get_secret_value(),
            settings.smtp_from,
        )
    ):
        return
    cursor = None
    while True:
        with Session(engine) as session:
            query = (
                select(User.id)
                .outerjoin(EmailPreference)
                .where(
                    User.active,
                    or_(
                        EmailPreference.owner_id.is_(None),
                        EmailPreference.notifications_enabled,
                    ),
                    or_(
                        EmailPreference.owner_id.is_(None),
                        EmailPreference.reminder_enabled,
                        EmailPreference.daily_enabled,
                        EmailPreference.weekly_enabled,
                    ),
                )
                .order_by(User.id)
                .limit(100)
            )
            if cursor is not None:
                query = query.where(User.id > cursor)
            ids = list(session.scalars(query))
        if not ids:
            return
        for user_id in ids:
            try:
                with Session(engine) as session:
                    user = session.get(User, user_id)
                    if user and user.active:
                        dispatch_email(EmailDispatch(), user, session)
            except (SQLAlchemyError, APIError, ValueError, OSError) as error:
                # 只记类型，避免数据库参数或邮件内容泄露。
                logger.warning("邮件调度用户检查失败：%s", type(error).__name__)
        cursor = ids[-1]


async def run_scheduler(stop: asyncio.Event):
    logger.info("邮件提醒定时任务已启动，检查间隔 60 秒")
    while not stop.is_set():
        try:
            await asyncio.to_thread(run_once)
        except (SQLAlchemyError, APIError, ValueError, OSError) as error:
            logger.warning("邮件调度扫描失败：%s", type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass
