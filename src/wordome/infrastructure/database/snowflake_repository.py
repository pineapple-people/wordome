from datetime import datetime
from typing import Any

from wordome.infrastructure.database.snowflake_connection import SnowflakeConnection


class SnowflakeRepository:
    """
    Business logic for database operations
    """

    def __init__(self, connection: SnowflakeConnection | None = None):
        self._connection = connection or SnowflakeConnection()

    async def health_check(self) -> dict[str, Any]:
        """
        Comprehensive health status for the service
        """
        is_connected = await self._connection.is_connected()

        result = {
            "database_connected": is_connected,
            "service": "wordome",
            "timestamp": datetime.utcnow().isoformat(),
        }

        if is_connected:
            # Optional: Verify critical tables exist
            try:
                await self._verify_critical_tables()
                result["critical_tables_accessible"] = True
            except Exception:
                result["critical_tables_accessible"] = False

        return result

    async def ping(self) -> str | None:
        """
        Simple hello-world check (kept for backward compatibility)
        """
        try:
            result = await self._connection.execute(
                "SELECT 'hello world' AS message;", fetch_one=True
            )
            return result[0] if result else ""
        except Exception as e:
            print(f"Error occurred: {e}")
            return None

    # Example business methods:
    async def get_warehouse_count(self) -> int | None:
        """
        Get total number of warehouses in account
        """
        try:
            result = await self._connection.execute("SHOW WAREHOUSES;")
            return len(result) if result else 0
        except Exception as e:
            print(f"Error occurred: {e}")
            return None
