
"""core/database/mysql.py."""
from collections.abc import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, declarative_base
from app.core.logger import logger_manager
from app.core.config.settings import settings
from sqlmodel import SQLModel

# SQLAlchemy declarativebase class
Base = declarative_base()

class MySQLManager:
    
    """MySQLManager ??"""
    def __init__(self):
        """__init__ ???"""
        self.logger = logger_manager.get_logger(__name__)
        self.async_engine: create_async_engine | None = None
        self.async_session_maker: async_sessionmaker | None = None
        self.sync_engine: create_engine | None = None
        self.sync_session_maker: sessionmaker | None = None
    
    def get_sqlalchemy_url(self) -> str:
        """get_sqlalchemy_url ???"""
        url = settings.database.DATABASE_URL
        # ensure using aiomysql driver
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+aiomysql://", 1)
        elif url.startswith("mysql+pymysql://"):
            return url.replace("mysql+pymysql://", "mysql+aiomysql://", 1)
        return url
    
    def get_sync_sqlalchemy_url(self) -> str:
        """get_sync_sqlalchemy_url ???"""
        url = settings.database.DATABASE_URL
        # ensure using pymysql driver
        if url.startswith("mysql://"):
            return url.replace("mysql://", "mysql+pymysql://", 1)
        elif url.startswith("mysql+aiomysql://"):
            return url.replace("mysql+aiomysql://", "mysql+pymysql://", 1)
        return url
    
    async def initialize(self) -> None:
        """initialize ?????"""
        if self.async_engine:
            self.logger.debug("MySQLManager is already initialized.")
            return
        
        try:
            db = settings.database
            
            # Initialize async engine
            self.async_engine = create_async_engine(
                self.get_sqlalchemy_url(),
                echo=db.ECHO,
                pool_pre_ping=db.POOL_PRE_PING,
                pool_timeout=db.POOL_TIMEOUT,
                pool_size=db.POOL_SIZE,
                max_overflow=db.POOL_MAX_OVERFLOW,
                # Set MySQL timezone to UTC (session level)
                connect_args={
                    "init_command": "SET SESSION time_zone = '+00:00'",
                },
            )
            await self._create_tables()
            
            self.async_session_maker = async_sessionmaker(
                self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )
            
            # Initialize sync engine (for background tasks)
            self.sync_engine = create_engine(
                self.get_sync_sqlalchemy_url(),
                echo=db.ECHO,
                pool_pre_ping=db.POOL_PRE_PING,
                pool_timeout=db.POOL_TIMEOUT,
                pool_size=db.POOL_SIZE,
                max_overflow=db.POOL_MAX_OVERFLOW,
                connect_args={
                    "init_command": "SET SESSION time_zone = '+00:00'",
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
        """get_db ?????"""
        if not self.async_session_maker:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        
        async with self.async_session_maker() as session:
            yield session
    
    def get_sync_db(self) -> Session:
        """get_sync_db ???"""
        if not self.sync_session_maker:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self.sync_session_maker()
    
    async def test_connection(self) -> bool:
        """test_connection ?????"""
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
        """close ?????"""
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
        """__aenter__ ?????"""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """__aexit__ ?????"""
        await self.close()

    async def _create_tables(self) -> None:
        """_create_tables ?????"""
        from app.models.user import User
        from app.models.token import RefreshToken, VerificationCode
        from app.models.chat import ChatSession, ChatMessage, ChatAttachment, ChatPromptSnapshot  # 你新定义的智聊模型
        from app.models.llm_settings import UserLLMSettings
        from app.models.usage import UsageEvent, UserUsageSettings
        # 在这里显式导入所有模型，确保它们被注册到 SQLModel.metadata 中
        # 如果不导入，SQLModel 就不知道有哪些表需要创建
        self.logger.info("🚀 Creating database tables...")
        async with self.async_engine.begin() as conn:
            # 使用 run_sync 调用 SQLModel 的同步建表方法
            await conn.run_sync(SQLModel.metadata.create_all)


# singletoninstance
mysql_manager = MySQLManager()


