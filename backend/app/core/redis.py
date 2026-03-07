"""Redis管理模块 - 提供同步和异步Redis客户端"""
from redis.asyncio import Redis as AsyncRedis
from redis.asyncio import from_url as async_from_url
from redis import Redis as SyncRedis
from redis import from_url as sync_from_url
from app.core.config.settings import settings
from app.core.logger import logger_manager

class RedisManager:
    """Redis管理器 - 管理同步和异步Redis连接"""
    def __init__(self):
        """初始化Redis管理器"""
        self.logger = logger_manager.get_logger(__name__)
        self.async_client: AsyncRedis | None = None
        self.sync_client: SyncRedis | None = None
        self.config = settings.redis
    
    async def initialize_async(self) -> None:
        """初始化异步Redis客户端"""
        if self.async_client:
            self.logger.debug("Redis异步客户端已初始化。")
            return
        
        try:
            self.async_client = async_from_url(
                self.config.REDIS_CONNECTION_URL,
                decode_responses=True,
                max_connections=self.config.REDIS_POOL_SIZE,
                socket_timeout=self.config.REDIS_SOCKET_TIMEOUT,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            self.logger.info("✅ Redis异步客户端已初始化。")
        except Exception:
            self.logger.exception("❌ 初始化Redis异步客户端失败。")
            raise
    
    def initialize_sync(self) -> None:
        """初始化同步Redis客户端"""
        if self.sync_client:
            self.logger.debug("Redis同步客户端已初始化。")
            return
        
        try:
            self.sync_client = sync_from_url(
                self.config.REDIS_CONNECTION_URL,
                decode_responses=True,
                max_connections=self.config.REDIS_POOL_SIZE,
                socket_timeout=self.config.REDIS_SOCKET_TIMEOUT,
                retry_on_timeout=True,
                health_check_interval=30,
            )
            self.logger.info("✅ Redis同步客户端已初始化。")
        except Exception:
            self.logger.exception("❌ 初始化Redis同步客户端失败。")
            raise
    
    # -------------------------------
    # ✅ 异步方法 - 用于FastAPI
    # -------------------------------
    
    async def get_async_client(self) -> AsyncRedis:
        """获取异步Redis客户端"""
        if not self.async_client:
            await self.initialize_async()
        return self.async_client
    
    async def get_async(self, key: str) -> str | None:
        """异步获取键值"""
        client = await self.get_async_client()
        return await client.get(key)
    
    async def set_async(self, key: str, value: str, ex: int = None) -> bool:
        """异步设置键值"""
        client = await self.get_async_client()
        ex = ex or self.config.REDIS_DEFAULT_TTL
        return await client.set(key, value, ex=ex)
    
    async def delete_async(self, *keys: str) -> int:
        """异步删除键"""
        client = await self.get_async_client()
        return await client.delete(*keys)
    
    async def delete_pattern_async(self, pattern: str) -> int:
        """异步删除匹配模式的键"""
        client = await self.get_async_client()
        keys = await client.keys(pattern)
        return await client.delete(*keys) if keys else 0
    
    async def async_test_connection(self) -> bool:
        """异步测试连接"""
        try:
            client = await self.get_async_client()
            await client.ping()
            self.logger.info("✅ Redis异步客户端连接测试成功。")
            return True
        except Exception:
            self.logger.exception("❌ Redis异步客户端连接测试失败。")
            raise
    
    # -------------------------------
    # ✅ 同步方法 - 用于Celery/脚本
    # -------------------------------
    
    def get_sync_client(self) -> SyncRedis:
        """获取同步Redis客户端"""
        if not self.sync_client:
            self.initialize_sync()
        return self.sync_client
    
    def get_sync(self, key: str) -> str | None:
        """同步获取键值"""
        return self.get_sync_client().get(key)
    
    def set_sync(self, key: str, value: str, ex: int = None) -> bool:
        """同步设置键值"""
        ex = ex or self.config.REDIS_DEFAULT_TTL
        return self.get_sync_client().set(key, value, ex=ex)
    
    def delete_sync(self, *keys: str) -> int:
        """同步删除键"""
        return self.get_sync_client().delete(*keys)
    
    def delete_pattern_sync(self, pattern: str) -> int:
        """同步删除匹配模式的键"""
        client = self.get_sync_client()
        keys = client.keys(pattern)
        return client.delete(*keys) if keys else 0
    
    def sync_test_connection(self) -> bool:
        """同步测试连接"""
        try:
            client = self.get_sync_client()
            client.ping()
            self.logger.info("✅ Redis同步客户端连接测试成功。")
            return True
        except Exception:
            self.logger.exception("❌ Redis同步客户端连接测试失败。")
            raise
    
    # -------------------------------
    # ✅ 资源清理
    # -------------------------------
    
    async def close(self) -> None:
        """关闭连接"""
        if self.async_client:
            try:
                await self.async_client.close()
                self.async_client = None
                self.logger.info("✅ Redis异步客户端已关闭。")
            except Exception:
                self.logger.exception("❌ 关闭Redis异步客户端失败。")
        
        if self.sync_client:
            try:
                self.sync_client.close()
                self.sync_client = None
                self.logger.info("✅ Redis同步客户端已关闭。")
            except Exception:
                self.logger.exception("❌ 关闭Redis同步客户端失败。")
    
    async def __aenter__(self) -> "RedisManager":
        """异步上下文管理器入口"""
        await self.initialize_async()
        return self
    
    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        """异步上下文管理器出口"""
        await self.close()


# 单例实例
redis_manager = RedisManager()
