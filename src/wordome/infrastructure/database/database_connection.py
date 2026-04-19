import snowflake.connector

from wordome.infrastructure.database.database_config import settings


class DatabaseConnection:
    """Manages Snowflake database connection lifecycle"""

    def __init__(self):
        self._connection = None

    def get_connection(self):
        """Get a Snowflake connection"""
        print(f"SETTINGS: {settings}")
        if self._connection is None or self._connection.is_closed():
            self._connection = snowflake.connector.connect(
                account=settings.account,
                user=settings.user,
                password=settings.password,
                warehouse=settings.warehouse,
                database=settings.database,
                schema=settings.schema,
            )
            print(f"CONNECTION: {self._connection}")
        return self._connection

    def test_connection(self):
        """Simple test to verify connection works"""
        conn = self.get_connection()
        cur = conn.cursor()
        try:
            cur.execute("SELECT CURRENT_VERSION()")
            version = cur.fetchone()[0]
            print(f"✅ Connected! Snowflake version: {version}")
            return True
        except Exception as e:
            print(f"❌ Connection failed: {e}")
            return False
        finally:
            cur.close()

    def close(self):
        """Close the connection"""
        if self._connection and not self._connection.is_closed():
            self._connection.close()
            self._connection = None
