import asyncio
import logging

from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from backend.core.security import redis
from backend.db.session import engine
from backend.features.assistant.history import purge

logger = logging.getLogger(__name__)


async def run_cleanup(stop: asyncio.Event):
    while not stop.is_set():
        try:
            await asyncio.to_thread(cleanup_once)
        except (SQLAlchemyError, RedisError) as error:
            logger.warning("对话清理失败：%s", type(error).__name__)
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass


def cleanup_once():
    with Session(engine) as session:
        purge(session, redis)
