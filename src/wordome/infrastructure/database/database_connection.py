import asyncio
from contextlib import asynccontextmanager

import snowflake.connector

from wordome.infrastructure.database.database_config import settings


class DatabaseConnection:
    async def _run(self, fn, *args, **kwargs):
        return await asyncio.to_thread(fn, *args, **kwargs)

    @asynccontextmanager
    async def session(self):
        conn = await self._run(
            snowflake.connector.connect,
            user=settings.user,
            password=settings.password,
            account=settings.account,
            warehouse=settings.warehouse,
            database=settings.database,
            schema=settings.schema,
        )
        try:
            yield conn
        finally:
            await self._run(conn.close)

    async def test_connection(self):
        """
        Test Snowflake connectivity
        Just open/close a connection
        """
        async with self.session():
            print("Connection successful")

    def _execute_fetchone(self, conn, sql: str):
        with conn.cursor() as cur:
            cur.execute(sql)
            return cur.fetchone()

    async def test_query(self):
        """
        Test example query
        """
        async with self.session() as conn:
            row = await self._run(
                self._execute_fetchone, conn, "SELECT 'hello world' AS message;"
            )
            print(row[0])
