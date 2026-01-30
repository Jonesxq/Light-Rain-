"""database connection managementgenerator"""

from typing import Any, Optional
from app.core.logger import logger_manager
from app.core.database.mysql import mysql_manager

logger = logger_manager.get_logger(__name__)


class DatabaseConnectionManager:
    """database connection managementgenerator - unifiedmanagementdatabase connection"""
    
    def __init__(self):
        self.mysql_manager = mysql_manager
    
    async def initialize(self) -> None:
        """Initializealldatabase connection"""
        await self.mysql_manager.initialize()
    
    async def test_connections(self) -> bool:
        """testalldatabase connection"""
        try:
            # testdatabase connection
            await self.mysql_manager.test_connection()
            logger.info("✅ All database connections tested successfully")
            return True
        except Exception as e:
            logger.error(f"❌ Connection test failed: {e}")
            raise
    
    async def close(self) -> None:
        """closealldatabase connection"""
        await self.mysql_manager.close()
    
    async def __aenter__(self) -> "DatabaseConnectionManager":
        """Enter context manager"""
        await self.initialize()
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_value: Optional[Exception],
        traceback: Optional[Any],
    ) -> None:
        """Exit context manager"""
        if exc_type is not None:
            logger.error(
                f"❌ Exception occurred in DatabaseConnectionManager context: "
                f"{exc_type.__name__}: {exc_value}"
            )
        await self.close()
        # return False means don't suppress exception, let it propagate
        return False


db_manager = DatabaseConnectionManager()

