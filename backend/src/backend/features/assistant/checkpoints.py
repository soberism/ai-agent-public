"""Keep checkpoint writes and conversation deletion on the same database lock order."""

from contextlib import contextmanager
from uuid import UUID

from langgraph.checkpoint.postgres import PostgresSaver

from backend.core.security import APIError


class RunSaver(PostgresSaver):
    run_id: str | None = None

    # shortcut: depends on the saver cursor hook; recheck integration on dependency upgrades.
    @contextmanager
    def _cursor(self, *, pipeline=False):
        # The saver owns its connection; its cursor transaction must also own the run lock.
        with (
            super()._cursor(pipeline=pipeline) as cursor,
            cursor.connection.transaction(),
        ):
            if self.run_id is not None:
                cursor.execute(
                    "SELECT id FROM agent_runs WHERE id = %s FOR KEY SHARE",
                    (UUID(self.run_id),),
                )
                if cursor.fetchone() is None:
                    raise APIError(410, "THREAD_EXPIRED", "对话已过期，请重新开始")
            yield cursor
