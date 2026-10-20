from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from backend.core.config import Settings


class Base(DeclarativeBase):
    pass


engine = create_engine(
    Settings().database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 3, "options": "-c statement_timeout=5000"},
)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
