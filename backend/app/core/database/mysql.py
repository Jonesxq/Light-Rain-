
"""MySQL数据库管理模块 - 提供异步和同步MySQL连接、会话管理和表创建"""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from app.core.logger import logger_manager
from app.core.config.settings import settings
from sqlmodel import SQLModel

# SQLAlchemy声明基类
Base = declarative_base()

class MySQLManager:
    """MySQL数据库管理器 - 管理异步和同步数据库连接、会话和表创建"""
    
    def __init__(self):
        """初始化MySQL管理器
        
        设置日志记录器和数据库引擎/会话工厂的初始状态
        """
        self.logger = logger_manager.get_logger(__name__)
        self.async_engine: create_async_engine | None = None
        self.async_session_maker: async_sessionmaker | None = None
        self.sync_engine: create_engine | None = None
        self.sync_session_maker: sessionmaker | None = None
    
    def get_sqlalchemy_url(self) -> str:
        """获取异步SQLAlchemy连接URL
        
        确保使用aiomysql驱动进行异步操作
        
        Returns:
            str: 配置好的异步数据库连接URL
        """
        url = settings.database.DATABASE_URL
        # 确保使用aiomysql驱动
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+aiomysql://", 1)
        elif url.startswith("mysql+pymysql://"):
            return url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
        return url
    
    def get_sync_sqlalchemy_url(self) -> str:
        """获取同步SQLAlchemy连接URL
        
        确保使用pymysql驱动进行同步操作
        
        Returns:
            str: 配置好的同步数据库连接URL
        """
        url = settings.database.DATABASE_URL
        # 确保使用pymysql驱动
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+pymysql://", 1)
        elif url.startswith("mysql+aiomysql://"):
            return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
        return url
    
    async def initialize(self) -> None:
        """初始化MySQL数据库连接
        
        创建异步和同步引擎、会话工厂，并创建数据库表
        
        Raises:
            Exception: 初始化失败时抛出异常
        """
        if self.async_engine:
            self.logger.debug("MySQLManager is already initialized.")
            return
        
        try:
            db = settings.database
            
            # 初始化异步引擎
            self.async_engine = create_async_engine(
                self.get_sqlalchemy_url(),
                echo=db.ECHO,
                pool_pre_ping=db.POOL_PRE_PING,
                pool_timeout=db.POOL_TIMEOUT,
                pool_size=db.POOL_SIZE,
                max_overflow=db.POOL_MAX_OVERFLOW,
                # 设置MySQL时区为UTC（会话级别）
                connect_args={
                    "init_command": "SET SESSION time_zone = '+00:00'",
                    "charset": "utf8mb4",
                },
            )
            await self._create_tables()
            
            self.async_session_maker = async_sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # 初始化同步引擎（用于后台任务）
            self.sync_engine = create_engine(
                self.get_sync_sqlalchemy_url(),
                echo=db.ECHO,
                pool_pre_ping=db.POOL_PRE_PING,
                pool_timeout=db.POOL_TIMEOUT,
                pool_size=db.POOL_SIZE,
                max_overflow=db.POOL_MAX_OVERFLOW,
                connect_args={
                    "init_command": "SET SESSION time_zone = '+00:00'",
                    "charset": "utf8mb4",
                },
            )
            
            self.sync_session_maker = sessionmaker(
                self.sync_engine,
                class_=Session,
                expire_on_commit=False,
            )
            
            self.logger.info("✅ MySQL initialized successfully (async + sync).")
        except Exception:
            self.logger.exception("❌ Failed to initialize MySQL.")
            raise
    
    async def get_db(self) -> AsyncGenerator[AsyncSession, None]:
        """获取异步数据库会话的生成器
        
        Yields:
            AsyncSession: 异步数据库会话
            
        Raises:
            RuntimeError: 数据库未初始化时抛出异常
        """
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        async with self.async_session_maker() as session:
            yield session
    
    def get_sync_db(self) -> Session:
        """获取同步数据库会话
        
        Returns:
            Session: 同步数据库会话
            
        Raises:
            RuntimeError: 数据库未初始化时抛出异常
        """
        if not self.sync_session_maker:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.sync_session_maker()
    
    async def test_connection(self) -> bool:
        """测试数据库连接
        
        Returns:
            bool: 连接成功返回True
            
        Raises:
            RuntimeError: 连接测试失败时抛出异常
        """
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized.")
        
        try:
            async with self.async_session_maker() as session:
                result = await session.execute(text("SELECT 1"))
                if result.scalar() != 1:
                    raise RuntimeError("❌ MySQL connection test failed.")
                self.logger.info("✅ MySQL connection test passed.")
                return True
        except Exception:
            self.logger.exception("❌ MySQL connection test failed.")
            raise
    
    async def close(self) -> None:
        """关闭数据库连接
        
        释放异步和同步引擎资源
        
        Raises:
            Exception: 关闭失败时抛出异常
        """
        if self.async_engine:
            try:
                await self.async_engine.dispose()
                self.async_engine = None
                self.async_session_maker = None
                self.logger.info("✅ MySQL async engine disposed successfully.")
            except Exception:
                self.logger.exception("❌ Failed to dispose MySQL async engine.")
                raise
        
        if self.sync_engine:
            try:
                self.sync_engine.dispose()
                self.sync_engine = None
                self.sync_session_maker = None
                self.logger.info("✅ MySQL sync engine disposed successfully.")
            except Exception:
                self.logger.exception("❌ Failed to dispose MySQL sync engine.")
                raise
    
    async def __aenter__(self) -> "MySQLManager":
        """异步上下文管理器入口
        
        Returns:
            MySQLManager: 当前管理器实例
        """
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """异步上下文管理器出口
        
        Args:
            exc_type: 异常类型
            exc_value: 异常值
            traceback: 异常追踪
        """
        await self.close()

    async def _create_tables(self) -> None:
        """创建数据库表
        
        显式导入所有数据模型以确保它们被注册到SQLModel元数据中，
        然后创建所有表
        """
        from app.models.user import User
        from app.models.token import RefreshToken, VerificationCode
        from app.models.chat import ChatSession, ChatMessage, ChatAttachment, ChatPromptSnapshot
        from app.models.llm_settings import UserLLMSettings
        from app.models.usage import UsageEvent, UserUsageSettings
        # 在这里显式导入所有模型，确保它们被注册到 SQLModel.metadata 中
        # 如果不导入，SQLModel 就不知道有哪些表需要创建
        self.logger.info("🚀 Creating database tables...")
        async with self.async_engine.begin() as conn:
            # 使用 run_sync 调用 SQLModel 的同步建表方法
            await conn.run_sync(SQLModel.metadata.create_all)


# 单例实例
mysql_manager = MySQLManager()


