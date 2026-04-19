import asyncio
from contextlib import asynccontextmanager

import snowflake.connector

from wordome.infrastructure.database.database_config import Settings, get_settings


class DatabaseConnection:
    def __init__(self, settings: Settings | None = None):
        """Store connection settings, loading them lazily by default."""
        self._settings = settings or get_settings()

    async def _run(self, fn, *args, **kwargs):
        """
        Run a blocking database call in a worker thread.
        """
        return await asyncio.to_thread(fn, *args, **kwargs)

    @asynccontextmanager
    async def session(self):
        """
        Open a Snowflake connection and always close it afterward.
        """
        conn = await self._run(
            snowflake.connector.connect,
            user=self._settings.user,
            password=self._settings.password,
            account=self._settings.account,
            warehouse=self._settings.warehouse,
            database=self._settings.database,
            schema=self._settings.schema,
        )
        try:
            yield conn
        finally:
            await self._run(conn.close)

    def _execute_fetchone(self, conn, sql: str):
        """
        Execute a query and return a single row.
        """
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()

    async def ping(self) -> str:
        """
        Run a tiny query to confirm the database connection works.
        """
        async with self.session() as conn:
            row = await self._run(
                self._execute_fetchone, conn, "SELECT 'hello world' AS message;"
            )
            return row[0] if row else ""
