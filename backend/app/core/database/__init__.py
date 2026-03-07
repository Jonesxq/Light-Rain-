"""数据库模块 - 提供数据库连接管理和依赖注入"""
from .connection import db_manager
from .mysql import mysql_manager, Base

async def get_db():
    """获取数据库会话的依赖注入函数
    
    Yields:
        AsyncSession: 异步数据库会话
    """
    async for session in mysql_manager.get_db():
        yield session

__all__ = ["db_manager", "mysql_manager", "Base", "get_db"]
