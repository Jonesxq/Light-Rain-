
"""数据库连接管理模块"""
from typing import Any, Optional
from app.core.logger import logger_manager
from app.core.database.mysql import mysql_manager

logger = logger_manager.get_logger(__name__)


class DatabaseConnectionManager:
    """数据库连接管理器"""
    def __init__(self):
        """初始化数据库连接管理器"""
        self.mysql_manager = mysql_manager
    
    async def initialize(self) -> None:
        """初始化数据库连接"""
        await self.mysql_manager.initialize()
    
    async def test_connections(self) -> bool:
        """测试数据库连接"""
        try:
            # 测试数据库连接
            await self.mysql_manager.test_connection()
            logger.info("✅ 所有数据库连接测试成功")
            return True
        except Exception as e:
            logger.error(f"❌ 连接测试失败: {e}")
            raise
    
    async def close(self) -> None:
        """关闭数据库连接"""
        await self.mysql_manager.close()
    
    async def __aenter__(self) -> "DatabaseConnectionManager":
        """异步上下文管理器入口"""
        await self.initialize()
        return self
    
    async def __aexit__(
        self,
        exc_type: Optional[type],
        exc_value: Optional[Exception],
        traceback: Optional[Any],
    ) -> None:
        """异步上下文管理器退出"""
        if exc_type is not None:
            logger.error(
                f"❌ 数据库连接管理器上下文中发生异常: "
                f"{exc_type.__name__}: {exc_value}"
            )
        await self.close()
        # 返回False表示不抑制异常，让其继续传播
        return False


db_manager = DatabaseConnectionManager()

