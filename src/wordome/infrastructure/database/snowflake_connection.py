import asyncio
from contextlib import asynccontextmanager
from typing import Any

import snowflake.connector

from wordome.infrastructure.database.snowflake_config import get_snowflake_config


class SnowflakeConnection:
    """Pure connection management - no business logic"""

    def __init__(self):
        """Load config lazily using your cached config function"""
        self._config = get_snowflake_config()

    async def _run(self, fn, *args, **kwargs):
        """Run blocking database call in a worker thread"""
        return await asyncio.to_thread(fn, *args, **kwargs)

    @asynccontextmanager
    async def get_connection(self):
        """Low-level connection provider"""
        conn = await self._run(
            snowflake.connector.connect,
            user=self._config.user,
            password=self._config.password,
            account=self._config.account,
            warehouse=self._config.warehouse,
            database=self._config.database,
            schema=self._config.schema,
        )
        try:
            yield conn
        finally:
            await self._run(conn.close)

    async def execute(self, sql: str, fetch_one: bool = False) -> Any:
        """Generic SQL execution without business interpretation"""
        async with self.get_connection() as conn:

            def _execute():
                with conn.cursor() as cur:
                    cur.execute(sql)
                    return cur.fetchone() if fetch_one else cur.fetchall()

            return await self._run(_execute)

    async def execute_many(self, sql: str, params_list: list[tuple]) -> None:
        """Execute same query with multiple parameter sets"""
        async with self.get_connection() as conn:

            def _execute_many():
                with conn.cursor() as cur:
                    cur.executemany(sql, params_list)
                    conn.commit()

            await self._run(_execute_many)

    async def is_connected(self) -> bool:
        """
        Pure technical check (does connection work?)
        """
        try:
            await self.execute("SELECT 1", fetch_one=True)
            return True
        except Exception:
            return False
